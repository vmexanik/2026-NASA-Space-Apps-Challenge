<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { api, ApiError } from './api';
import { setLocale } from './i18n';
import { compact, date, monthName, monthYear, num, pct } from './format';
import { downloadCsv, downloadPng, downloadSvg } from './exporters';
import AoiMap from './components/AoiMap.vue';
import AoiForm from './components/AoiForm.vue';
import CalendarHeatmap from './components/CalendarHeatmap.vue';
import SeasonalChart from './components/SeasonalChart.vue';
import YearlyAnomalies from './components/YearlyAnomalies.vue';

const { t, locale } = useI18n();

const meta = ref(null);
const aoi = ref(null);
const dateFrom = ref('');
const dateTo = ref('');

const calendar = ref(null);
const summary = ref(null);
const loading = ref(false);
const error = ref('');
const notice = ref('');
const mode = ref('counts');
const selectedYear = ref(null);

const mapRef = ref(null);
const heatmap = ref(null);
const season = ref(null);
const anomalies = ref(null);

// --- layout -------------------------------------------------------------------------
const wide = ref(window.innerWidth >= 1024);
const controlsOpen = ref(wide.value);
const onResize = () => (wide.value = window.innerWidth >= 1024);
// Space covered by the floating panels, so the map keeps the AOI in the visible middle.
const insets = computed(() => (wide.value ? [controlsOpen.value ? 344 : 0, aoi.value ? 424 : 0] : [0, 0]));

function scrollToResults() {
    document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' });
}

// Every way to remove the shape (panel button, ×, trash on the map) asks first, inline:
// the map shows a red "Delete area" next to the trash button and the left panel one under its button.
// Clicking any delete control again (or Esc) backs out.
const confirmingDelete = ref(false);
function askDelete() {
    confirmingDelete.value = true;
}
function toggleDelete() {
    confirmingDelete.value = !confirmingDelete.value;
}
function cancelDelete() {
    confirmingDelete.value = false;
}
function clearAoi() {
    confirmingDelete.value = false;
    aoi.value = null;
}
watch(aoi, () => (confirmingDelete.value = false));

// --- data ---------------------------------------------------------------------------
const query = () => ({ aoi: aoi.value, date_from: dateFrom.value || null, date_to: dateTo.value || null });
let requestId = 0;

async function run() {
    if (!aoi.value) return;
    const id = ++requestId;
    loading.value = true;
    error.value = '';
    notice.value = '';
    try {
        const [c, s] = await Promise.all([api.calendar(query()), api.summary(query())]);
        if (id !== requestId) return; // a newer request is on its way
        calendar.value = c;
        summary.value = s;
        selectedYear.value = c.years[c.years.length - 1] ?? null;
    } catch (e) {
        if (id !== requestId) return;
        calendar.value = null;
        summary.value = null;
        error.value = e instanceof ApiError && Object.keys(e.errors).length ? Object.values(e.errors).flat().join(' ') : e.message || t('errors.generic');
    } finally {
        if (id === requestId) loading.value = false;
    }
}

function preset(years) {
    if (!meta.value) return;
    dateTo.value = meta.value.data.to;
    dateFrom.value = years ? `${Number(meta.value.data.to.slice(0, 4)) - years + 1}-01-01` : meta.value.data.from;
    run();
}

// A new AOI (drawn, typed or preset) re-runs the query right away.
watch(
    aoi,
    (value) => {
        if (value) {
            if (!wide.value) controlsOpen.value = false; // phones: show the map and the stats
            return run();
        }
        requestId++;
        calendar.value = null;
        summary.value = null;
        error.value = '';
        loading.value = false;
    },
    { deep: true },
);

onMounted(async () => {
    document.documentElement.lang = locale.value;
    window.addEventListener('resize', onResize);
    try {
        meta.value = await api.meta();
        dateFrom.value = meta.value.data.from;
        dateTo.value = meta.value.data.to;
    } catch {
        error.value = t('errors.generic');
    }
});
onBeforeUnmount(() => window.removeEventListener('resize', onResize));

async function draw(kind) {
    if (!wide.value) controlsOpen.value = false; // free the map on phones
    await nextTick();
    mapRef.value?.startDraw(kind);
}

// --- derived ------------------------------------------------------------------------
const current = computed(() => summary.value?.current_month);
const statusStyle = {
    above: 'bg-[#e08214] text-[#1d1b19]',
    normal: 'bg-[#d8daeb] text-[#1d1b19]',
    below: 'bg-[#542788] text-white',
    unknown: 'bg-line text-ink',
};
const statusIcon = { above: '▲', normal: '●', below: '▼', unknown: '?' };
const trendText = computed(() => {
    const tr = summary.value?.trend;
    if (!tr) return t('kpi.trendNone');
    return `${t('kpi.' + tr.direction)} · ${t('kpi.trendValue', { pct: pct(tr.pct_per_decade) })}`;
});
const fireSeason = computed(() => (summary.value?.fire_season ?? []).map((m) => monthName(m)).join(', '));
const tooLarge = computed(() => summary.value && meta.value && summary.value.totals.hotspots_raw > meta.value.limits.csv_export_max_rows);

// --- exports ------------------------------------------------------------------------
const exporting = ref(false);
async function exportHotspots() {
    exporting.value = true;
    notice.value = '';
    try {
        const r = await api.exportCsv(query());
        notice.value = r.truncated ? t('export.truncated', { max: num(r.max) }) : t('export.done');
    } catch (e) {
        error.value = e.message || t('errors.generic');
    } finally {
        exporting.value = false;
    }
}

function exportCalendarTable() {
    const rows = [['year', 'month', 'hotspots_harmonized', 'detections_raw', 'source', 'partial', 'anomaly_vs_mean', 'anomaly_pct', 'z_score']];
    for (const c of calendar.value.cells) rows.push([c.year, c.month, c.count, c.count_raw, c.source, c.partial, c.anomaly, c.anomaly_pct, c.z]);
    downloadCsv(rows, `calendar_${calendar.value.range.from}_${calendar.value.range.to}`);
}

function exportRankings() {
    const s = summary.value;
    const rows = [['section', 'year', 'month', 'hotspots', 'extra']];
    s.top_months.forEach((m) => rows.push(['top_month', m.year, m.month, m.count, m.source]));
    s.top_years.forEach((y) => rows.push(['top_year', y.year, '', y.count, y.complete ? 'complete' : 'incomplete']));
    s.yearly.forEach((y) => rows.push(['yearly_anomaly_pct', y.year, '', y.count, y.anomaly_pct]));
    calendar.value.baseline.by_month.forEach((b) => rows.push(['baseline_month', '', b.month, b.median, `mean=${b.mean};p10=${b.p10};p90=${b.p90}`]));
    downloadCsv(rows, `analytics_${s.range.from}_${s.range.to}`);
}

const fname = (name) => `${name}_${calendar.value.range.from}_${calendar.value.range.to}`;

const chip = 'rounded-full border border-line px-2.5 py-0.5 text-sm hover:border-accent';
const btn = 'rounded-md border border-line px-2.5 py-1 text-sm hover:border-accent';
</script>

<template>
    <div class="min-h-screen">
        <!-- Header -->
        <header class="flex h-14 items-center justify-between gap-3 border-b border-line bg-panel px-4">
            <div class="flex min-w-0 items-center gap-2.5">
                <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true" class="shrink-0">
                    <rect width="32" height="32" rx="7" fill="#bc3754" />
                    <path d="M16 6c1 4 6 6 6 12a6 6 0 0 1-12 0c0-3 2-5 3-6 0 2 1 3 2 3 0-4-1-6 1-9z" fill="#fcffa4" />
                </svg>
                <div class="min-w-0">
                    <h1 class="truncate text-base leading-tight font-semibold">{{ t('app.title') }}</h1>
                    <p class="hidden truncate text-xs text-muted sm:block">{{ t('app.subtitle') }}</p>
                </div>
                <span v-if="meta?.demo" class="ml-1 hidden shrink-0 rounded-full bg-warn px-2 py-0.5 text-xs md:inline" :title="t('app.demo')">⚠ Demo data</span>
            </div>
            <div class="flex shrink-0 items-center gap-3">
                <a href="#method" class="hidden text-sm underline decoration-line underline-offset-4 hover:decoration-accent sm:inline">{{ t('method.title') }}</a>
                <div role="group" :aria-label="t('app.language')" class="flex overflow-hidden rounded-md border border-line text-sm">
                    <button
                        v-for="l in ['en', 'uk']"
                        :key="l"
                        type="button"
                        class="px-2.5 py-1"
                        :class="locale === l ? 'bg-ink text-page' : 'hover:bg-line'"
                        :aria-pressed="locale === l"
                        @click="setLocale(l)"
                    >
                        {{ l === 'en' ? 'EN' : 'UA' }}
                    </button>
                </div>
            </div>
        </header>

        <!-- Map stage: full viewport on desktop -->
        <section class="lg:relative lg:h-[calc(100svh-3.5rem)]">
            <div class="relative h-[70svh] lg:h-full" :class="{ 'panel-open': aoi }">
                <AoiMap
                    ref="mapRef"
                    v-model="aoi"
                    :insets="insets"
                    :confirm-delete="confirmingDelete"
                    @delete="askDelete"
                    @delete-confirm="clearAoi"
                    @delete-cancel="cancelDelete"
                    class="absolute inset-0 z-0" />

                <!-- Controls (left) -->
                <div class="absolute top-3 left-3 z-[500] w-[min(320px,calc(100%-4.5rem))] rounded-xl border border-line bg-panel/95 shadow-lg backdrop-blur">
                    <button
                        type="button"
                        class="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left font-semibold"
                        :aria-expanded="controlsOpen"
                        aria-controls="controls-body"
                        @click="controlsOpen = !controlsOpen"
                    >
                        <span>{{ t('aoi.controls') }}</span>
                        <span aria-hidden="true" class="text-muted transition-transform" :class="controlsOpen ? 'rotate-180' : ''">▾</span>
                    </button>

                    <div v-show="controlsOpen" id="controls-body" class="max-h-[calc(70svh-5rem)] space-y-4 overflow-y-auto border-t border-line px-4 pt-3 pb-4 lg:max-h-[calc(100svh-9rem)]">
                        <p v-if="!aoi" class="text-sm text-muted">{{ t('aoi.empty') }}</p>

                        <div v-if="aoi" class="space-y-1.5">
                            <button type="button" class="inline-flex w-full items-center justify-center gap-2 rounded-md border border-red-700 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 dark:border-red-300 dark:text-red-300 dark:hover:bg-red-950" :aria-expanded="confirmingDelete" @click="toggleDelete">
                                <svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6h12M8 6V4h4v2m-6 0 1 10h6l1-10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" /></svg>
                                {{ t('aoi.delete') }}
                            </button>
                            <button v-if="confirmingDelete" type="button" class="w-full rounded-md bg-red-700 px-3 py-2 text-sm font-semibold text-white hover:bg-red-800 dark:bg-red-400 dark:text-red-950" @click="clearAoi" @keydown.esc="cancelDelete">
                                {{ t('aoi.deleteYes') }}
                            </button>
                            <p class="text-xs text-muted">{{ t('aoi.oneShape') }}</p>
                        </div>
                        <div v-else class="flex gap-2">
                            <button type="button" class="inline-flex flex-1 items-center justify-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-ink" @click="draw('rectangle')">
                                <svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="5" width="14" height="10" rx="1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-dasharray="3 2" /></svg>
                                {{ t('aoi.draw') }}
                            </button>
                            <button type="button" :class="btn" :title="t('aoi.drawPolygon')" @click="draw('polygon')">
                                <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2 18 8l-3 9H5L2 8z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" /></svg>
                                <span class="sr-only">{{ t('aoi.drawPolygon') }}</span>
                            </button>
                        </div>

                        <AoiForm v-model="aoi" />

                        <form class="space-y-2 border-t border-line pt-3" @submit.prevent="run">
                            <p class="text-xs font-medium tracking-wide text-muted uppercase">{{ t('dates.title') }}</p>
                            <div class="grid grid-cols-2 gap-2">
                                <label class="text-xs text-muted">
                                    {{ t('dates.from') }}
                                    <input v-model="dateFrom" type="date" :min="meta?.data.from" :max="meta?.data.to" class="mt-0.5 w-full rounded-md border border-line bg-panel px-1.5 py-1 text-sm text-ink" />
                                </label>
                                <label class="text-xs text-muted">
                                    {{ t('dates.to') }}
                                    <input v-model="dateTo" type="date" :min="meta?.data.from" :max="meta?.data.to" class="mt-0.5 w-full rounded-md border border-line bg-panel px-1.5 py-1 text-sm text-ink" />
                                </label>
                            </div>
                            <div class="flex flex-wrap gap-1.5">
                                <button type="button" :class="chip" @click="preset(0)">{{ t('dates.all') }}</button>
                                <button type="button" :class="chip" @click="preset(10)">{{ t('dates.last10') }}</button>
                                <button type="button" :class="chip" @click="preset(5)">{{ t('dates.last5') }}</button>
                            </div>
                            <button type="submit" class="w-full rounded-md border border-ink px-3 py-1.5 text-sm font-medium disabled:opacity-50" :disabled="loading || !aoi">
                                {{ loading ? t('loading') : t('run') }}
                            </button>
                        </form>
                    </div>
                </div>
            </div>

            <!-- Statistics (right on desktop, under the map on phones) -->
            <aside
                v-if="aoi"
                class="z-[500] border-b border-line bg-panel p-4 lg:absolute lg:top-3 lg:right-3 lg:bottom-3 lg:w-[400px] lg:overflow-y-auto lg:rounded-xl lg:border lg:bg-panel/95 lg:shadow-lg lg:backdrop-blur"
                aria-labelledby="panel-title"
                :aria-busy="loading"
            >
                <div class="mb-3 flex items-start justify-between gap-2">
                    <div>
                        <h2 id="panel-title" class="text-base font-semibold">{{ t('panel.title') }}</h2>
                        <p v-if="summary" class="text-xs text-muted">
                            {{ t('aoi.area', { area: num(summary.aoi.area_km2) }) }} · {{ date(summary.range.from) }} – {{ date(summary.range.to) }}
                        </p>
                    </div>
                    <button type="button" class="rounded-md px-2 py-0.5 text-lg leading-none text-muted hover:bg-line hover:text-ink" :aria-label="t('panel.close')" :title="t('panel.close')" @click="toggleDelete">×</button>
                </div>

                <p v-if="error" class="rounded-md bg-red-50 p-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200" role="alert">{{ error }}</p>
                <div v-else-if="loading && !summary" class="space-y-3" aria-hidden="true">
                    <div v-for="i in 4" :key="i" class="h-16 animate-pulse rounded-lg bg-line"></div>
                </div>

                <div v-if="summary" class="space-y-3" :class="{ 'opacity-60 transition-opacity': loading }">
                    <!-- KPIs -->
                    <div class="grid grid-cols-2 gap-2">
                        <div class="rounded-lg border border-line p-3">
                            <p class="text-xs text-muted">{{ t('kpi.total') }}</p>
                            <p class="text-xl font-semibold tabular-nums">{{ num(summary.totals.hotspots) }}</p>
                        </div>
                        <div class="rounded-lg border border-line p-3">
                            <p class="text-xs text-muted">{{ t('kpi.perYear') }}</p>
                            <p class="text-xl font-semibold tabular-nums">{{ num(summary.totals.mean_per_year) }}</p>
                        </div>
                        <div class="rounded-lg border border-line p-3">
                            <p class="text-xs text-muted">{{ t('kpi.peakMonth') }}</p>
                            <p class="text-sm font-semibold">
                                <template v-if="summary.totals.peak_month">{{ monthYear(summary.totals.peak_month.year, summary.totals.peak_month.month) }}</template>
                                <template v-else>—</template>
                            </p>
                            <p class="text-xs text-muted tabular-nums">{{ num(summary.totals.peak_month?.count) }}</p>
                        </div>
                        <div class="rounded-lg border border-line p-3">
                            <p class="text-xs text-muted">{{ t('kpi.trend') }}</p>
                            <p class="text-sm font-semibold">{{ summary.trend ? { up: '↗', down: '↘', flat: '→' }[summary.trend.direction] : '' }} {{ trendText }}</p>
                        </div>
                    </div>

                    <!-- Current month vs median -->
                    <div v-if="current" class="rounded-lg border border-line p-3">
                        <div class="flex items-start justify-between gap-2">
                            <p class="text-xs text-muted">{{ t('current.title') }} · {{ monthYear(current.year, current.month) }}</p>
                            <span class="inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold" :class="statusStyle[current.status]">
                                <span aria-hidden="true">{{ statusIcon[current.status] }}</span>{{ t('current.status.' + current.status) }}
                            </span>
                        </div>
                        <p class="mt-1 text-lg font-semibold tabular-nums">
                            {{ current.partial ? t('current.soFar', { count: num(current.count), days: current.days_elapsed, total: current.days_in_month }) : t('current.full', { count: num(current.count) }) }}
                        </p>
                        <p class="text-sm text-muted">
                            {{ current.partial
                                ? t('current.median', { month: monthName(current.month, 'long'), median: num(current.median_to_date) })
                                : t('current.medianFull', { month: monthName(current.month, 'long'), years: current.baseline_years, median: num(current.median) }) }}
                            <template v-if="current.ratio !== null"> · {{ t('current.ratio', { ratio: num(current.ratio, 2) }) }}</template>
                        </p>
                    </div>

                    <!-- Season + top months -->
                    <div class="rounded-lg border border-line p-3">
                        <p v-if="fireSeason" class="text-sm">🔥 {{ t('season.fireSeason', { months: fireSeason }) }}</p>
                        <p class="mt-2 text-xs text-muted">{{ t('panel.top') }}</p>
                        <ol class="mt-1 space-y-0.5 text-sm">
                            <li v-for="(m, i) in summary.top_months.slice(0, 5)" :key="`${m.year}-${m.month}`" class="flex justify-between gap-2">
                                <span><span class="text-muted tabular-nums">{{ i + 1 }}.</span> {{ monthYear(m.year, m.month) }}</span>
                                <span class="font-medium tabular-nums">{{ num(m.count) }}</span>
                            </li>
                        </ol>
                    </div>

                    <div class="flex flex-wrap gap-2">
                        <button type="button" class="flex-1 rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-ink" @click="scrollToResults">↓ {{ t('panel.more') }}</button>
                        <button type="button" :class="btn" :disabled="exporting" @click="exportHotspots">⬇ CSV</button>
                    </div>
                    <p v-if="notice" class="text-xs text-muted" role="status">{{ notice }}</p>
                </div>
            </aside>
        </section>

        <!-- Everything else below the map -->
        <div id="results" class="mx-auto max-w-7xl scroll-mt-4 space-y-6 px-4 py-8">
            <template v-if="calendar && summary">
                <!-- Calendar -->
                <section class="rounded-xl border border-line bg-panel p-4" aria-labelledby="cal-title">
                    <div class="mb-3 flex flex-wrap items-start justify-between gap-3">
                        <div class="max-w-2xl">
                            <h2 id="cal-title" class="text-base font-semibold">{{ t('calendar.title') }}</h2>
                            <p class="text-sm text-muted">{{ t('calendar.desc') }}</p>
                        </div>
                        <div class="flex flex-wrap items-center gap-2">
                            <div role="group" class="flex overflow-hidden rounded-md border border-line text-sm">
                                <button type="button" class="px-3 py-1" :class="mode === 'counts' ? 'bg-ink text-page' : 'hover:bg-line'" :aria-pressed="mode === 'counts'" @click="mode = 'counts'">{{ t('calendar.modeCounts') }}</button>
                                <button type="button" class="px-3 py-1" :class="mode === 'anomaly' ? 'bg-ink text-page' : 'hover:bg-line'" :aria-pressed="mode === 'anomaly'" @click="mode = 'anomaly'">{{ t('calendar.modeAnomaly') }}</button>
                            </div>
                            <button type="button" :class="btn" @click="downloadPng(heatmap.svg, fname('calendar'))">{{ t('export.png') }}</button>
                            <button type="button" :class="btn" @click="downloadSvg(heatmap.svg, fname('calendar'))">{{ t('export.svg') }}</button>
                        </div>
                    </div>
                    <CalendarHeatmap ref="heatmap" :data="calendar" :mode="mode" @select="selectedYear = $event" />
                </section>

                <div class="grid gap-6 xl:grid-cols-2">
                    <!-- Seasonal profile -->
                    <section class="rounded-xl border border-line bg-panel p-4" aria-labelledby="season-h">
                        <div class="mb-2 flex flex-wrap items-start justify-between gap-2">
                            <div>
                                <h2 id="season-h" class="text-base font-semibold">{{ t('season.title') }}</h2>
                                <p class="text-sm text-muted">{{ t('season.desc') }}</p>
                            </div>
                            <div class="flex items-center gap-2">
                                <label class="text-sm">
                                    <span class="sr-only">{{ t('season.year') }}</span>
                                    <select v-model.number="selectedYear" class="rounded-md border border-line bg-panel px-2 py-1 text-sm">
                                        <option v-for="y in calendar.years" :key="y" :value="y">{{ y }}</option>
                                    </select>
                                </label>
                                <button type="button" :class="btn" @click="downloadPng(season.svg, fname('seasonal'))">{{ t('export.png') }}</button>
                            </div>
                        </div>
                        <SeasonalChart ref="season" :calendar="calendar" :year="selectedYear" />
                    </section>

                    <!-- Yearly anomalies -->
                    <section class="rounded-xl border border-line bg-panel p-4" aria-labelledby="anom-h">
                        <div class="mb-2 flex flex-wrap items-start justify-between gap-2">
                            <div>
                                <h2 id="anom-h" class="text-base font-semibold">{{ t('anomalies.title') }}</h2>
                                <p class="text-sm text-muted">{{ t('anomalies.desc') }}</p>
                            </div>
                            <button type="button" :class="btn" @click="downloadPng(anomalies.svg, fname('anomalies'))">{{ t('export.png') }}</button>
                        </div>
                        <YearlyAnomalies ref="anomalies" :yearly="summary.yearly" @select="selectedYear = $event" />
                    </section>
                </div>

                <!-- Rankings -->
                <div class="grid gap-6 md:grid-cols-2">
                    <section class="rounded-xl border border-line bg-panel p-4">
                        <h2 class="mb-2 text-base font-semibold">{{ t('rank.months') }}</h2>
                        <table class="w-full text-sm">
                            <thead class="text-left text-xs text-muted">
                                <tr><th class="py-1 font-medium">#</th><th class="font-medium">{{ t('rank.month') }}</th><th class="text-right font-medium">{{ t('rank.count') }}</th><th class="text-right font-medium">{{ t('rank.source') }}</th></tr>
                            </thead>
                            <tbody>
                                <tr v-for="(m, i) in summary.top_months" :key="`${m.year}-${m.month}`" class="border-t border-line">
                                    <td class="py-1.5 text-muted tabular-nums">{{ i + 1 }}</td>
                                    <td>{{ monthYear(m.year, m.month) }}</td>
                                    <td class="text-right font-medium tabular-nums">{{ num(m.count) }}</td>
                                    <td class="text-right text-xs text-muted">{{ m.source === 'modis' ? 'MODIS*' : 'VIIRS' }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </section>
                    <section class="rounded-xl border border-line bg-panel p-4">
                        <h2 class="mb-2 text-base font-semibold">{{ t('rank.years') }}</h2>
                        <table class="w-full text-sm">
                            <thead class="text-left text-xs text-muted">
                                <tr><th class="py-1 font-medium">#</th><th class="font-medium">{{ t('rank.year') }}</th><th class="text-right font-medium">{{ t('rank.count') }}</th><th></th></tr>
                            </thead>
                            <tbody>
                                <tr v-for="(y, i) in summary.top_years" :key="y.year" class="border-t border-line">
                                    <td class="py-1.5 text-muted tabular-nums">{{ i + 1 }}</td>
                                    <td>{{ y.year }}</td>
                                    <td class="text-right font-medium tabular-nums">{{ num(y.count) }}</td>
                                    <td class="text-right text-xs text-muted">{{ y.complete ? '' : t('anomalies.incomplete') }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </section>
                </div>

                <!-- Downloads -->
                <section class="rounded-xl border border-line bg-panel p-4" aria-labelledby="dl-h">
                    <h2 id="dl-h" class="mb-2 text-base font-semibold">{{ t('export.title') }}</h2>
                    <div class="flex flex-wrap gap-2">
                        <button type="button" class="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-ink disabled:opacity-60" :disabled="exporting" @click="exportHotspots">
                            ⬇ {{ exporting ? t('loading') : t('export.csv') }}
                            <span class="opacity-80">(~{{ compact(Math.min(summary.totals.hotspots_raw, meta?.limits.csv_export_max_rows ?? Infinity)) }})</span>
                        </button>
                        <button type="button" class="rounded-md border border-line px-3 py-2 text-sm hover:border-accent" @click="exportCalendarTable">⬇ {{ t('export.calendarCsv') }}</button>
                        <button type="button" class="rounded-md border border-line px-3 py-2 text-sm hover:border-accent" @click="exportRankings">⬇ {{ t('export.summaryCsv') }}</button>
                    </div>
                    <p v-if="tooLarge" class="mt-2 rounded-md bg-warn p-2 text-sm">{{ t('export.tooMany', { expected: num(summary.totals.hotspots_raw), max: num(meta.limits.csv_export_max_rows) }) }}</p>
                    <p v-if="notice" class="mt-2 text-sm text-muted" role="status">{{ notice }}</p>
                </section>
            </template>

            <p v-else-if="!aoi" class="text-muted">{{ t('aoi.empty') }}</p>

            <!-- Methodology -->
            <section id="method" class="rounded-xl border border-line bg-panel p-4 text-sm leading-relaxed" aria-labelledby="method-h">
                <h2 id="method-h" class="mb-2 text-base font-semibold">{{ t('method.title') }}</h2>
                <p v-if="meta?.demo" class="mb-2 rounded-md bg-warn p-2">⚠ {{ t('app.demo') }}</p>
                <template v-if="meta">
                    <p class="mb-2">{{ t('method.p1') }}</p>
                    <p class="mb-2">{{ t('method.p2', { grid: meta.method.grid_step }) }}</p>
                    <p class="mb-2">{{ t('method.p3', { modis: meta.method.modis_min_confidence, viirs: meta.method.viirs_confidence_levels.join(', '), version: meta.method.version }) }}</p>
                    <p class="mb-2">{{ t('method.p4') }}</p>
                    <p class="mb-1 font-medium">{{ t('method.sources') }}</p>
                    <ul class="mb-2 flex flex-wrap gap-1.5">
                        <li v-for="s in meta.sources" :key="s.code" class="rounded border border-line px-2 py-0.5 font-mono text-xs">{{ s.code }}</li>
                    </ul>
                    <p class="text-xs text-muted">{{ t('method.firms') }}</p>
                </template>
            </section>
        </div>
    </div>
</template>
