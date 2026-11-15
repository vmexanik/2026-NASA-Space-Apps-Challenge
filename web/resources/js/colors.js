// Colour-vision-deficiency-safe scales.
//  - Sequential: reversed "inferno" (light → dark), perceptually uniform, reads as "more fire".
//  - Diverging: PuOr (purple = below normal, orange = above normal).
// Every coloured value is also shown as a number or text, so colour is never the only channel.

const INFERNO = ['#fcffa4', '#f6d746', '#fca50a', '#f37819', '#dd513a', '#bc3754', '#932667', '#6a176e', '#420a68', '#160b39'];
const PUOR = ['#542788', '#8073ac', '#b2abd2', '#d8daeb', '#f7f7f7', '#fee0b6', '#fdb863', '#e08214', '#b35806'];

function hexToRgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function interpolate(stops, t) {
    const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(x));
    const f = x - i;
    const a = hexToRgb(stops[i]);
    const b = hexToRgb(stops[i + 1]);
    const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
    return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/** Counts: sqrt scale so small values stay distinguishable next to extreme months. */
export function sequential(value, max) {
    if (!value || !max) return null; // caller uses the "zero" colour
    return interpolate(INFERNO, Math.sqrt(value / max));
}

/** Anomaly in % (−100…+∞), clamped to ±100 %. */
export function diverging(pct) {
    if (pct === null || pct === undefined) return null;
    const t = (Math.max(-100, Math.min(100, pct)) + 100) / 200;
    return interpolate(PUOR, t);
}

/** Black or white text, whichever contrasts better with the fill. */
export function textOn(fill) {
    if (!fill) return 'currentColor';
    const rgb = fill.startsWith('#') ? hexToRgb(fill) : fill.match(/\d+/g).map(Number);
    const [r, g, b] = rgb.map((v) => {
        const c = v / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    return lum > 0.4 ? '#1d1b19' : '#ffffff';
}

// --- Discrete classes for the calendar -------------------------------------------------
// Five classes above zero with round, readable limits, spaced evenly on a log scale up to the
// largest month of the area (1–10, 11–50, 51–200, …). A legend of ranges reads faster than a ramp.
const NICE = [1, 2, 5];
const CLASS_COLORS = ['#fcffa4', '#fca50a', '#dd513a', '#932667', '#420a68'];

function niceAtLeast(v) {
    for (let p = 1; ; p *= 10) for (const n of NICE) if (n * p >= v) return n * p;
}

/** Upper limits of classes 1–4; class 5 is everything above. */
export function classBreaks(max) {
    if (!max || max <= 5) return [1, 2, 3, 4];
    const out = [];
    for (let k = 1; k <= 4; k++) {
        const b = niceAtLeast(Math.round(max ** (k / 5)));
        out.push(Math.max(b, (out.at(-1) ?? 0) + 1));
    }
    return out;
}

/** 0 for no fires, 1–5 for the classes. */
export function classOf(value, breaks) {
    if (!value) return 0;
    const i = breaks.findIndex((b) => value <= b);
    return i === -1 ? 5 : i + 1;
}

export function classColor(k) {
    return k === 0 ? null : CLASS_COLORS[k - 1];
}

/** [{ k, color, from, to }] for the legend; to is null for the open last class. */
export function classLegend(breaks) {
    return CLASS_COLORS.map((color, i) => ({
        k: i + 1,
        color,
        from: i === 0 ? 1 : breaks[i - 1] + 1,
        to: i < 4 ? breaks[i] : null,
    }));
}
