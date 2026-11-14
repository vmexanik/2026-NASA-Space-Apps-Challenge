// Thin client for the public API. Request body: { aoi: GeoJSON Polygon, date_from, date_to }.

export class ApiError extends Error {
    constructor(message, status, errors = {}) {
        super(message);
        this.status = status;
        this.errors = errors;
    }
}

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content ?? '';

/** Signed in to the admin panel: the map offers "Save as quick area". */
export const isAdmin = () => document.querySelector('meta[name="wc-admin"]') !== null;

async function request(method, url, body, signal) {
    const res = await fetch(url, {
        method,
        signal,
        headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrf() },
        body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
        let data = {};
        try {
            data = await res.json();
        } catch {
            /* not JSON */
        }
        throw new ApiError(data.message || res.statusText, res.status, data.errors || {});
    }
    return res;
}

export const api = {
    meta: () => request('GET', '/api/meta').then((r) => r.json()),
    calendar: (query) => request('POST', '/api/calendar', query).then((r) => r.json()),
    summary: (query) => request('POST', '/api/summary', query).then((r) => r.json()),
    /** Fires in the visible box: { bbox: [w, s, e, n], zoom, date_from, date_to } → GeoJSON + truncated. */
    /** Admin only: save the drawn shape as a quick area. */
    savePreset: (name, geometry) => request('POST', '/presets', { name, geometry }).then((r) => r.json()),
    map: (query, signal) => request('POST', '/api/map', query, signal).then((r) => r.json()),

    /** Downloads the CSV and returns { truncated, expected, max }. */
    async exportCsv(query) {
        const res = await request('POST', '/api/export/csv', query);
        const blob = await res.blob();
        const name = /filename=([^;]+)/.exec(res.headers.get('Content-Disposition') || '')?.[1] || 'hotspots.csv';
        saveBlob(blob, name.replace(/"/g, ''));
        return {
            truncated: res.headers.get('X-Export-Truncated') === '1',
            expected: Number(res.headers.get('X-Export-Expected-Rows')),
            max: Number(res.headers.get('X-Export-Max-Rows')),
        };
    },
};

export function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
