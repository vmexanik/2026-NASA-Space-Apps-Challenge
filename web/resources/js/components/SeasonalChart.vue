<script setup>
// Climatology: median per calendar month, 10–90th percentile band, and one selected year.
// Hovering a month (its whole column) or moving with ← → on the focused chart shows its numbers.
// The read-out is an HTML layer over the SVG, so PNG/SVG exports stay clean.
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { compact, monthName, num, pct } from '../format';

const props = defineProps({
    calendar: { type: Object, required: true },
    year: { type: Number, default: null },
});
const { t, locale } = useI18n();
const svg = ref(null);
defineExpose({ svg });

const W = 640;
const H = 260;
const M = { top: 16, right: 16, bottom: 30, left: 48 };
const iw = W - M.left - M.right;
const ih = H - M.top - M.bottom;

const base = computed(() => props.calendar.baseline.by_month);
const yearCells = computed(() => props.calendar.cells.filter((c) => c.year === props.year));
const yearByMonth = computed(() => new Map(yearCells.value.map((c) => [c.month, c])));
const max = computed(() => {
    const vals = [...base.value.map((b) => b.p90 ?? 0), ...yearCells.value.map((c) => c.count + (c.count_error ?? 0))];
    return Math.max(1, ...vals) * 1.08;
});

const x = (m) => M.left + ((m - 0.5) / 12) * iw;
const y = (v) => M.top + ih - (v / max.value) * ih;

const band = computed(() => {
    const top = base.value.map((b) => `${x(b.month)},${y(b.p90 ?? 0)}`);
    const bottom = [...base.value].reverse().map((b) => `${x(b.month)},${y(b.p10 ?? 0)}`);
    return [...top, ...bottom].join(' ');
});
const medianPath = computed(() => base.value.map((b, i) => `${i ? 'L' : 'M'}${x(b.month)},${y(b.median ?? 0)}`).join(' '));
const yearPath = computed(() => yearCells.value.map((c, i) => `${i ? 'L' : 'M'}${x(c.month)},${y(c.count)}`).join(' '));

const ticks = computed(() => {
    const step = niceStep(max.value / 4);
    const out = [];
    for (let v = 0; v <= max.value; v += step) out.push(v);
    return out;
});
function niceStep(raw) {
    const p = 10 ** Math.floor(Math.log10(raw || 1));
    const n = raw / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

const months = computed(() => {
    void locale.value;
    return Array.from({ length: 12 }, (_, i) => monthName(i + 1));
});

// --- read-out ------------------------------------------------------------------------
const active = ref(null); // month 1..12 under the pointer / keyboard
const info = computed(() => {
    if (!active.value) return null;
    const b = base.value[active.value - 1];
    const c = yearByMonth.value.get(active.value) ?? null;
    return {
        month: active.value,
        median: b?.median ?? null,
        p10: b?.p10 ?? null,
        p90: b?.p90 ?? null,
        years: b?.n ?? 0,
        cell: c,
        vsMedian: c && b?.median ? ((c.count / b.median - 1) * 100) : null,
    };
});
// Tooltip sits beside the guide line, flipped to the left in the second half of the year.
const tipStyle = computed(() => {
    if (!active.value) return {};
    const left = (x(active.value) / W) * 100;
    return active.value <= 6 ? { left: `calc(${left}% + 12px)` } : { right: `calc(${100 - left}% + 12px)` };
});

function onKey(e) {
    const moves = { ArrowLeft: -1, ArrowRight: 1, Home: -12, End: 12 };
    if (!(e.key in moves)) return;
    e.preventDefault();
    active.value = Math.min(12, Math.max(1, (active.value ?? 0) + moves[e.key]));
}
</script>

<template>
    <figure class="relative">
        <svg
            ref="svg"
            :viewBox="`0 0 ${W} ${H}`"
            class="h-auto w-full rounded outline-none focus-visible:ring-2 focus-visible:ring-accent"
            role="img"
            tabindex="0"
            :aria-labelledby="'season-title season-desc'"
            @keydown="onKey"
            @focus="active ??= yearCells.at(-1)?.month ?? 1"
            @blur="active = null"
            @mouseleave="active = null"
        >
            <title id="season-title">{{ t('season.title') }}</title>
            <desc id="season-desc">{{ t('season.desc') }} {{ t('season.keyboard') }}</desc>

            <g v-for="v in ticks" :key="v">
                <line :x1="M.left" :x2="W - M.right" :y1="y(v)" :y2="y(v)" stroke="currentColor" class="text-line" />
                <text :x="M.left - 6" :y="y(v) + 4" text-anchor="end" class="fill-current text-[11px] text-muted tabular-nums">{{ compact(v) }}</text>
            </g>
            <text
                v-for="(m, i) in months"
                :key="m"
                :x="x(i + 1)"
                :y="H - 10"
                text-anchor="middle"
                class="fill-current text-[11px]"
                :class="active === i + 1 ? 'font-semibold text-ink' : 'text-muted'"
            >{{ m }}</text>

            <polygon :points="band" fill="#fca50a" fill-opacity="0.22" />
            <path :d="medianPath" fill="none" stroke="#bc3754" stroke-width="2.5" />
            <path v-if="yearCells.length" :d="yearPath" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="5 3" class="text-ink" />

            <!-- guide line of the active month -->
            <line
                v-if="active"
                :x1="x(active)"
                :x2="x(active)"
                :y1="M.top"
                :y2="M.top + ih"
                stroke="currentColor"
                stroke-opacity="0.35"
                class="text-ink"
                pointer-events="none"
            />

            <!-- median nodes -->
            <circle
                v-for="b in base"
                :key="'m' + b.month"
                :cx="x(b.month)"
                :cy="y(b.median ?? 0)"
                :r="active === b.month ? 5 : 3"
                fill="#bc3754"
                pointer-events="none"
            />
            <!-- selected year: error bar + node -->
            <g v-for="c in yearCells" :key="c.month" pointer-events="none">
                <line
                    v-if="c.count_error"
                    :x1="x(c.month)"
                    :x2="x(c.month)"
                    :y1="y(c.count + c.count_error)"
                    :y2="y(Math.max(0, c.count - c.count_error))"
                    stroke="currentColor"
                    stroke-width="1.5"
                    class="text-ink"
                    :stroke-opacity="active === c.month ? 0.8 : 0.35"
                />
                <circle
                    :cx="x(c.month)"
                    :cy="y(c.count)"
                    :r="active === c.month ? 6 : 4"
                    fill="var(--wc-panel)"
                    stroke="currentColor"
                    stroke-width="2"
                    class="text-ink"
                />
            </g>

            <!-- hover targets: the whole column of each month -->
            <rect
                v-for="m in 12"
                :key="'h' + m"
                :x="x(m) - iw / 24"
                :y="M.top"
                :width="iw / 12"
                :height="ih + M.bottom"
                fill="transparent"
                @mouseenter="active = m"
            />
        </svg>

        <!-- read-out -->
        <div
            v-if="info"
            class="pointer-events-none absolute top-2 z-10 w-56 rounded-md border border-line bg-panel/95 p-2 text-xs shadow-lg backdrop-blur"
            :style="tipStyle"
            role="status"
            aria-live="polite"
        >
            <p class="mb-1 text-sm font-semibold">{{ monthName(info.month, 'long') }}</p>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 tabular-nums">
                <dt class="flex items-center gap-1.5 text-muted"><span class="inline-block h-0.5 w-3 bg-[#bc3754]"></span>{{ t('season.median') }}</dt>
                <dd class="text-right font-medium">{{ num(info.median) }}</dd>
                <dt class="flex items-center gap-1.5 text-muted"><span class="inline-block h-2 w-3 bg-[#fca50a]/40"></span>{{ t('season.usual') }}</dt>
                <dd class="text-right">{{ num(info.p10) }} – {{ num(info.p90) }}</dd>
                <template v-if="year">
                    <dt class="flex items-center gap-1.5 text-muted"><span class="inline-block h-0 w-3 border-t-2 border-dashed border-ink"></span>{{ year }}</dt>
                    <dd class="text-right font-semibold">
                        <template v-if="info.cell">{{ num(info.cell.count) }}<span v-if="info.cell.count_error" class="font-normal text-muted"> ± {{ num(info.cell.count_error) }}</span></template>
                        <template v-else>—</template>
                    </dd>
                </template>
            </dl>
            <p v-if="info.vsMedian !== null" class="mt-1 text-muted">{{ t('season.vsMedian', { pct: pct(info.vsMedian) }) }}</p>
            <p v-if="info.cell" class="text-muted">
                {{ info.cell.source === 'modis' ? t('calendar.modis') : t('calendar.viirs') }} · {{ t('season.detections', { n: num(info.cell.count_raw) }) }}
            </p>
            <p v-if="info.cell?.partial" class="text-muted">{{ t('calendar.partial') }}</p>
            <p v-if="info.cell?.incomplete" class="text-muted">{{ t('calendar.incomplete') }}</p>
            <p class="mt-1 text-[10px] text-muted">{{ t('season.basis', { n: info.years }) }}</p>
        </div>

        <figcaption class="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
            <span class="inline-flex items-center gap-1.5"><span class="inline-block h-0.5 w-5 bg-[#bc3754]"></span>{{ t('season.median') }}</span>
            <span class="inline-flex items-center gap-1.5"><span class="inline-block h-3 w-5 bg-[#fca50a]/30"></span>{{ t('season.range') }}</span>
            <span v-if="year" class="inline-flex items-center gap-1.5"><span class="inline-block h-0 w-5 border-t-2 border-dashed border-ink"></span>{{ t('season.year') }} {{ year }}</span>
            <span>{{ t('season.hint') }}</span>
        </figcaption>
    </figure>
</template>
