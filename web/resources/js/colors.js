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
    const [r, g, b] = fill.match(/\d+/g).map(Number).map((v) => {
        const c = v / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    return lum > 0.4 ? '#1d1b19' : '#ffffff';
}

export const legendStops = { sequential: INFERNO, diverging: PUOR };
