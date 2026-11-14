<script setup>
// Month × year heatmap. Every cell carries its number (or the anomaly %) as text,
// is reachable by keyboard (roving tabindex + arrow keys) and has a spoken label.
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { diverging, legendStops, sequential, textOn } from '../colors';
import { compact, monthName, monthYear, num, pct } from '../format';

const props = defineProps({
    data: { type: Object, required: true },
    mode: { type: String, default: 'counts' }, // counts | anomaly
});
const emit = defineEmits(['select']);
const { t, locale } = useI18n();

const svg = ref(null);
defineExpose({ svg });

const LABEL_W = 46;
const SRC_W = 58;
const CELL_W = 46;
const CELL_H = 24;
const HEAD_H = 26;
const GAP = 2;

const years = computed(() => props.data.years);
const byKey = computed(() => {
    const m = new Map();
    for (const c of props.data.cells) m.set(`${c.year}-${c.month}`, c);
    return m;
});
const width = LABEL_W + 12 * CELL_W + SRC_W;
const height = computed(() => HEAD_H + years.value.length * CELL_H + 4);
const switchRow = computed(() => years.value.findIndex((y) => y >= 2012));
const months = computed(() => {
    void locale.value; // re-render month names on language change
    return Array.from({ length: 12 }, (_, i) => monthName(i + 1));
});

function cellFill(c) {
    if (!c) return null;
    return props.mode === 'anomaly' ? diverging(c.anomaly_pct) : sequential(c.count, props.data.scale.max);
}

function cellText(c) {
    if (!c) return '';
    if (props.mode === 'anomaly') return c.anomaly_pct === null ? '·' : `${c.anomaly_pct > 0 ? '+' : ''}${Math.round(c.anomaly_pct)}`;
    return c.count === 0 ? '0' : compact(c.count);
}

function rowSource(year) {
    const sources = new Set(props.data.cells.filter((c) => c.year === year).map((c) => c.source));
    if (sources.size > 1) return 'MODIS/VIIRS';
    return sources.has('modis') ? 'MODIS*' : 'VIIRS';
}

function label(c) {
    const head = t('calendar.cell', { month: monthYear(c.year, c.month), count: num(c.count) });
    const detail = t('calendar.cellDetail', {
        source: c.source === 'modis' ? t('calendar.modis') : t('calendar.viirs'),
        raw: num(c.count_raw),
        mean: num(props.data.baseline.by_month[c.month - 1]?.mean, 0),
        anomaly: pct(c.anomaly_pct),
    });
    const notes = [
        c.count_error ? t('calendar.error', { err: num(c.count_error) }) : null,
        c.partial ? t('calendar.partial') : null,
        c.incomplete ? t('calendar.incomplete') : null,
    ].filter(Boolean);
    return `${head}. ${detail}${notes.length ? ' (' + notes.join('; ') + ')' : ''}`;
}

// --- keyboard / hover ------------------------------------------------------------
const active = ref({ row: 0, col: 0 });
const hover = ref(null);
const shown = computed(() => {
    const pos = hover.value ?? active.value;
    return byKey.value.get(`${years.value[pos.row]}-${pos.col + 1}`) ?? null;
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
            <svg
                ref="svg"
                :viewBox="`0 0 ${width} ${height}`"
                class="block h-auto w-full max-w-[940px] min-w-[560px] select-none"
                role="grid"
                :aria-label="t('calendar.title')"
                :aria-describedby="'calendar-help'"
                @keydown="onKey"
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

                <!-- month header -->
                <g role="row">
                    <text
                        v-for="(m, i) in months"
                        :key="'h' + i"
                        :x="LABEL_W + i * CELL_W + CELL_W / 2"
                        :y="HEAD_H - 9"
                        text-anchor="middle"
                        class="fill-current text-[11px] text-muted"
                        role="columnheader"
                    >{{ m }}</text>
                </g>

                <g v-for="(year, r) in years" :key="year" role="row">
                    <text
                        :x="LABEL_W - 8"
                        :y="HEAD_H + r * CELL_H + CELL_H / 2 + 4"
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
                        <template v-if="byKey.get(`${year}-${col}`)">
                            <rect
                                :x="LABEL_W + (col - 1) * CELL_W + GAP / 2"
                                :y="HEAD_H + r * CELL_H + GAP / 2"
                                :width="CELL_W - GAP"
                                :height="CELL_H - GAP"
                                rx="3"
                                :fill="cellFill(byKey.get(`${year}-${col}`)) || 'var(--wc-zero)'"
                            />
                            <rect
                                v-if="byKey.get(`${year}-${col}`).partial"
                                :x="LABEL_W + (col - 1) * CELL_W + GAP / 2"
                                :y="HEAD_H + r * CELL_H + GAP / 2"
                                :width="CELL_W - GAP"
                                :height="CELL_H - GAP"
                                rx="3"
                                fill="url(#hatch)"
                            />
                            <rect
                                v-if="byKey.get(`${year}-${col}`).incomplete"
                                :x="LABEL_W + (col - 1) * CELL_W + GAP / 2"
                                :y="HEAD_H + r * CELL_H + GAP / 2"
                                :width="CELL_W - GAP"
                                :height="CELL_H - GAP"
                                rx="3"
                                fill="url(#hatch-incomplete)"
                            />
                            <text
                                :x="LABEL_W + (col - 1) * CELL_W + CELL_W / 2"
                                :y="HEAD_H + r * CELL_H + CELL_H / 2 + 4"
                                text-anchor="middle"
                                class="text-[11px] tabular-nums pointer-events-none"
                                :class="cellFill(byKey.get(`${year}-${col}`)) ? '' : 'fill-current text-muted'"
                                :fill="cellFill(byKey.get(`${year}-${col}`)) ? textOn(cellFill(byKey.get(`${year}-${col}`))) : 'currentColor'"
                            >{{ cellText(byKey.get(`${year}-${col}`)) }}</text>
                        </template>
                        <rect
                            class="frame"
                            :x="LABEL_W + (col - 1) * CELL_W + GAP / 2"
                            :y="HEAD_H + r * CELL_H + GAP / 2"
                            :width="CELL_W - GAP"
                            :height="CELL_H - GAP"
                            rx="3"
                            fill="none"
                            :stroke="active.row === r && active.col === col - 1 ? 'var(--wc-ink)' : 'none'"
                            stroke-width="2"
                        />
                    </g>

                    <text
                        :x="LABEL_W + 12 * CELL_W + 8"
                        :y="HEAD_H + r * CELL_H + CELL_H / 2 + 4"
                        class="fill-current text-[10px] text-muted"
                        aria-hidden="true"
                    >{{ rowSource(year) }}</text>
                </g>

                <!-- MODIS → VIIRS switch -->
                <line
                    v-if="switchRow > 0"
                    :x1="LABEL_W - 40"
                    :x2="width - 4"
                    :y1="HEAD_H + switchRow * CELL_H"
                    :y2="HEAD_H + switchRow * CELL_H"
                    stroke="currentColor"
                    stroke-dasharray="4 3"
                    class="text-ink"
                    aria-hidden="true"
                />
            </svg>
        </div>

        <p id="calendar-help" class="sr-only">{{ t('calendar.keyboard') }}</p>

        <!-- Text read-out of the hovered / focused month -->
        <p class="mt-2 min-h-[2.5rem] text-sm" aria-live="polite">
            <template v-if="shown">
                <strong>{{ monthYear(shown.year, shown.month) }}: {{ num(shown.count) }}<template v-if="shown.count_error"> ± {{ num(shown.count_error) }}</template></strong>
                <span class="text-muted">
                    · {{ shown.source === 'modis' ? t('calendar.modis') : t('calendar.viirs') }}
                    · {{ t('calendar.vsMean', { pct: pct(shown.anomaly_pct) }) }}
                    <template v-if="shown.partial"> · {{ t('calendar.partial') }}</template>
                    <template v-if="shown.incomplete"> · {{ t('calendar.incomplete') }}</template>
                </span>
            </template>
        </p>

        <!-- Legend -->
        <div class="mt-1 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted">
            <div class="flex items-center gap-2">
                <span>{{ mode === 'anomaly' ? t('calendar.below') : t('calendar.fewer') }}</span>
                <span
                    class="h-3 w-40 rounded-sm"
                    :style="{ background: `linear-gradient(90deg, ${(mode === 'anomaly' ? legendStops.diverging : legendStops.sequential).join(',')})` }"
                    aria-hidden="true"
                ></span>
                <span>{{ mode === 'anomaly' ? t('calendar.above') : t('calendar.more') }}</span>
                <span v-if="mode === 'counts'" class="tabular-nums">(0 – {{ num(data.scale.max) }})</span>
                <span v-else class="tabular-nums">(−100 % … +100 %)</span>
            </div>
            <div class="flex items-center gap-1.5">
                <svg width="14" height="14" aria-hidden="true"><rect width="14" height="14" rx="2" fill="var(--wc-zero)" /><rect width="14" height="14" rx="2" fill="url(#hatch)" /></svg>
                {{ t('calendar.partial') }}
            </div>
            <div class="flex items-center gap-1.5">
                <svg width="14" height="14" aria-hidden="true"><rect width="14" height="14" rx="2" fill="var(--wc-zero)" /><rect width="14" height="14" rx="2" fill="url(#hatch-incomplete)" /></svg>
                {{ t('calendar.incomplete') }}
            </div>
            <div>MODIS* = {{ t('calendar.modis') }}</div>
        </div>
    </div>
</template>
