#!/usr/bin/env python3
"""Build a self-contained HTML page from the output of borrow_test.py: borrowing for the factor of a 2-degree square
and month — which neighbourhood and how strongly — on three countries.

Usage: python3 -I make_borrow_page.py <borrow_test.json> <out.html>
"""
import json
import sys

SRC, OUT = sys.argv[1], sys.argv[2]
data = json.load(open(SRC, encoding="utf-8"))
UA = {"Ukraine": "Україна", "Brazil": "Бразилія", "Australia": "Австралія"}
payload = {"data": data, "ua": UA}

html = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Позичання для множника квадрата 2°</title>
<style>
  :root {
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6f6e69;
    --grid: #e6e5e0; --rule: #b9b8b1; --best: #e3eefb; --worst: #fbe9e1;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --base: #b9b8b1;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9d9c93;
      --grid: #2e2e2c; --rule: #5a5955; --best: #1c3350; --worst: #44261a;
      --s1: #3987e5; --s2: #d95926; --s3: #199e70; --base: #6f6e69;
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
  .ln { width: 16px; height: 3px; border-radius: 2px; display: inline-block; }
  svg { display: block; width: 100%; height: auto; }
  .axis text { fill: var(--ink-3); font-size: 11px; font-variant-numeric: tabular-nums; }
  .grid line { stroke: var(--grid); }
  .val { fill: var(--ink-2); font-size: 10.5px; font-variant-numeric: tabular-nums; }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; font-variant-numeric: tabular-nums; }
  th, td { padding: 4px 6px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
  th { color: var(--ink-2); font-weight: 600; vertical-align: bottom; }
  td.hl { background: var(--best); font-weight: 650; border-radius: 4px; }
  td.lo { background: var(--worst); border-radius: 4px; }
  tr.pick td { font-weight: 650; }
  ul, ol { padding-left: 22px; max-width: 82ch; }
  li { margin-bottom: 6px; }
  code { font-size: 13px; }
  .formula { font-size: 16px; background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 10px 14px; display: inline-block; margin: 4px 0 10px; }
  .muted { color: var(--ink-3); font-size: 13.5px; }
  .tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--grid);
         border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.16); padding: 7px 10px; font-size: 12.5px; display: none; z-index: 5; }
</style>
</head>
<body>
<main>
  <h1>Позичання для множника квадрата 2°</h1>
  <p class="lead">Квадрат 2°, множник на календарний місяць. Якщо своїх пожеж у квадраті мало, множник позичає в сусідів —
  тим сильніше, чим менше своїх точок. Перевіряємо, у кого позичати і наскільки сильно. Кожен рік вгадуємо множниками з інших 10 років.</p>

  <div class="tiles" id="tiles"></div>

  <h2>Як позичає квадрат</h2>
  <div class="formula">множник = (VIIRS квадрата + λ × множник сусідів) / (MODIS квадрата + λ)</div>
  <p>λ — сила позичання в точках MODIS. Квадрат із λ своїми точками вірить собі наполовину; з 10 × λ — на 91%. Множник сусідів
  рахується так само й тягнеться до множника всього регіону, якщо бідні й сусіди.</p>
  <p>Сусіди, яких перевіряли: <b>хрест</b> — 4 квадрати ліворуч, праворуч, згори, знизу (твоя ідея); <b>кільце</b> — усі 8 навколо;
  <b>сусідні місяці</b> — той самий квадрат у попередньому й наступному місяці; <b>хрест + місяці</b> — разом; <b>великий квадрат</b> —
  8°, у якому лежить квадрат; <b>регіон</b> — уся країна, як у №15.</p>

  <h2>1. Бідні на пожежі місця</h2>
  <p>Області ~55 км, чий квадрат за інші роки має менше 100 точок MODIS у цьому місяці. Саме для них позичання й потрібне. λ = 300.</p>
  <div class="card">
    <div class="legend" id="legend1"></div>
    <div class="row3" id="sparse"></div>
  </div>

  <h2>2. Наскільки сильно позичати</h2>
  <p>Загальна помилка на областях ~220 км залежно від сили позичання λ. Пунктир — без позичання. Занадто сильне позичання
  шкодить: тоді навіть багаті на пожежі квадрати починають вірити сусідам.</p>
  <div class="card">
    <div class="legend" id="legend2"></div>
    <div class="row3" id="lam"></div>
  </div>

  <h2>3. Усі числа</h2>
  <p>Помилка на областях ~55 км і ~220 км, і окремо в бідних місцях (області ~55 км). Синім — найкращий у стовпчику, червонуватим — найгірший.</p>
  <div class="card"><table id="table"></table></div>

  <h2>Висновок (ще не рішення)</h2>
  <ul id="concl"></ul>

  <h2>Як рахували</h2>
  <ol>
    <li>Точки Aqua (MODIS) і Suomi NPP (VIIRS) з файлів країн архіву FIRMS, <code>type = 0</code>, 2012–2022.</li>
    <li>M і V — точки MODIS і VIIRS квадрата 2° у цьому календарному місяці за інші 10 років. Без позичання множник = V / M
      (без жодної точки MODIS — множник регіону).</li>
    <li>З позичанням: множник = (V + λ · k<sub>сус</sub>) / (M + λ), де k<sub>сус</sub> = (V<sub>сус</sub> + λ · k<sub>регіону</sub>) / (M<sub>сус</sub> + λ).</li>
    <li>Кожна клітинка 0,25° вгадується множником свого квадрата; суми по областях 0,5° і 2° порівнюються зі справжнім VIIRS
      (області-місяці зі 100+ точками VIIRS). «Бідне місце» — область, чий квадрат за інші роки має менше 100 точок MODIS у цьому місяці.</li>
  </ol>

  <h2>Як відтворити</h2>
  <p>Скрипти поруч: <code>borrow_test.py</code> (розрахунок) і <code>make_borrow_page.py</code> (ця сторінка). Сирі числа — <code>borrow_test.json</code>.</p>
</main>
<div class="tip" id="tip"></div>
<script>
(() => {
const P = __DATA__, D = P.data, C = Object.keys(D.countries), L = D.lambdas.map(String);
const VAR = ["cross", "ring", "months", "cross+months", "big square", "region"];
const VN = {own: "без позичання", cross: "хрест (4 сусіди)", ring: "кільце (8 сусідів)", months: "сусідні місяці",
            "cross+months": "хрест + місяці", "big square": "великий квадрат 8°", region: "регіон (країна)"};
const COL = {cross: "--s1", months: "--s2", "cross+months": "--s3"};
const pct = (x, d = 1) => x == null ? "—" : (x * 100).toFixed(d).replace(".", ",") + "%";
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tip = document.getElementById("tip");
const own = (c) => D.countries[c].variants.own["-"];
const get = (c, v, lam) => v === "own" ? own(c) : D.countries[c].variants[v][lam];
const PICK = ["cross", "300"];

// tiles
const sp = C.map(c => `${pct(own(c)["0.5"].error_sparse, 0)} → ${pct(get(c, ...PICK)["0.5"].error_sparse, 0)}`).join(" / ");
const share = C.map(c => pct(D.countries[c].sparse_share["0.5"], 1)).join(" / ");
const all2 = C.map(c => `${pct(own(c)["2.0"].error)} → ${pct(get(c, ...PICK)["2.0"].error)}`).join(" / ");
document.getElementById("tiles").innerHTML = `
  <div class="tile"><div class="k">Бідні на пожежі місця</div><div class="v">позичання сильно допомагає</div>
    <div class="s">хрест, λ = 300: помилка ${sp} (Україна / Бразилія / Австралія)</div></div>
  <div class="tile"><div class="k">Загалом</div><div class="v">зміна мала, бо бідних місць мало</div>
    <div class="s">у бідних місцях лише ${share} пожеж; області ~220 км: ${all2}</div></div>
  <div class="tile"><div class="k">Найнадійніше</div><div class="v">хрест із 4 сусідів, λ = 300</div>
    <div class="s">ніде не гірше, ніж без позичання, і допомагає бідним місцям у всіх трьох країнах</div></div>`;

const NS = "http://www.w3.org/2000/svg";
const el = (tag, a, p) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); p.appendChild(e); return e; };
const showTip = (ev, html) => { tip.innerHTML = html; tip.style.display = "block"; tip.style.left = (ev.clientX + 14) + "px"; tip.style.top = (ev.clientY + 14) + "px"; };
const hide = () => tip.style.display = "none";

// 1. sparse places: horizontal bars per country
document.getElementById("legend1").innerHTML = `<span><i class="sw" style="background:var(--base)"></i>без позичання</span><span><i class="sw" style="background:var(--s1)"></i>з позичанням, λ = 300</span>`;
function sparse() {
  const box = document.getElementById("sparse"); box.innerHTML = "";
  for (const c of C) {
    const wrap = document.createElement("div"); wrap.innerHTML = `<h3>${P.ua[c]}</h3>`; box.appendChild(wrap);
    const rows = ["own", ...VAR], W = 340, rh = 22, H = rows.length * rh + 24, Lx = 128, Rx = 40;
    const svg = el("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${P.ua[c]}: помилка в бідних місцях`}, wrap);
    const xmax = 0.45, x = v => Lx + v / xmax * (W - Lx - Rx);
    const ax = el("g", {class: "axis"}, svg), g = el("g", {class: "grid"}, svg);
    for (const v of [0, 0.1, 0.2, 0.3, 0.4]) { el("line", {x1: x(v), x2: x(v), y1: 0, y2: H - 20}, g);
      el("text", {x: x(v), y: H - 6, "text-anchor": "middle"}, ax).textContent = Math.round(v * 100) + "%"; }
    rows.forEach((v, i) => {
      const val = get(c, v, "300")["0.5"].error_sparse, yy = i * rh + 4;
      el("text", {x: Lx - 6, y: yy + 13, "text-anchor": "end", fill: css("--ink-2"), "font-size": 11.5}, svg).textContent = VN[v];
      const r = el("rect", {x: Lx, y: yy, width: Math.max(x(val) - Lx, 1), height: rh - 7, rx: 3, fill: css(v === "own" ? "--base" : "--s1")}, svg);
      el("text", {x: x(val) + 4, y: yy + 12, class: "val"}, svg).textContent = pct(val, 0);
      r.addEventListener("mousemove", ev => showTip(ev, `<b>${P.ua[c]}: ${VN[v]}</b><br>помилка в бідних місцях: ${pct(val)}`));
      r.addEventListener("mouseleave", hide);
    });
  }
}

// 2. lambda curves
document.getElementById("legend2").innerHTML = Object.keys(COL).map(v => `<span><i class="ln" style="background:var(${COL[v]})"></i>${VN[v]}</span>`).join("") +
  `<span><i class="ln" style="background:var(--ink-2)"></i>без позичання (пунктир)</span>`;
function lam() {
  const box = document.getElementById("lam"); box.innerHTML = "";
  for (const c of C) {
    const wrap = document.createElement("div"); wrap.innerHTML = `<h3>${P.ua[c]}</h3>`; box.appendChild(wrap);
    const W = 340, H = 200, Lx = 44, Rx = 24, T = 10, B = 26;
    const svg = el("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${P.ua[c]}: помилка залежно від λ`}, wrap);
    const vals = Object.keys(COL).flatMap(v => L.map(l => get(c, v, l)["2.0"].error)).concat([own(c)["2.0"].error]);
    const lo = Math.floor(Math.min(...vals) * 200) / 200 - 0.005, hi = Math.ceil(Math.max(...vals) * 200) / 200 + 0.005;
    const x = i => Lx + i * (W - Lx - Rx) / (L.length - 1), y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const g = el("g", {class: "grid"}, svg), ax = el("g", {class: "axis"}, svg);
    for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; el("line", {x1: Lx, x2: W - Rx, y1: y(v), y2: y(v)}, g);
      el("text", {x: Lx - 5, y: y(v) + 4, "text-anchor": "end"}, ax).textContent = (v * 100).toFixed(1).replace(".", ",") + "%"; }
    L.forEach((l, i) => el("text", {x: x(i), y: H - 8, "text-anchor": "middle"}, ax).textContent = "λ " + l);
    el("line", {x1: Lx, x2: W - Rx, y1: y(own(c)["2.0"].error), y2: y(own(c)["2.0"].error), stroke: css("--ink-2"), "stroke-dasharray": "4 4"}, svg);
    for (const v of Object.keys(COL)) {
      el("path", {d: L.map((l, i) => (i ? "L" : "M") + x(i) + "," + y(get(c, v, l)["2.0"].error)).join(""), fill: "none", stroke: css(COL[v]), "stroke-width": 2}, svg);
      L.forEach((l, i) => { const val = get(c, v, l)["2.0"].error;
        el("circle", {cx: x(i), cy: y(val), r: 3.5, fill: css(COL[v]), stroke: css("--surface"), "stroke-width": 1.5}, svg);
        const h = el("circle", {cx: x(i), cy: y(val), r: 9, fill: "transparent"}, svg);
        h.addEventListener("mousemove", ev => showTip(ev, `<b>${P.ua[c]}: ${VN[v]}, λ = ${l}</b><br>помилка на областях ~220 км: ${pct(val, 2)}<br>без позичання: ${pct(own(c)["2.0"].error, 2)}`));
        h.addEventListener("mouseleave", hide); });
    }
  }
}
function drawAll() { sparse(); lam(); }
drawAll();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawAll);

// 3. table
const rows = [["own", "-"], ...VAR.flatMap(v => L.map(l => [v, l]))];
const cols = C.flatMap(c => [[c, "0.5", "error"], [c, "2.0", "error"], [c, "0.5", "error_sparse"]]);
const ext = cols.map(([c, q, k]) => { const vs = rows.map(([v, l]) => get(c, v, l)[q][k]); return {best: Math.min(...vs), worst: Math.max(...vs)}; });
document.getElementById("table").innerHTML =
  `<thead><tr><th rowspan="2">Сусіди</th><th rowspan="2">λ</th>${C.map(c => `<th colspan="3" style="text-align:center">${P.ua[c]}</th>`).join("")}</tr>` +
  `<tr>${C.map(() => `<th>~55 км</th><th>~220 км</th><th>бідні<br>місця</th>`).join("")}</tr></thead><tbody>` +
  rows.map(([v, l]) => `<tr class="${v === PICK[0] && l === PICK[1] ? "pick" : ""}"><td>${VN[v]}</td><td>${l === "-" ? "—" : l}</td>` +
    cols.map(([c, q, k], i) => { const x = get(c, v, l)[q][k];
      const cls = Math.abs(x - ext[i].best) < 1e-12 ? "hl" : Math.abs(x - ext[i].worst) < 1e-12 ? "lo" : "";
      return `<td class="${cls}">${pct(x)}</td>`; }).join("") + `</tr>`).join("") + `</tbody>`;

document.getElementById("concl").innerHTML = `
  <li><b>Позичання потрібне бідним на пожежі місцям:</b> там помилка падає з ${C.map(c => pct(own(c)["0.5"].error_sparse, 0)).join(" / ")}
    до ${C.map(c => pct(get(c, ...PICK)["0.5"].error_sparse, 0)).join(" / ")} (хрест, λ = 300).</li>
  <li><b>Загальна точність змінюється мало</b> (до −1,2 пункту), бо в бідних місцях цих трьох країн лише ${share} пожеж.
    Але людина може вибрати на карті саме тихе місце — тоді виграш відчутний.</li>
  <li><b>Хрест із 4 сусідів (λ = 300)</b> — найнадійніший: ніде не гірший, ніж без позичання. Сусідні місяці трохи кращі
    в Австралії, але в Україні нічого не дають. Кільце з 8 сусідів майже таке саме, як хрест.</li>
  <li><b>Занадто сильне позичання шкодить</b> (λ = 1000): багаті квадрати починають вірити сусідам, і помилка росте.</li>
  <li>Коли бідні й сусіди, множник поки тягнеться до регіону (країни). Для всього світу це буде множник більшої області
    або всього світу — вирішимо, коли складатимемо базу.</li>`;
})();
</script>
</body>
</html>
"""
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(html.replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
print("wrote", OUT)
