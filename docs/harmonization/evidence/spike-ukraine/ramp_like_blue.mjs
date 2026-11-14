// A one-hue ramp at the hue of a documented colour, mirroring the lightness of given blue steps; runs the skill's ramp checks.
// usage: node ramp_like_blue.mjs <validate_palette.js> <hue hex> <mode> <surface> <blue hex,...>
const { validateOrdinal, apca } = await import(process.argv[2]);
const [hueHex, mode, surface, list] = process.argv.slice(3);
const s2lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const lin2s = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const hex2lin = (h) => [1, 3, 5].map((i) => s2lin(parseInt(h.slice(i, i + 2), 16) / 255));
function oklab([r, g, b]) {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1072969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}
function lin([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
}
const ok = (rgb) => rgb.every((c) => c >= -1e-6 && c <= 1 + 1e-6);
const hex = (rgb) => "#" + rgb.map((c) => Math.round(Math.min(1, Math.max(0, lin2s(Math.min(1, Math.max(0, c))))) * 255).toString(16).padStart(2, "0")).join("");
const lch = (h) => { const [L, a, b] = oklab(hex2lin(h)); return [L, Math.hypot(a, b), Math.atan2(b, a)]; };
const hue = lch(hueHex)[2];
const ramp = list.split(",").map((b) => {
  let [L, C] = lch(b); C = Math.max(C, 0.12);
  if (!ok(lin([L, C * Math.cos(hue), C * Math.sin(hue)]))) {
    let lo = 0, hi = C;
    for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; ok(lin([L, mid * Math.cos(hue), mid * Math.sin(hue)])) ? (lo = mid) : (hi = mid); }
    C = lo * 0.97;
  }
  return hex(lin([L, C * Math.cos(hue), C * Math.sin(hue)]));
});
const res = validateOrdinal(ramp, { mode, surface });
console.log(mode, ramp.join(","), res.ok ? "ALL PASS" : "FAIL " + JSON.stringify(res.report.filter((r) => !r[1])));
for (const f of ramp) { const w = Math.abs(apca("#ffffff", f)), k = Math.abs(apca("#0b0b0b", f)); console.log("   ink", f, w > k ? "white" : "black"); }
