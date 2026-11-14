<script setup>
// Full-size Leaflet map with Leaflet.draw for the AOI. All Leaflet controls sit on the
// right; App overlays its own panels (controls on the left, statistics on the right).
import { onBeforeUnmount, onMounted, ref, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import { api } from '../api';
import { sequential } from '../colors';
import { date, num } from '../format';

// Leaflet.draw uses 20 px vertex handles on touch-capable browsers (most desktops today); halve them.
const HANDLE = 10;
function shrinkHandles() {
    const icon = (className) => new L.DivIcon({ iconSize: new L.Point(HANDLE, HANDLE), className });
    const vertex = 'leaflet-div-icon leaflet-editing-icon';
    for (const proto of [L.Draw.Polyline.prototype, L.Edit.PolyVerticesEdit.prototype]) {
        proto.options.icon = icon(vertex);
        proto.options.touchIcon = icon(vertex);
    }
    Object.assign(L.Edit.SimpleShape.prototype.options, {
        moveIcon: icon('leaflet-div-icon leaflet-editing-icon leaflet-edit-move'),
        resizeIcon: icon('leaflet-div-icon leaflet-editing-icon leaflet-edit-resize'),
        touchMoveIcon: icon('leaflet-div-icon leaflet-editing-icon leaflet-edit-move leaflet-touch-icon'),
        touchResizeIcon: icon('leaflet-div-icon leaflet-editing-icon leaflet-edit-resize leaflet-touch-icon'),
    });
}

// Leaflet.draw texts ("Cancel", "Save", tooltips) in the current UI language, with clearer wording.
function localizeDraw() {
    const d = L.drawLocal;
    const a = (key) => ({ title: t(`draw.${key}.title`), text: t(`draw.${key}.text`) });
    d.draw.toolbar.actions = a('cancel');
    d.draw.toolbar.finish = a('finish');
    d.draw.toolbar.undo = a('undo');
    d.draw.toolbar.buttons.rectangle = t('aoi.draw');
    d.draw.toolbar.buttons.polygon = t('aoi.drawPolygon');
    d.draw.handlers.rectangle.tooltip.start = t('draw.tip.rectStart');
    d.draw.handlers.simpleshape.tooltip.end = t('draw.tip.rectEnd');
    d.draw.handlers.polygon.tooltip = {
        start: t('draw.tip.polyStart'),
        cont: t('draw.tip.polyCont'),
        end: t('draw.tip.polyEnd'),
    };
    d.edit.toolbar.actions.save = a('save');
    d.edit.toolbar.actions.cancel = a('revert');
    d.edit.toolbar.buttons.edit = t('draw.editButton');
    d.edit.handlers.edit.tooltip = { text: t('draw.tip.editText'), subtext: t('draw.tip.editSub') };
}

const props = defineProps({
    modelValue: { type: Object, default: null },
    // Pixels covered by overlay panels, so fitBounds keeps the AOI visible: [left, right].
    insets: { type: Array, default: () => [0, 0] },
    // The parent is asking "delete the shape?": show the confirmation bar next to the trash button.
    confirmDelete: { type: Boolean, default: false },
    // Dates of the fires layer (YYYY-MM-DD); empty until the app knows the data range.
    dateFrom: { type: String, default: '' },
    dateTo: { type: String, default: '' },
});
// 'delete' asks to remove the shape, 'delete-confirm' confirms it, 'delete-cancel' (trash clicked again) backs out.
const emit = defineEmits(['update:modelValue', 'delete', 'delete-confirm', 'delete-cancel']);
const { t, locale } = useI18n();

const el = ref(null);
let map = null;
let drawn = null;
let lastEmitted = null;

const STYLE = { color: '#b4410f', weight: 2.5, fillOpacity: 0.1 };
// showArea is off: Leaflet.draw 1.0.4 throws "type is not defined" in readableArea under ES modules.
// The area is shown in the statistics panel instead.
const RECT = { shapeOptions: STYLE, showArea: false };
const POLY = { allowIntersection: false, showArea: false, shapeOptions: STYLE };
const ring = computed(() => props.modelValue?.coordinates?.[0] ?? []);

const round = (v) => Math.round(v * 1e4) / 1e4;

// One shape at a time: while a shape exists the toolbar offers only edit/delete,
// otherwise only the draw tools.
let drawControl = null;
let editControl = null;
let deleteControl = null;

// Leaflet.draw's own delete mode (pick the shape, then Save/Cancel) is overkill for a single shape.
// This trash button asks the parent; while `confirmDelete` is on, a Leaflet-style action bar
// next to it offers a red "Delete area"; clicking the trash again cancels.
let confirmBar = null;
const DeleteControl = L.Control.extend({
    options: { position: 'topright' },
    onAdd() {
        const root = L.DomUtil.create('div', 'leaflet-draw');
        const section = L.DomUtil.create('div', 'leaflet-draw-section', root);
        const bar = L.DomUtil.create('div', 'leaflet-draw-toolbar leaflet-bar', section);
        const trash = L.DomUtil.create('a', 'leaflet-draw-edit-remove', bar);
        trash.href = '#';
        trash.title = t('draw.removeButton');
        trash.setAttribute('role', 'button');
        trash.innerHTML = `<span class="sr-only">${t('draw.removeButton')}</span>`;

        confirmBar = L.DomUtil.create('ul', 'leaflet-draw-actions leaflet-draw-actions-top', section);
        const action = (text, title, event) => {
            const a = L.DomUtil.create('a', 'wc-danger', L.DomUtil.create('li', '', confirmBar));
            a.href = '#';
            a.textContent = text;
            a.title = title;
            a.setAttribute('role', 'button');
            L.DomEvent.on(a, 'click', (e) => {
                L.DomEvent.preventDefault(e);
                emit(event);
            });
        };
        action(t('draw.confirmDelete.text'), t('draw.confirmDelete.title'), 'delete-confirm');
        showConfirm();

        L.DomEvent.disableClickPropagation(root);
        L.DomEvent.on(trash, 'click', (e) => {
            L.DomEvent.preventDefault(e);
            emit(props.confirmDelete ? 'delete-cancel' : 'delete');
        });
        return root;
    },
});

function showConfirm() {
    if (confirmBar) confirmBar.style.display = props.confirmDelete ? 'block' : 'none';
}

// Toolbar texts are read when a control is created, so rebuild both on a language change.
// Removing a toolbar also stops any draw/edit mode it started.
function buildControls() {
    if (drawControl) map.removeControl(drawControl);
    if (editControl) map.removeControl(editControl);
    if (deleteControl) map.removeControl(deleteControl);
    localizeDraw();
    drawControl = new L.Control.Draw({
        position: 'topright',
        draw: { polyline: false, circle: false, circlemarker: false, marker: false, rectangle: RECT, polygon: POLY },
        edit: false,
    });
    editControl = new L.Control.Draw({
        position: 'topright',
        draw: false,
        edit: { featureGroup: drawn, remove: false },
    });
    deleteControl = new DeleteControl();
    syncToolbar();
}

function syncToolbar() {
    if (!map || !drawControl) return;
    const hasShape = ring.value.length > 0;
    if (hasShape) {
        map.removeControl(drawControl);
        map.addControl(editControl);
        map.addControl(deleteControl);
    } else {
        map.removeControl(editControl);
        map.removeControl(deleteControl);
        map.addControl(drawControl);
    }
}

function isBox(points) {
    const open = points.length > 1 && points[0][0] === points.at(-1)[0] && points[0][1] === points.at(-1)[1] ? points.slice(0, -1) : points;
    if (open.length !== 4) return false;
    const xs = new Set(open.map((p) => p[0]));
    const ys = new Set(open.map((p) => p[1]));
    return xs.size === 2 && ys.size === 2;
}

function redraw(fit) {
    if (!map || !drawn) return;
    drawn.clearLayers();
    syncToolbar();
    if (!ring.value.length) return;
    const latlngs = ring.value.map(([lon, lat]) => [lat, lon]);
    // An axis-aligned box stays a rectangle while editing (its corners move together).
    const layer = isBox(ring.value) ? L.rectangle(L.latLngBounds(latlngs), STYLE) : L.polygon(latlngs, STYLE);
    drawn.addLayer(layer);
    if (fit) fitTo(layer.getBounds());
}

function fitTo(bounds) {
    // No animation: an interrupted zoom animation (or one in a background tab) can leave old tiles.
    map.fitBounds(bounds, {
        paddingTopLeft: [props.insets[0] + 24, 24],
        paddingBottomRight: [props.insets[1] + 24, 24],
        maxZoom: 9,
        animate: false,
    });
}

/** Start drawing from an outside button (bigger target than the Leaflet toolbar). */
// Uses the toolbar's own handler, so its action bar ("Finish shape", "Stop drawing") shows up too.
function startDraw(kind = 'rectangle') {
    if (!map || ring.value.length) return; // delete the current shape first
    const modes = drawControl._toolbars.draw._modes; // Leaflet.draw 1.0.4 internals
    for (const m of Object.values(modes)) m.handler.disable();
    modes[kind === 'polygon' ? 'polygon' : 'rectangle'].handler.enable();
}

defineExpose({ startDraw });

// --- fires layer --------------------------------------------------------------------
// Drawn on canvas: points from zoom 9, grid cells below (POST /api/map). MODIS points get their
// own colour, since their weight comes from the harmonization factor.
const MODIS = new Set(['Terra', 'Aqua']);
const POINT_COLOR = { modis: '#1b7f8c', viirs: '#bc3754' };
let fires = null;
let renderer = null;
let firesTimer = null;
let firesAbort = null;
const firesNote = ref('');

function scheduleFires() {
    clearTimeout(firesTimer);
    firesTimer = setTimeout(loadFires, 300); // the API is rate-limited per IP
}

async function loadFires() {
    if (!map || !props.dateFrom || !props.dateTo) return;
    firesAbort?.abort();
    firesAbort = new AbortController();
    const b = map.getBounds();
    const clip = (v, lim) => Math.max(-lim, Math.min(lim, v));
    const bbox = [clip(b.getWest(), 180), clip(b.getSouth(), 90), clip(b.getEast(), 180), clip(b.getNorth(), 90)];
    if (bbox[0] >= bbox[2] || bbox[1] >= bbox[3]) return;

    firesNote.value = t('fires.loading');
    try {
        const data = await api.map({ bbox, zoom: map.getZoom(), date_from: props.dateFrom, date_to: props.dateTo }, firesAbort.signal);
        drawFires(data);
        firesNote.value = data.truncated ? t('fires.zoomIn') : '';
    } catch (e) {
        if (e.name !== 'AbortError') firesNote.value = '';
    }
}

function drawFires(data) {
    fires.clearLayers();
    const maxCell = Math.max(0, ...data.features.filter((f) => f.properties.kind === 'cell').map((f) => f.properties.n_harm));
    for (const f of data.features) {
        const p = f.properties;
        if (p.kind === 'point') {
            const [lon, lat] = f.geometry.coordinates;
            const modis = MODIS.has(p.satellite);
            const lines = [
                `<strong>${modis ? t('fires.modis') : t('fires.viirs')}</strong> · ${p.satellite}`,
                date(p.acq_date) + (p.frp != null ? ` · FRP ${num(p.frp, 1)} MW` : ''),
                t('fires.weight', { w: num(p.weight, 2) }),
            ];
            if (p.own_share != null) lines.push(t('fires.ownShare', { p: `${num(p.own_share * 100)} %` }));
            L.circleMarker([lat, lon], {
                renderer,
                radius: 4,
                weight: 1,
                color: '#ffffff',
                fillColor: modis ? POINT_COLOR.modis : POINT_COLOR.viirs,
                fillOpacity: 0.9,
            })
                .bindTooltip(lines.join('<br>'))
                .addTo(fires);
        } else {
            const ring = f.geometry.coordinates[0];
            L.rectangle([[ring[0][1], ring[0][0]], [ring[2][1], ring[2][0]]], {
                renderer,
                weight: 0,
                fillColor: sequential(p.n_harm, maxCell) ?? 'transparent',
                fillOpacity: 0.45,
                interactive: true,
            })
                .bindTooltip(t('fires.cell', { n: num(p.n_harm), raw: num(p.n_raw) }))
                .addTo(fires);
        }
    }
}

watch(() => [props.dateFrom, props.dateTo], scheduleFires);

onMounted(async () => {
    // leaflet-draw expects a global L.
    window.L = L;
    await import('leaflet-draw');

    map = L.map(el.value, { worldCopyJump: true, zoomControl: false }).setView([30, 10], 3);
    L.control.zoom({ position: 'topright' }).addTo(map);

    // Free basemaps that need no API key (CARTO now requires one). The first one is the default.
    const layers = {
        [t('aoi.layers.osm')]: L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }),
        [t('aoi.layers.light')]: L.layerGroup([
            L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
                maxZoom: 16,
                attribution: 'Tiles &copy; Esri — Esri, HERE, Garmin, &copy; OpenStreetMap contributors',
            }),
            L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
                maxZoom: 16,
            }),
        ]),
        [t('aoi.layers.satellite')]: L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            { maxZoom: 18, attribution: 'Tiles &copy; Esri — Esri, Maxar, Earthstar Geographics, GIS User Community' },
        ),
    };
    Object.values(layers)[0].addTo(map);
    L.control.layers(layers, null, { position: 'topright' }).addTo(map);

    renderer = L.canvas({ padding: 0.2 });
    fires = L.layerGroup().addTo(map);
    // moveend also fires after every zoom, so a zoomend listener would double the requests.
    map.on('moveend', scheduleFires);
    scheduleFires();

    shrinkHandles();
    drawn = new L.FeatureGroup().addTo(map);
    buildControls();

    const fromLayer = (layer) => {
        const geom = layer.toGeoJSON().geometry;
        geom.coordinates = [geom.coordinates[0].map(([lon, lat]) => [round(lon), round(lat)])];
        // Ignore broken shapes (e.g. a click without a drag while the map was still loading).
        const pts = geom.coordinates[0];
        const ok = pts.every(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lon) <= 180 && Math.abs(lat) <= 90);
        if (!ok || new Set(pts.map((p) => p[0])).size < 2 || new Set(pts.map((p) => p[1])).size < 2) {
            redraw(false);
            return;
        }
        lastEmitted = JSON.stringify(geom);
        emit('update:modelValue', geom);
    };
    map.on(L.Draw.Event.CREATED, (e) => fromLayer(e.layer));
    map.on(L.Draw.Event.EDITED, (e) => e.layers.eachLayer(fromLayer));

    redraw(true);
});

onBeforeUnmount(() => {
    clearTimeout(firesTimer);
    firesAbort?.abort();
    map?.remove();
});

watch(
    () => props.modelValue,
    (value) => {
        // Don't jump the view when the user just drew the shape themselves.
        const fromMap = value && JSON.stringify(value) === lastEmitted;
        redraw(!fromMap);
    },
    { deep: true },
);

watch(() => props.confirmDelete, showConfirm);

watch(locale, () => {
    if (!map) return;
    // Removing the old toolbar stops any edit in progress; then put back the saved shape.
    buildControls();
    redraw(false);
});
</script>

<template>
    <div class="h-full w-full">
        <div ref="el" class="h-full w-full" role="application" :aria-label="t('aoi.title')"></div>
        <p
            v-if="firesNote"
            class="pointer-events-none absolute top-3 left-1/2 z-[500] -translate-x-1/2 rounded-md bg-panel/95 px-3 py-1 text-xs shadow"
            role="status"
        >{{ firesNote }}</p>
    </div>
</template>
