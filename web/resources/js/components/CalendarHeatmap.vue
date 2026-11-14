<script setup>
// Month × year table of harmonized hotspots. Every cell shows its number and typical error; the colour is
// one of five classes with round limits (legend); ▲ / ▼ mark months well above / below the usual range of
// that calendar month (above its 90th / below its 10th percentile). A "Year" column sums each row and a
// "Median" row shows the typical month. Hover or move with the arrow keys for the full read-out.
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { classBreaks, classColor, classLegend, classOf, textOn } from '../colors';
import { compact, monthName, monthYear, num, pct } from '../format';

const props = defineProps({ data: { type: Object, required: true } });
const emit = defineEmits(['select']);
const { t, locale } = useI18n();

const svg = ref(null);
defineExpose({ svg });

const LABEL_W = 66; // fits "Median" / "Медіана" as well as the years
const CELL_W = 48;
const CELL_H = 34;
const HEAD_H = 26;
const TOTAL_W = 64;
const GAP = 2;
const MEDIAN_GAP = 10;

const years = computed(() => props.data.years);
const byKey = computed(() => {
    const m = new Map();
    for (const c of props.data.cells) m.set(`${c.year}-${c.month}`, c);
    return m;
});
const base = computed(() => props.data.baseline.by_month);
const breaks = computed(() => classBreaks(props.data.scale.max));
const legend = computed(() => classLegend(breaks.value));

const width = LABEL_W + 12 * CELL_W + TOTAL_W;
const medianY = computed(() => HEAD_H + years.value.length * CELL_H + MEDIAN_GAP);
const height = computed(() => medianY.value + CELL_H + 4);
const months = computed(() => {
    void locale.value; // re-render month names on language change
    return Array.from({ length: 12 }, (_, i) => monthName(i + 1));
});

const cellX = (col) => LABEL_W + (col - 1) * CELL_W;
const rowY = (r) => HEAD_H + r * CELL_H;
const fillOf = (v) => classColor(classOf(v, breaks.value));

/** 'high' above the 90th percentile of the same calendar month, 'low' below the 10th; months in progress are not judged. */
function flag(c) {
    if (!c || c.partial) return null;
    const b = base.value[c.month - 1];
    if (b?.p90 != null && c.count > b.p90) return 'high';
    if (b?.p10 != null && c.count < b.p10) return 'low';
    return null;
}

// Per year: the harmonized total and, for the read-out, what each sensor contributed.
const yearTotals = computed(() => {
    const out = new Map();
    for (const c of props.data.cells) {
        const y = out.get(c.year) ?? {
            year: c.year, count: 0, error: 0, partial: false, incomplete: false,
            modis: { count: 0, raw: 0, months: 0 }, viirs: { count: 0, raw: 0, months: 0 },
        };
        y.count += c.count;
        y.error = y.error === null || c.count_error == null ? null : y.error + c.count_error;
        y.partial ||= c.partial;
        y.incomplete ||= c.incomplete;
        const s = y[c.source] ?? y.viirs;
        s.count += c.count;
        s.raw += c.count_raw;
        s.months += 1;
        out.set(c.year, y);
    }
    return out;
});

function label(c) {
    const parts = [
        t('calendar.cell', { month: monthYear(c.year, c.month), count: num(c.count) }),
        c.count_error ? t('calendar.error', { err: num(c.count_error) }) : null,
        flag(c) ? t(`calendar.flag.${flag(c)}`) : null,
        c.partial ? t('calendar.partial') : null,
        c.incomplete ? t('calendar.incomplete') : null,
    ];
    return parts.filter(Boolean).join('. ');
}

// --- keyboard / hover ------------------------------------------------------------
const active = ref({ row: 0, col: 0 });
const hover = ref(null);
const focused = ref(false);
const pos = computed(() => hover.value ?? (focused.value ? active.value : null));
const shown = computed(() => (pos.value ? byKey.value.get(`${years.value[pos.value.row]}-${pos.value.col + 1}`) ?? null : null));
const YEAR_COL = 12; // the "Year" column after the twelve months
const shownYear = computed(() => (pos.value?.col === YEAR_COL ? yearTotals.value.get(years.value[pos.value.row]) ?? null : null));
const shownBase = computed(() => (shown.value ? base.value[shown.value.month - 1] : null));
const vsMedian = computed(() => {
    const c = shown.value;
    const m = c?.median_to_date;
    return c && m ? (c.count / m - 1) * 100 : null;
});
// Read-out beside the cell: right of it in the first half of the year, left in the second; below it in
// the upper half of the table, above it in the lower half.
const tipStyle = computed(() => {
    if (!pos.value) return {};
    const { row, col } = pos.value;
    const style = {};
    if (col < 6) style.left = `${((cellX(col + 2) + 4) / width) * 100}%`;
    else style.right = `${((width - cellX(col + 1) + 4) / width) * 100}%`;
    if (row < years.value.length / 2) style.top = `${(rowY(row) / height.value) * 100}%`;
    else style.bottom = `${((height.value - rowY(row) - CELL_H) / height.value) * 100}%`;
    return style;
});

watch(
    () => props.data,
    () => {
        // Start on the most recent month with data.
        const last = props.data.cells[props.data.cells.length - 1];
        if (last) active.value = { row: years.value.indexOf(last.year), col: last.month - 1 };
    },
    { immediate: true },
);

function focusCell(row, col) {
    row = Math.max(0, Math.min(years.value.length - 1, row));
    col = Math.max(0, Math.min(11, col));
    active.value = { row, col };
    svg.value?.querySelector(`[data-cell="${row}-${col}"]`)?.focus();
    emit('select', years.value[row]);
}

function onKey(e) {
    const { row, col } = active.value;
    const moves = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1], Home: [0, -col], End: [0, 11 - col] };
    const m = moves[e.key];
    if (!m) return;
    e.preventDefault();
    focusCell(row + m[0], col + m[1]);
}
</script>

<template>
    <div>
        <div class="overflow-x-auto">
            <div class="relative min-w-[640px] max-w-[1000px]">
                <svg
                    ref="svg"
                    :viewBox="`0 0 ${width} ${height}`"
                    class="block h-auto w-full select-none"
                    role="grid"
                    :aria-label="t('calendar.title')"
                    :aria-describedby="'calendar-help'"
                    @keydown="onKey"
                    @focusin="focused = true"
                    @focusout="focused = false"
                    @mouseleave="hover = null"
                >
                    <defs>
                        <pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                            <line x1="0" y1="0" x2="0" y2="5" stroke="#000" stroke-opacity="0.25" stroke-width="2" />
                        </pattern>
                        <!-- Days without any satellite: hatched the other way, so it reads apart from "month in progress". -->
                        <pattern id="hatch-incomplete" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
                            <line x1="0" y1="0" x2="0" y2="5" stroke="#000" stroke-opacity="0.25" stroke-width="2" />
                        </pattern>
                    </defs>

                    <!-- header -->
                    <g role="row">
                        <text
                            v-for="(m, i) in months"
                            :key="'h' + i"
                            :x="cellX(i + 1) + CELL_W / 2"
                            :y="HEAD_H - 9"
                            text-anchor="middle"
                            class="fill-current text-[11px]"
                            :class="pos?.col === i ? 'font-semibold text-ink' : 'text-muted'"
                            role="columnheader"
                        >{{ m }}</text>
                        <text :x="cellX(13) + TOTAL_W - 6" :y="HEAD_H - 9" text-anchor="end" class="fill-current text-[11px] text-muted" role="columnheader">{{ t('calendar.yearTotal') }}</text>
                    </g>

                    <g v-for="(year, r) in years" :key="year" role="row">
                        <text
                            :x="LABEL_W - 8"
                            :y="rowY(r) + CELL_H / 2 + 4"
                            text-anchor="end"
                            class="fill-current text-[12px] font-medium tabular-nums"
                            role="rowheader"
                        >{{ year }}</text>

                        <g
                            v-for="col in 12"
                            :key="col"
                            role="gridcell"
                            :data-cell="`${r}-${col - 1}`"
                            :tabindex="active.row === r && active.col === col - 1 ? 0 : -1"
                            :aria-label="byKey.get(`${year}-${col}`) ? label(byKey.get(`${year}-${col}`)) : monthYear(year, col) + ': —'"
                            class="outline-none [&:focus-visible>rect.frame]:stroke-[3]"
                            @focus="active = { row: r, col: col - 1 }"
                            @click="focusCell(r, col - 1)"
                            @mouseenter="hover = { row: r, col: col - 1 }"
                        >
                            <template v-for="c in [byKey.get(`${year}-${col}`)]" :key="'c'">
                                <template v-if="c">
                                    <rect :x="cellX(col) + GAP / 2" :y="rowY(r) + GAP / 2" :width="CELL_W - GAP" :height="CELL_H - GAP" rx="3" :fill="fillOf(c.count) || 'var(--wc-zero)'" />
                                    <rect v-if="c.partial" :x="cellX(col) + GAP / 2" :y="rowY(r) + GAP / 2" :width="CELL_W - GAP" :height="CELL_H - GAP" rx="3" fill="url(#hatch)" />
                                    <rect v-if="c.incomplete" :x="cellX(col) + GAP / 2" :y="rowY(r) + GAP / 2" :width="CELL_W - GAP" :height="CELL_H - GAP" rx="3" fill="url(#hatch-incomplete)" />
                                    <text
                                        :x="cellX(col) + CELL_W / 2"
                                        :y="rowY(r) + (c.count_error ? 15 : CELL_H / 2 + 4)"
                                        text-anchor="middle"
                                        class="pointer-events-none text-[12px] font-medium tabular-nums"
                                        :fill="fillOf(c.count) ? textOn(fillOf(c.count)) : 'currentColor'"
                                        :class="fillOf(c.count) ? '' : 'fill-current text-muted'"
                                    >{{ compact(c.count) }}</text>
                                    <text
                                        v-if="c.count_error"
                                        :x="cellX(col) + CELL_W / 2"
                                        :y="rowY(r) + 27"
                                        text-anchor="middle"
                                        class="pointer-events-none text-[9px] tabular-nums"
                                        :fill="fillOf(c.count) ? textOn(fillOf(c.count)) : 'currentColor'"
                                        fill-opacity="0.8"
                                    >±{{ compact(c.count_error) }}</text>
                                    <text
                                        v-if="flag(c)"
                                        :x="cellX(col) + CELL_W - 5"
                                        :y="rowY(r) + 10"
                                        text-anchor="end"
                                        class="pointer-events-none text-[9px]"
                                        :fill="fillOf(c.count) ? textOn(fillOf(c.count)) : 'currentColor'"
                                    >{{ flag(c) === 'high' ? '▲' : '▼' }}</text>
                                </template>
                            </template>
                            <rect
                                class="frame"
                                :x="cellX(col) + GAP / 2"
                                :y="rowY(r) + GAP / 2"
                                :width="CELL_W - GAP"
                                :height="CELL_H - GAP"
                                rx="3"
                                fill="none"
                                :stroke="pos && pos.row === r && pos.col === col - 1 ? 'var(--wc-ink)' : 'none'"
                                stroke-width="2"
                            />
                        </g>

                        <!-- year total: one harmonized number; hover for what each sensor gave -->
                        <g
                            role="gridcell"
                            :aria-label="`${year}: ${num(yearTotals.get(year)?.count)}${yearTotals.get(year)?.error ? ' ± ' + num(yearTotals.get(year).error) : ''}`"
                            @mouseenter="hover = { row: r, col: YEAR_COL }"
                        >
                            <rect :x="cellX(13) + GAP" :y="rowY(r) + GAP / 2" :width="TOTAL_W - GAP" :height="CELL_H - GAP" rx="3" :fill="pos && pos.row === r && pos.col === YEAR_COL ? 'var(--wc-line)' : 'transparent'" />
                            <text :x="cellX(13) + TOTAL_W - 6" :y="rowY(r) + CELL_H / 2 + 4" text-anchor="end" class="fill-current text-[12px] font-semibold tabular-nums">{{ compact(yearTotals.get(year)?.count) }}</text>
                        </g>
                    </g>

                    <!-- typical month -->
                    <g role="row">
                        <text :x="LABEL_W - 8" :y="medianY + CELL_H / 2 + 4" text-anchor="end" class="fill-current text-[11px] font-medium" role="rowheader">{{ t('calendar.medianRow') }}</text>
                        <g v-for="b in base" :key="'md' + b.month" role="gridcell" :aria-label="`${monthName(b.month, 'long')}: ${t('season.median')} ${num(b.median)}`">
                            <rect :x="cellX(b.month) + GAP / 2" :y="medianY + GAP / 2" :width="CELL_W - GAP" :height="CELL_H - GAP" rx="3" :fill="fillOf(b.median) || 'var(--wc-zero)'" stroke="currentColor" stroke-opacity="0.35" stroke-dasharray="3 2" />
                            <text
                                :x="cellX(b.month) + CELL_W / 2"
                                :y="medianY + CELL_H / 2 + 4"
                                text-anchor="middle"
                                class="text-[12px] font-medium tabular-nums"
                                :fill="fillOf(b.median) ? textOn(fillOf(b.median)) : 'currentColor'"
                            >{{ compact(b.median === null ? null : Math.round(b.median)) }}</text>
                        </g>
                    </g>
                </svg>

                <!-- read-out of a year total -->
                <div
                    v-if="shownYear"
                    class="pointer-events-none absolute z-10 w-64 rounded-md border border-line bg-panel/95 p-2 text-xs shadow-lg backdrop-blur"
                    :style="tipStyle"
                    role="status"
                    aria-live="polite"
                >
                    <p class="mb-1 text-sm font-semibold">{{ shownYear.year }}<span v-if="shownYear.partial" class="font-normal text-muted"> · {{ t('anomalies.incomplete') }}</span></p>
                    <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 tabular-nums">
                        <dt class="text-muted">{{ t('calendar.tip.hotspots') }}</dt>
                        <dd class="text-right font-semibold">{{ num(shownYear.count) }}<span v-if="shownYear.error" class="font-normal text-muted"> ± {{ num(shownYear.error) }}</span></dd>
                        <template v-for="s in ['modis', 'viirs']" :key="s">
                            <template v-if="shownYear[s].months">
                                <dt class="text-muted">{{ s === 'modis' ? t('calendar.tip.fromModis') : t('calendar.tip.fromViirs') }}</dt>
                                <dd class="text-right">{{ num(shownYear[s].count) }}</dd>
                                <dd class="col-span-2 -mt-0.5 text-right text-[10px] text-muted">{{ t('calendar.tip.sensorDetail', { months: shownYear[s].months, raw: num(shownYear[s].raw) }) }}</dd>
                            </template>
                        </template>
                    </dl>
                    <p v-if="shownYear.modis.months" class="mt-1 text-[10px] text-muted">{{ t('calendar.tip.modisNote') }}</p>
                    <p v-if="shownYear.incomplete" class="text-muted">{{ t('calendar.incomplete') }}</p>
                </div>

                <!-- read-out of the hovered / focused month -->
                <div
                    v-if="shown"
                    class="pointer-events-none absolute z-10 w-60 rounded-md border border-line bg-panel/95 p-2 text-xs shadow-lg backdrop-blur"
                    :style="tipStyle"
                    role="status"
                    aria-live="polite"
                >
                    <p class="mb-1 text-sm font-semibold">{{ monthYear(shown.year, shown.month) }}</p>
                    <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 tabular-nums">
                        <dt class="text-muted">{{ t('calendar.tip.hotspots') }}</dt>
                        <dd class="text-right font-semibold">{{ num(shown.count) }}<span v-if="shown.count_error" class="font-normal text-muted"> ± {{ num(shown.count_error) }}</span></dd>
                        <dt class="text-muted">{{ t('calendar.tip.detections') }}</dt>
                        <dd class="text-right">{{ num(shown.count_raw) }} · {{ shown.source === 'modis' ? 'MODIS' : 'VIIRS' }}</dd>
                        <dt class="text-muted">{{ shown.partial ? t('calendar.tip.medianToDate') : t('calendar.tip.median', { month: monthName(shown.month, 'long') }) }}</dt>
                        <dd class="text-right">{{ num(shown.median_to_date) }}</dd>
                        <dt class="text-muted">{{ t('calendar.tip.usual') }}</dt>
                        <dd class="text-right">{{ num(shownBase?.p10) }} – {{ num(shownBase?.p90) }}</dd>
                        <dt class="text-muted">{{ t('calendar.tip.vsMedian') }}</dt>
                        <dd class="text-right font-medium">{{ pct(vsMedian) }}</dd>
                    </dl>
                    <p v-if="flag(shown)" class="mt-1 font-medium">{{ flag(shown) === 'high' ? '▲' : '▼' }} {{ t(`calendar.flag.${flag(shown)}`) }}</p>
                    <p v-if="shown.rank" class="mt-1 text-muted">{{ t('calendar.tip.rank', { rank: shown.rank, of: shown.rank_of, month: monthName(shown.month, 'long') }) }}</p>
                    <p v-if="shown.partial" class="text-muted">{{ t('calendar.tip.partial', { days: shown.days_elapsed, total: shown.days_in_month }) }}</p>
                    <p v-if="shown.incomplete" class="text-muted">{{ t('calendar.incomplete') }}</p>
                </div>
            </div>
        </div>

        <p id="calendar-help" class="sr-only">{{ t('calendar.keyboard') }}</p>

        <!-- Legend -->
        <div class="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted">
            <div class="flex flex-wrap items-center gap-1" :aria-label="t('calendar.legendCounts')">
                <span class="mr-1">{{ t('calendar.legendCounts') }}:</span>
                <span class="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5" style="background: var(--wc-zero)">0</span>
                <span
                    v-for="l in legend"
                    :key="l.k"
                    class="inline-flex items-center rounded-sm px-1.5 py-0.5 tabular-nums"
                    :style="{ background: l.color, color: textOn(l.color) }"
                >{{ l.to === null ? `> ${compact(l.from - 1)}` : l.from === l.to ? compact(l.from) : `${compact(l.from)}–${compact(l.to)}` }}</span>
            </div>
            <div>▲ {{ t('calendar.flag.high') }} · ▼ {{ t('calendar.flag.low') }}</div>
            <div>±N = {{ t('calendar.errorLegend') }}</div>
            <div class="flex items-center gap-1.5">
                <svg width="14" height="14" aria-hidden="true"><rect width="14" height="14" rx="2" fill="var(--wc-zero)" /><rect width="14" height="14" rx="2" fill="url(#hatch)" /></svg>
                {{ t('calendar.partial') }}
            </div>
            <div class="flex items-center gap-1.5">
                <svg width="14" height="14" aria-hidden="true"><rect width="14" height="14" rx="2" fill="var(--wc-zero)" /><rect width="14" height="14" rx="2" fill="url(#hatch-incomplete)" /></svg>
                {{ t('calendar.incomplete') }}
            </div>
        </div>
    </div>
</template>
