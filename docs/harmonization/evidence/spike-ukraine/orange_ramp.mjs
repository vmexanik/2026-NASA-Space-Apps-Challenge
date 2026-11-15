// Derive a one-hue orange ramp that mirrors the lightness steps of the documented blue ramp,
// at the hue of the documented orange (#eb6834), then run the skill's ordinal checks on it.
const { validateOrdinal, apca, contrast } = await import(process.argv[2]);

const s2lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const lin2s = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const hex2lin = (h) => [1, 3, 5].map((i) => s2lin(parseInt(h.slice(i, i + 2), 16) / 255));
function oklab([r, g, b]) {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1072969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
          1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
          0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}
function lin([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
          -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
          -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
}
const inGamut = (rgb) => rgb.every((c) => c >= -1e-6 && c <= 1 + 1e-6);
const toHex = (rgb) => "#" + rgb.map((c) => Math.round(Math.min(1, Math.max(0, lin2s(Math.min(1, Math.max(0, c))))) * 255).toString(16).padStart(2, "0")).join("");
const lch = (h) => { const [L, a, b] = oklab(hex2lin(h)); return [L, Math.hypot(a, b), Math.atan2(b, a)]; };

const hue = lch("#eb6834")[2];
function step(L, cWant) {
  let lo = 0, hi = cWant;
  if (!inGamut(lin([L, cWant * Math.cos(hue), cWant * Math.sin(hue)]))) {
    for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; inGamut(lin([L, mid * Math.cos(hue), mid * Math.sin(hue)])) ? (lo = mid) : (hi = mid); }
    cWant = lo * 0.97;
  }
  return toHex(lin([L, cWant * Math.cos(hue), cWant * Math.sin(hue)]));
}
const blueLight = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"];
const blueDark = ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"];
for (const [mode, blue, surface] of [["light", blueLight, "#fcfcfb"], ["dark", blueDark, "#1a1a19"]]) {
  const ramp = blue.map((h) => { const [L, C] = lch(h); return step(L, Math.max(C, 0.12)); });
  const res = validateOrdinal(ramp, { mode, surface });
  console.log(mode, ramp.join(","), res.ok ? "ALL PASS" : "FAIL");
  console.log("    " + JSON.stringify(res.report));
  for (const f of ramp) {
    const w = Math.abs(apca("#ffffff", f)), k = Math.abs(apca("#0b0b0b", f));
    console.log("    ink", f, w > k ? "white" : "black", `(white ${w.toFixed(0)}, black ${k.toFixed(0)})`, "L", lch(f)[0].toFixed(3), "vs surface", contrast(f, surface).toFixed(2));
  }
}
