#!/usr/bin/env python3
"""Build a self-contained HTML page from the output of time_bins.py: one factor per square for the whole year, per
season, per calendar month, or per calendar month pooled with its neighbours; errors, calendar colours, and the
shape of the year each variant gives.

Usage: python3 -I make_time_page.py <time_bins_2deg.json> <time_bins_1deg.json> <time_bins_4deg.json> <out.html>
"""
import json
import sys

F2, F1, F4, OUT = sys.argv[1:5]
d2 = json.load(open(F2, encoding="utf-8"))
d1 = json.load(open(F1, encoding="utf-8"))
d4 = json.load(open(F4, encoding="utf-8"))
UA = {"Ukraine": "Україна", "Brazil": "Бразилія", "Australia": "Австралія"}
payload = {"d2": d2, "other": {"1": d1, "4": d4}, "ua": UA}

html = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Чи потрібні місяці в множнику квадрата</title>
<style>
  :root {
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6f6e69;
    --grid: #e6e5e0; --rule: #b9b8b1; --best: #e3eefb; --worst: #fbe9e1;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9d9c93;
      --grid: #2e2e2c; --rule: #5a5955; --best: #1c3350; --worst: #44261a;
      --s1: #3987e5; --s2: #d95926; --s3: #199e70;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 1100px; margin: 0 auto; padding: 32px 20px 56px; }
  h1 { font-size: 28px; line-height: 1.25; margin: 0 0 10px; }
  h2 { font-size: 21px; margin: 40px 0 10px; }
  h3 { font-size: 15px; margin: 0 0 6px; }
  p { margin: 0 0 12px; max-width: 78ch; }
  .lead { font-size: 18px; color: var(--ink-2); }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; margin: 24px 0; }
  .tile, .card { background: var(--surface); border: 1px solid var(--grid); border-radius: 12px; }
  .tile { padding: 14px 16px; }
  .tile .k { font-size: 13px; color: var(--ink-2); }
  .tile .v { font-size: 21px; font-weight: 650; margin-top: 2px; line-height: 1.3; }
  .tile .s { font-size: 13px; color: var(--ink-3); margin-top: 4px; }
  .card { padding: 16px 18px; position: relative; overflow-x: auto; }
  .row3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 12px; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--ink-2); margin: 0 0 10px; }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; flex: none; }
  svg { display: block; width: 100%; height: auto; }
  .axis text { fill: var(--ink-3); font-size: 11px; font-variant-numeric: tabular-nums; }
  .grid line { stroke: var(--grid); }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; font-variant-numeric: tabular-nums; }
  th, td { padding: 5px 6px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--ink-2); font-weight: 600; vertical-align: bottom; }
  td.hl { background: var(--best); font-weight: 650; border-radius: 4px; }
  td.lo { background: var(--worst); border-radius: 4px; }
  ul, ol { padding-left: 22px; max-width: 82ch; }
  li { margin-bottom: 6px; }
  code { font-size: 13px; }
  .muted { color: var(--ink-3); font-size: 13.5px; }
  .tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--grid);
         border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.16); padding: 7px 10px; font-size: 12.5px; display: none; z-index: 5; }
</style>
</head>
<body>
<main>
  <h1>Чи потрібні місяці в множнику квадрата</h1>
  <p class="lead">Квадрати 2°. Порівнюємо чотири способи прив'язати множник квадрата до часу: один на весь рік, один на сезон,
  один на календарний місяць, і місяць разом із сусідніми (наприклад, для червня — травень, червень і липень разом).
  Кожен рік вгадуємо множниками з інших 10 років.</p>

  <div class="tiles" id="tiles"></div>

  <h2>1. Помилка й колір календаря</h2>
  <div class="card"><table id="table"></table></div>
  <p class="muted" style="margin-top:8px">Синім — найкращий у стовпчику, червонуватим — найгірший. «Календар» — частка місяців,
  де колір календаря (далеко нижче … далеко вище норми) збігся зі справжнім VIIRS.</p>

  <h2>2. Що ламається з одним множником на рік</h2>
  <p>Частка пожеж року, що припадає на кожен місяць. Сірий — справжній VIIRS. Якщо множник один на весь рік, форма року
  зсувається, бо суміш пожеж у різні сезони різна.</p>
  <div class="card">
    <div class="legend">
      <span><i class="sw" style="background:var(--ink-2)"></i>справжній VIIRS</span>
      <span><i class="sw" style="background:var(--s2)"></i>один множник на весь рік</span>
      <span><i class="sw" style="background:var(--s1)"></i>множник на місяць</span>
    </div>
    <div class="row3" id="shapes"></div>
  </div>

  <h2>3. Чи залежить це від розміру квадрата</h2>
  <p>Те саме для квадратів 1° і 4°, помилка на областях ~220 км (2°):</p>
  <div class="card"><table id="robust"></table></div>

  <h2>Висновок (ще не рішення)</h2>
  <ul id="concl"></ul>

  <h2>Як рахували</h2>
  <ol>
    <li>Точки Aqua (MODIS) і Suomi NPP (VIIRS) з файлів країн архіву FIRMS, <code>type = 0</code>, 2012–2022.</li>
    <li>Множник квадрата для місяця m року y = сума VIIRS / сума MODIS у цьому квадраті за інші 10 років, у місяцях часового кошика:
      весь рік — усі 12 місяців; сезон — грудень–лютий, березень–травень, червень–серпень, вересень–листопад; місяць — лише m;
      місяць із сусідніми — m − 1, m, m + 1.</li>
    <li>Кожна клітинка 0,25° вгадується множником свого квадрата 2°; суми по областях 0,5° і 2° порівнюються зі справжнім VIIRS
      (області-місяці зі 100+ точками VIIRS). Квадрат без точок MODIS у кошику за інші роки бере множник усієї країни.</li>
  </ol>

  <h2>Як відтворити</h2>
  <p>Скрипти поруч: <code>time_bins.py</code> (розрахунок, розмір квадрата — третій аргумент) і <code>make_time_page.py</code>
  (ця сторінка). Сирі числа — <code>time_bins_2deg.json</code>, <code>time_bins_1deg.json</code>, <code>time_bins_4deg.json</code>.</p>
</main>
<div class="tip" id="tip"></div>
<script>
(() => {
const P = __DATA__, D = P.d2, C = Object.keys(D.countries);
const V = ["year", "season", "month", "month3"];
const VN = {year: "Один на весь рік", season: "На сезон (4)", month: "На місяць (12)", month3: "Місяць із сусідніми (12)"};
const pct = (x, d = 1) => (x * 100).toFixed(d).replace(".", ",") + "%";
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const MON = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"];
const tip = document.getElementById("tip");
const R = (c, v) => D.countries[c].variants[v];

// tiles
const ua = c => R(c, "year")["2.0"].error, um = c => R(c, "month")["2.0"].error;
document.getElementById("tiles").innerHTML = `
  <div class="tile"><div class="k">Один множник на весь рік</div><div class="v">гірше всюди, найбільше в Україні</div>
    <div class="s">області ~220 км: ${C.map(c => pct(ua(c), 0)).join(" / ")} проти ${C.map(c => pct(um(c), 0)).join(" / ")} з місяцями (Україна / Бразилія / Австралія)</div></div>
  <div class="tile"><div class="k">Місяць, сезон чи місяць із сусідніми</div><div class="v">майже рівні</div>
    <div class="s">різниця між ними 0,1–2,5 пункту; в Україні й Бразилії найкращий місяць, в Австралії — місяць із сусідніми</div></div>
  <div class="tile"><div class="k">Чому потрібні місяці</div><div class="v">у різні сезони різна суміш пожеж</div>
    <div class="s">з одним множником Україна отримала б березень і жовтень завеликими, липень і серпень замалими</div></div>`;

// main table
const cols = [];
for (const c of C) for (const q of ["0.5", "2.0"]) for (const k of ["error", "calendar"]) cols.push([c, q, k]);
const ext = cols.map(([c, q, k]) => { const vals = V.map(v => R(c, v)[q][k]);
  return k === "error" ? {best: Math.min(...vals), worst: Math.max(...vals)} : {best: Math.max(...vals), worst: Math.min(...vals)}; });
document.getElementById("table").innerHTML =
  `<thead><tr><th rowspan="2">Множник квадрата</th>${C.map(c => `<th colspan="4" style="text-align:center">${P.ua[c]}</th>`).join("")}</tr>` +
  `<tr>${C.map(() => `<th>помилка<br>~55 км</th><th>календар<br>~55 км</th><th>помилка<br>~220 км</th><th>календар<br>~220 км</th>`).join("")}</tr></thead><tbody>` +
  V.map(v => `<tr><td>${VN[v]}</td>` + cols.map(([c, q, k], i) => { const x = R(c, v)[q][k];
    const cls = Math.abs(x - ext[i].best) < 1e-12 ? "hl" : Math.abs(x - ext[i].worst) < 1e-12 ? "lo" : "";
    return `<td class="${cls}">${pct(x)}</td>`; }).join("") + `</tr>`).join("") + `</tbody>`;

// shape charts
const NS = "http://www.w3.org/2000/svg";
const el = (tag, a, p) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); p.appendChild(e); return e; };
function shapes() {
  const box = document.getElementById("shapes"); box.innerHTML = "";
  for (const c of C) {
    const wrap = document.createElement("div"); wrap.innerHTML = `<h3>${P.ua[c]}</h3>`; box.appendChild(wrap);
    const W = 340, H = 190, L = 36, Rr = 6, T = 8, B = 22;
    const svg = el("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${P.ua[c]}: частка пожеж року по місяцях`}, wrap);
    const S = D.countries[c].shape, series = [["actual", "--ink-2"], ["year", "--s2"], ["month", "--s1"]];
    const vmax = Math.ceil(Math.max(...series.flatMap(([k]) => S[k])) * 100 / 5) * 5 / 100;
    const y = v => T + (1 - v / vmax) * (H - T - B), gw = (W - L - Rr) / 12, bw = (gw - 4) / 3;
    const g = el("g", {class: "grid"}, svg), ax = el("g", {class: "axis"}, svg);
    for (let k = 0; k <= 2; k++) { const v = vmax * k / 2; el("line", {x1: L, x2: W - Rr, y1: y(v), y2: y(v)}, g);
      el("text", {x: L - 5, y: y(v) + 4, "text-anchor": "end"}, ax).textContent = Math.round(v * 100) + "%"; }
    for (let m = 0; m < 12; m++) {
      el("text", {x: L + m * gw + gw / 2, y: H - 6, "text-anchor": "middle"}, ax).textContent = MON[m].slice(0, 2);
      series.forEach(([k, col], i) => {
        const x = L + m * gw + 2 + i * bw, v = S[k][m];
        const r = el("rect", {x, y: y(v), width: Math.max(bw - 1, 1), height: Math.max(y(0) - y(v), 0), fill: css(col), rx: 1}, svg);
        r.addEventListener("mousemove", ev => { tip.innerHTML = `<b>${P.ua[c]}, ${MON[m]}</b><br>справжній VIIRS: ${pct(S.actual[m])}<br>один множник на рік: ${pct(S.year[m])}<br>множник на місяць: ${pct(S.month[m])}`;
          tip.style.display = "block"; tip.style.left = (ev.clientX + 14) + "px"; tip.style.top = (ev.clientY + 14) + "px"; });
        r.addEventListener("mouseleave", () => tip.style.display = "none");
      });
    }
  }
}
shapes();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", shapes);

// robustness
const O = P.other;
document.getElementById("robust").innerHTML =
  `<thead><tr><th>Множник квадрата</th>${["1", "4"].map(s => C.map(c => `<th>${P.ua[c]}, ${s}°</th>`).join("")).join("")}</tr></thead><tbody>` +
  V.map(v => `<tr><td>${VN[v]}</td>` + ["1", "4"].map(s => C.map(c => {
    const vals = V.map(w => O[s].countries[c].variants[w]["2.0"].error), x = O[s].countries[c].variants[v]["2.0"].error;
    const cls = x === Math.min(...vals) ? "hl" : x === Math.max(...vals) ? "lo" : "";
    return `<td class="${cls}">${pct(x)}</td>`; }).join("")).join("") + `</tr>`).join("") + `</tbody>`;

document.getElementById("concl").innerHTML = `
  <li><b>Прив'язка до часу потрібна.</b> Один множник на весь рік дає найбільшу помилку в усіх трьох країнах; в Україні на
    областях ~220 км — ${pct(ua("Ukraine"), 0)} проти ${pct(um("Ukraine"), 0)} з місяцями, і календар правильний у ${pct(R("Ukraine", "year")["2.0"].calendar, 0)}
    місяців проти ${pct(R("Ukraine", "month")["2.0"].calendar, 0)}.</li>
  <li><b>Місяць, сезон і місяць із сусідніми майже рівні.</b> Місяць найкращий там, де пожеж багато й сезони різкі (Україна, Бразилія);
    місяць із сусідніми — там, де в окремому місяці пожеж менше (Австралія).</li>
  <li>Те саме видно на квадратах 1° і 4°: висновок не залежить від розміру квадрата.</li>
  <li>Можливе покращення: множник місяця, який позичає із сусідніх місяців лише тоді, коли своїх пожеж мало — так само,
    як №15 позичає в сусідніх квадратів.</li>`;
})();
</script>
</body>
</html>
"""
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(html.replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
print("wrote", OUT)
