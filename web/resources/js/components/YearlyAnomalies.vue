<script setup>
// Diverging bars: yearly total vs. the mean complete year. Values are printed on the bars.
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { diverging } from '../colors';
import { num, pct } from '../format';

const props = defineProps({ yearly: { type: Array, required: true } });
const emit = defineEmits(['select']);
const { t } = useI18n();
const svg = ref(null);
defineExpose({ svg });

const BAR = 22;
const W = 640;
const M = { top: 8, right: 64, bottom: 8, left: 48 };
const H = computed(() => M.top + M.bottom + props.yearly.length * BAR);
const iw = W - M.left - M.right;

const extent = computed(() => Math.max(25, ...props.yearly.map((y) => Math.abs(y.anomaly_pct ?? 0))));
const zero = M.left + iw / 2;
// Leave room for the value label at the end of the longest bar.
const xw = (p) => ((p ?? 0) / extent.value) * (iw / 2 - 48);
</script>

<template>
    <figure>
        <svg ref="svg" :viewBox="`0 0 ${W} ${H}`" class="h-auto w-full" role="img" :aria-label="t('anomalies.title')">
            <line :x1="zero" :x2="zero" :y1="M.top" :y2="H - M.bottom" stroke="currentColor" class="text-muted" />
            <g
                v-for="(y, i) in yearly"
                :key="y.year"
                class="cursor-pointer"
                @click="emit('select', y.year)"
            >
                <title>{{ y.year }}: {{ num(y.count) }} ({{ y.complete ? pct(y.anomaly_pct) : t('anomalies.incomplete') }})</title>
                <text :x="M.left - 8" :y="M.top + i * BAR + BAR / 2 + 4" text-anchor="end" class="fill-current text-[12px] tabular-nums">{{ y.year }}</text>
                <rect
                    v-if="y.complete && y.anomaly_pct !== null"
                    :x="y.anomaly_pct >= 0 ? zero : zero + xw(y.anomaly_pct)"
                    :y="M.top + i * BAR + 3"
                    :width="Math.max(1, Math.abs(xw(y.anomaly_pct)))"
                    :height="BAR - 6"
                    rx="2"
                    :fill="diverging(y.anomaly_pct)"
                    stroke="currentColor"
                    stroke-opacity="0.25"
                />
                <text
                    :x="y.complete && y.anomaly_pct !== null ? (y.anomaly_pct >= 0 ? zero + xw(y.anomaly_pct) + 6 : zero + xw(y.anomaly_pct) - 6) : zero + 6"
                    :y="M.top + i * BAR + BAR / 2 + 4"
                    :text-anchor="y.complete && y.anomaly_pct < 0 ? 'end' : 'start'"
                    class="fill-current text-[11px] tabular-nums text-muted"
                >{{ y.complete ? pct(y.anomaly_pct) : t('anomalies.incomplete') }}</text>
            </g>
        </svg>
    </figure>
</template>
