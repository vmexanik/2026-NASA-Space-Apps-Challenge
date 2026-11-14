<script setup>
// Climatology: median per calendar month, 10–90th percentile band, and one selected year.
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { compact, monthName, num } from '../format';

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
const max = computed(() => {
    const vals = [...base.value.map((b) => b.p90 ?? 0), ...yearCells.value.map((c) => c.count)];
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
</script>

<template>
    <figure>
        <svg ref="svg" :viewBox="`0 0 ${W} ${H}`" class="h-auto w-full" role="img" :aria-labelledby="'season-title season-desc'">
            <title id="season-title">{{ t('season.title') }}</title>
            <desc id="season-desc">{{ t('season.desc') }}</desc>

            <g v-for="v in ticks" :key="v">
                <line :x1="M.left" :x2="W - M.right" :y1="y(v)" :y2="y(v)" stroke="currentColor" class="text-line" />
                <text :x="M.left - 6" :y="y(v) + 4" text-anchor="end" class="fill-current text-[11px] text-muted tabular-nums">{{ compact(v) }}</text>
            </g>
            <text v-for="(m, i) in months" :key="m" :x="x(i + 1)" :y="H - 10" text-anchor="middle" class="fill-current text-[11px] text-muted">{{ m }}</text>

            <polygon :points="band" fill="#fca50a" fill-opacity="0.22" />
            <path :d="medianPath" fill="none" stroke="#bc3754" stroke-width="2.5" />
            <path v-if="yearCells.length" :d="yearPath" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="5 3" class="text-ink" />
            <g v-for="c in yearCells" :key="c.month">
                <circle :cx="x(c.month)" :cy="y(c.count)" r="4" fill="var(--wc-panel)" stroke="currentColor" stroke-width="2" class="text-ink">
                    <title>{{ c.year }}-{{ String(c.month).padStart(2, '0') }}: {{ num(c.count) }}</title>
                </circle>
            </g>
        </svg>
        <figcaption class="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
            <span class="inline-flex items-center gap-1.5"><span class="inline-block h-0.5 w-5 bg-[#bc3754]"></span>{{ t('season.median') }}</span>
            <span class="inline-flex items-center gap-1.5"><span class="inline-block h-3 w-5 bg-[#fca50a]/30"></span>{{ t('season.range') }}</span>
            <span v-if="year" class="inline-flex items-center gap-1.5"><span class="inline-block h-0 w-5 border-t-2 border-dashed border-ink"></span>{{ t('season.year') }} {{ year }}</span>
        </figcaption>
    </figure>
</template>
