<script setup>
// Quick areas and a typed bounding box: the keyboard-friendly way to set the AOI.
import { nextTick, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { api, isAdmin } from '../api';

const props = defineProps({
    modelValue: { type: Object, default: null },
    // Quick areas from /api/meta (saved by admins): [{ id, name: { en, uk }, geometry }].
    presets: { type: Array, default: () => [] },
});
const emit = defineEmits(['update:modelValue', 'preset-saved']);
const { t, locale } = useI18n();

const admin = isAdmin();
const saving = ref(false);
const saved = ref('');

// "Save as quick area": a native modal <dialog> (top layer above the map, Esc closes, focus stays inside).
const dialog = ref(null);
const nameEn = ref(null);
const draft = reactive({ en: '', uk: '', error: '' });

function openSave() {
    Object.assign(draft, { en: '', uk: '', error: '' });
    saved.value = '';
    dialog.value?.showModal();
    nextTick(() => nameEn.value?.focus());
}

async function savePreset() {
    const en = draft.en.trim();
    if (!en) {
        draft.error = t('aoi.presetNameRequired');
        nameEn.value?.focus();
        return;
    }
    saving.value = true;
    draft.error = '';
    try {
        const preset = await api.savePreset(en, props.modelValue, draft.uk.trim() || null);
        emit('preset-saved', preset);
        saved.value = t('aoi.presetSaved', { name: preset.name[locale.value] ?? en });
        dialog.value?.close();
    } catch (e) {
        draft.error = e.message || t('errors.generic');
    } finally {
        saving.value = false;
    }
}

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
                    v-for="p in presets"
                    :key="p.id"
                    type="button"
                    class="rounded-full border border-line bg-panel px-2.5 py-0.5 text-sm hover:border-accent"
                    @click="emit('update:modelValue', JSON.parse(JSON.stringify(p.geometry)))"
                >
                    {{ p.name[locale] ?? p.name.en }}
                </button>
            </div>
            <div v-if="admin && modelValue" class="mt-2">
                <button
                    type="button"
                    class="rounded-md border border-dashed border-line px-2.5 py-1 text-sm hover:border-accent disabled:opacity-60"
                    :disabled="saving"
                    @click="openSave"
                >＋ {{ t('aoi.savePreset') }}</button>
                <p v-if="saved" class="mt-1 text-xs text-muted" role="status">{{ saved }}</p>

                <dialog
                    ref="dialog"
                    class="m-auto w-[min(360px,calc(100%-2rem))] rounded-xl border border-line bg-panel p-0 text-ink shadow-xl backdrop:bg-black/40"
                    aria-labelledby="preset-dialog-title"
                    @click.self="dialog.close()"
                >
                    <form class="space-y-3 p-4" @submit.prevent="savePreset">
                        <h2 id="preset-dialog-title" class="text-base font-semibold">{{ t('aoi.savePreset') }}</h2>
                        <p class="text-xs text-muted">{{ t('aoi.presetHelp') }}</p>
                        <label class="block text-sm">
                            {{ t('aoi.presetNameEn') }}
                            <input
                                ref="nameEn"
                                v-model="draft.en"
                                type="text"
                                maxlength="80"
                                required
                                class="mt-1 w-full rounded-md border border-line bg-panel px-2 py-1.5 text-sm"
                                :aria-invalid="!!draft.error"
                                aria-describedby="preset-dialog-error"
                            />
                        </label>
                        <label class="block text-sm">
                            {{ t('aoi.presetNameUk') }} <span class="text-xs text-muted">({{ t('aoi.optional') }})</span>
                            <input v-model="draft.uk" type="text" maxlength="80" class="mt-1 w-full rounded-md border border-line bg-panel px-2 py-1.5 text-sm" />
                        </label>
                        <p v-if="draft.error" id="preset-dialog-error" class="text-sm text-red-700 dark:text-red-300" role="alert">{{ draft.error }}</p>
                        <div class="flex justify-end gap-2 pt-1">
                            <button type="button" class="rounded-md border border-line px-3 py-1.5 text-sm hover:border-accent" @click="dialog.close()">{{ t('aoi.cancel') }}</button>
                            <button type="submit" class="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-ink disabled:opacity-60" :disabled="saving">
                                {{ saving ? t('loading') : t('aoi.save') }}
                            </button>
                        </div>
                    </form>
                </dialog>
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
