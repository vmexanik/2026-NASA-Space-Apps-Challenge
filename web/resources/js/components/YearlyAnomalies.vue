<script setup>
// Fires per year: bar length is the harmonized total (with its error), colour is the difference
// from the average complete year, the dashed line is that average. Hover / focus a year for its numbers,
// click to show it in the seasonal profile. The read-out is HTML over the SVG, so exports stay clean.
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { diverging } from '../colors';
import { compact, num, pct } from '../format';

const props = defineProps({
    yearly: { type: Array, required: true },
    mean: { type: Number, default: null }, // average complete year
    selected: { type: Number, default: null },
});
const emit = defineEmits(['select']);
const { t } = useI18n();
const svg = ref(null);
defineExpose({ svg });

const BAR = 22;
const W = 640;
const M = { top: 8, right: 120, bottom: 8, left: 48 };
const H = computed(() => M.top + M.bottom + props.yearly.length * BAR);
const iw = W - M.left - M.right;

const max = computed(() => Math.max(1, props.mean ?? 0, ...props.yearly.map((y) => y.count + (y.count_error ?? 0))));
const xw = (v) => ((v ?? 0) / max.value) * iw;
const rowY = (i) => M.top + i * BAR;

const active = ref(null); // index of the hovered / focused year
const info = computed(() => (active.value === null ? null : props.yearly[active.value]));
// Below the row in the upper half of the list, above it in the lower half, so it stays on screen.
const tipStyle = computed(() => {
    if (active.value === null) return {};
    return active.value < props.yearly.length / 2
        ? { top: `${((rowY(active.value) + BAR) / H.value) * 100}%` }
        : { bottom: `${((H.value - rowY(active.value)) / H.value) * 100}%` };
});

function focusRow(i) {
    active.value = Math.min(props.yearly.length - 1, Math.max(0, i));
    svg.value?.querySelector(`[data-row="${active.value}"]`)?.focus();
}
function onKey(e, i) {
    const moves = { ArrowUp: -1, ArrowDown: 1, Home: -i, End: props.yearly.length };
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        emit('select', props.yearly[i].year);
        return;
    }
    if (!(e.key in moves)) return;
    e.preventDefault();
    focusRow(i + moves[e.key]);
}
const sourceLabel = (s) => ({ modis: t('calendar.modis'), viirs: t('calendar.viirs'), mixed: 'MODIS → VIIRS' })[s] ?? '';
</script>

<template>
    <figure class="relative">
        <svg
            ref="svg"
            :viewBox="`0 0 ${W} ${H}`"
            class="h-auto w-full"
            role="list"
            :aria-label="t('anomalies.title')"
            @mouseleave="active = null"
        >
            <!-- average year -->
            <g v-if="mean">
                <line :x1="M.left + xw(mean)" :x2="M.left + xw(mean)" :y1="M.top" :y2="H - M.bottom" stroke="currentColor" stroke-dasharray="4 3" class="text-muted" />
            </g>

            <g
                v-for="(y, i) in yearly"
                :key="y.year"
                role="listitem"
                tabindex="0"
                :data-row="i"
                :aria-label="`${y.year}: ${num(y.count)}${y.count_error ? ' ± ' + num(y.count_error) : ''}, ${y.complete ? pct(y.anomaly_pct) : t('anomalies.incomplete')}`"
                class="cursor-pointer outline-none [&:focus-visible>rect.frame]:stroke-[2]"
                @mouseenter="active = i"
                @focus="active = i"
                @blur="active = null"
                @click="emit('select', y.year)"
                @keydown="onKey($event, i)"
            >
                <!-- whole row is the hover target -->
                <rect class="frame" :x="0" :y="rowY(i)" :width="W" :height="BAR" :fill="active === i || selected === y.year ? 'var(--wc-line)' : 'transparent'" fill-opacity="0.6" stroke="var(--wc-ink)" stroke-width="0" />
                <text :x="M.left - 8" :y="rowY(i) + BAR / 2 + 4" text-anchor="end" class="fill-current text-[12px] tabular-nums" :class="{ 'font-semibold': selected === y.year }">{{ y.year }}</text>
                <rect
                    :x="M.left"
                    :y="rowY(i) + 4"
                    :width="Math.max(1, xw(y.count))"
                    :height="BAR - 8"
                    rx="2"
                    :fill="y.complete && y.anomaly_pct !== null ? diverging(y.anomaly_pct) : 'var(--wc-zero)'"
                    stroke="currentColor"
                    stroke-opacity="0.25"
                    :stroke-dasharray="y.complete ? null : '3 2'"
                />
                <line
                    v-if="y.count_error"
                    :x1="M.left + xw(Math.max(0, y.count - y.count_error))"
                    :x2="M.left + xw(y.count + y.count_error)"
                    :y1="rowY(i) + BAR / 2"
                    :y2="rowY(i) + BAR / 2"
                    stroke="currentColor"
                    stroke-width="1.5"
                    class="text-ink"
                    stroke-opacity="0.6"
                />
                <text :x="M.left + xw(y.count + (y.count_error ?? 0)) + 6" :y="rowY(i) + BAR / 2 + 4" class="fill-current text-[11px] tabular-nums">
                    {{ compact(y.count) }}
                    <tspan class="text-muted" fill-opacity="0.7">{{ y.complete ? pct(y.anomaly_pct) : t('anomalies.incomplete') }}</tspan>
                </text>
            </g>
        </svg>

        <div
            v-if="info"
            class="pointer-events-none absolute right-2 z-10 w-56 rounded-md border border-line bg-panel/95 p-2 text-xs shadow-lg backdrop-blur"
            :style="tipStyle"
            role="status"
            aria-live="polite"
        >
            <p class="mb-1 text-sm font-semibold">{{ info.year }}<span v-if="!info.complete" class="font-normal text-muted"> · {{ t('anomalies.incomplete') }}</span></p>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 tabular-nums">
                <dt class="text-muted">{{ t('anomalies.fires') }}</dt>
                <dd class="text-right font-semibold">{{ num(info.count) }}<span v-if="info.count_error" class="font-normal text-muted"> ± {{ num(info.count_error) }}</span></dd>
                <dt class="text-muted">{{ t('anomalies.vsMean') }}</dt>
                <dd class="text-right">{{ info.complete ? pct(info.anomaly_pct) : '—' }}</dd>
                <dt class="text-muted">{{ t('anomalies.mean') }}</dt>
                <dd class="text-right">{{ num(mean) }}</dd>
                <dt class="text-muted">{{ t('anomalies.detections') }}</dt>
                <dd class="text-right">{{ num(info.count_raw) }}</dd>
            </dl>
            <p class="mt-1 text-muted">{{ sourceLabel(info.source) }}<template v-if="info.incomplete"> · {{ t('calendar.incomplete') }}</template></p>
            <p class="mt-1 text-[10px] text-muted">{{ t('anomalies.clickHint') }}</p>
        </div>

        <figcaption class="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted">
            <span class="inline-flex items-center gap-1.5"><span class="inline-block h-0 w-5 border-t-2 border-dashed border-muted"></span>{{ t('anomalies.mean') }}</span>
            <span class="inline-flex items-center gap-1.5"><span class="inline-block h-0.5 w-5 bg-ink/60"></span>{{ t('anomalies.errorBar') }}</span>
            <span>{{ t('anomalies.colorHint') }}</span>
        </figcaption>
    </figure>
</template>
