<script setup>
// Quick areas and a typed bounding box: the keyboard-friendly way to set the AOI.
import { reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps({ modelValue: { type: Object, default: null } });
const emit = defineEmits(['update:modelValue']);
const { t } = useI18n();

const PRESETS = [
    { name: 'Kyiv region', bbox: [29.2, 49.2, 32.2, 51.6] },
    { name: 'Ukraine', bbox: [22.1, 44.3, 40.2, 52.4] },
    { name: 'California', bbox: [-124.5, 32.5, -114.1, 42.0] },
    { name: 'Rondônia, BR', bbox: [-66.8, -13.7, -59.8, -7.9] },
    { name: 'New South Wales', bbox: [141.0, -37.5, 153.6, -28.2] },
];

const box = reactive({ west: null, south: null, east: null, north: null });
const error = ref('');

const round = (v) => Math.round(v * 1e4) / 1e4;
const bboxPolygon = ([w, s, e, n]) => ({ type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] });

watch(
    () => props.modelValue,
    (v) => {
        const r = v?.coordinates?.[0] ?? [];
        if (!r.length) return;
        box.west = round(Math.min(...r.map((p) => p[0])));
        box.east = round(Math.max(...r.map((p) => p[0])));
        box.south = round(Math.min(...r.map((p) => p[1])));
        box.north = round(Math.max(...r.map((p) => p[1])));
    },
    { immediate: true, deep: true },
);

function apply() {
    const vals = [box.west, box.south, box.east, box.north];
    if (vals.some((v) => v === null || v === '' || Number.isNaN(Number(v)))) {
        error.value = t('aoi.errorMissing');
        return;
    }
    const [w, s, e, n] = vals.map(Number);
    if (w < -180 || e > 180 || s < -90 || n > 90 || w >= e || s >= n) {
        error.value = t('aoi.errorRange');
        return;
    }
    error.value = '';
    emit('update:modelValue', bboxPolygon([w, s, e, n]));
}
</script>

<template>
    <div class="space-y-3">
        <div>
            <p class="mb-1 text-xs font-medium tracking-wide text-muted uppercase">{{ t('aoi.presets') }}</p>
            <div class="flex flex-wrap gap-1.5">
                <button
                    v-for="p in PRESETS"
                    :key="p.name"
                    type="button"
                    class="rounded-full border border-line bg-panel px-2.5 py-0.5 text-sm hover:border-accent"
                    @click="emit('update:modelValue', bboxPolygon(p.bbox))"
                >
                    {{ p.name }}
                </button>
            </div>
        </div>

        <details class="group">
            <summary class="cursor-pointer text-sm font-medium select-none">{{ t('aoi.coords') }}</summary>
            <form class="mt-2 space-y-2" @submit.prevent="apply">
                <div class="grid grid-cols-4 gap-1.5">
                    <label v-for="k in ['west', 'south', 'east', 'north']" :key="k" class="text-xs text-muted">
                        {{ t('aoi.' + k) }}
                        <input
                            v-model.number="box[k]"
                            type="number"
                            step="0.0001"
                            inputmode="decimal"
                            class="mt-0.5 w-full rounded-md border border-line bg-panel px-1.5 py-1 text-sm text-ink tabular-nums"
                        />
                    </label>
                </div>
                <button type="submit" class="rounded-md border border-line px-3 py-1 text-sm hover:border-accent">{{ t('aoi.apply') }}</button>
                <p v-if="error" class="text-sm text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
            </form>
        </details>
    </div>
</template>
