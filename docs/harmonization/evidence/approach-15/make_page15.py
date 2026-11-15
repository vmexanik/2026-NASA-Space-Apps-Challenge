#!/usr/bin/env python3
"""Build a self-contained HTML page that explains approach 15 in plain words: the 2-degree cells of the globe that
have fires, how much data each holds, how a cell's factor is drawn toward the country's, a worked example, and how
the application would use the factors.

Usage: python3 -I make_page15.py <global_cells.json> <dir of npz files from extract.py> <out.html>
"""
import json
import sys
from collections import Counter

import numpy as np

SRC, CUT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
LAMBDA = 100
g = json.load(open(SRC, encoding="utf-8"))
months_rich = Counter()
for row, col, month, n in g["cell_month"]:
    if n >= LAMBDA:
        months_rich[(row, col)] += 1
cells = [[row, col, n, months_rich.get((row, col), 0)] for row, col, n in g["cells"]]
cm_counts = [n for _, _, _, n in g["cell_month"]]
total = sum(cm_counts)
poor = []
for lim in (10, 100, 1000):
    few = [n for n in cm_counts if n < lim]
    poor.append({"lim": lim, "share": len(few) / len(cm_counts), "points": sum(few) / total})

# worked example: Ukraine, August, learning years 2012-2016
D0 = np.datetime64("2000-01-01")


def load(sensor):
    parts = [np.load(f"{CUT}/Ukraine_{sensor}_{y}.npz") for y in range(2012, 2017)]
    d = {k: np.concatenate([p[k] for p in parts]) for k in parts[0].files}
    if sensor == "modis":
        keep = d["aqua"] == 1
        d = {k: v[keep] for k, v in d.items()}
    mon = (D0 + (d["t"] // 1440).astype("timedelta64[D]")).astype("datetime64[M]").astype(int) % 12 + 1
    row = np.floor((d["lat"] + 90) / 2).astype(int)
    col = np.floor((d["lon"] + 180) / 2).astype(int)
    return mon, row, col


mm, mr, mc = load("modis")
vm, vr, vc = load("viirs-snpp")
sel_m, sel_v = mm == 8, vm == 8
k_country = sel_v.sum() / sel_m.sum()
cnt_m = Counter(zip(mr[sel_m], mc[sel_m]))
cnt_v = Counter(zip(vr[sel_v], vc[sel_v]))
example_cells = [(69, 109), (69, 104), (69, 101), (70, 109)]  # lat 48-50 lon 38-40, lat 48-50 lon 28-30, lat 48-50 lon 22-24, lat 50-52 lon 38-40
example = {"k_country": float(k_country), "modis": int(sel_m.sum()), "viirs": int(sel_v.sum()), "cells": []}
for row, col in example_cells:
    m, v = cnt_m.get((row, col), 0), cnt_v.get((row, col), 0)
    example["cells"].append({"lat": row * 2 - 90, "lon": col * 2 - 180, "m": m, "v": v,
                             "own": v / m if m else None, "w": m / (m + LAMBDA),
                             "k15": (v + LAMBDA * k_country) / (m + LAMBDA)})

payload = {"cells": cells, "n_cells": len(cells), "n_cell_months": len(cm_counts), "points": total,
           "poor": poor, "example": example, "lambda": LAMBDA, "years": g["years"]}

html = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>№15 простими словами: місця на глобусі</title>
<style>
  :root {
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6f6e69;
    --grid: #e6e5e0; --rule: #b9b8b1; --best: #e3eefb; --s1: #2a78d6;
    --q1: #86b6ef; --q2: #5598e7; --q3: #2a78d6; --q4: #1c5cab; --q5: #104281;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9d9c93;
      --grid: #2e2e2c; --rule: #5a5955; --best: #1c3350; --s1: #3987e5;
      --q1: #184f95; --q2: #256abf; --q3: #3987e5; --q4: #6da7ec; --q5: #9ec5f4;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 1100px; margin: 0 auto; padding: 32px 20px 56px; }
  h1 { font-size: 28px; line-height: 1.25; margin: 0 0 10px; }
  h2 { font-size: 21px; margin: 40px 0 10px; }
  p { margin: 0 0 12px; max-width: 78ch; }
  .lead { font-size: 18px; color: var(--ink-2); }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin: 24px 0; }
  .tile, .card { background: var(--surface); border: 1px solid var(--grid); border-radius: 12px; }
  .tile { padding: 14px 16px; }
  .tile .k { font-size: 13px; color: var(--ink-2); }
  .tile .v { font-size: 30px; font-weight: 650; margin-top: 2px; font-variant-numeric: tabular-nums; }
  .tile .s { font-size: 13px; color: var(--ink-3); margin-top: 2px; }
  .card { padding: 16px 18px; position: relative; overflow-x: auto; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--ink-2); margin: 0 0 10px; }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .sw { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }
  svg { display: block; width: 100%; height: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }
  th, td { padding: 6px 9px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--ink-2); font-weight: 600; vertical-align: bottom; }
  td.hl { background: var(--best); font-weight: 650; border-radius: 4px; }
  ol, ul { padding-left: 22px; max-width: 82ch; }
  li { margin-bottom: 6px; }
  code { font-size: 13.5px; }
  .muted { color: var(--ink-3); font-size: 13.5px; }
  .formula { font-size: 17px; background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 12px 16px; display: inline-block; margin: 6px 0 12px; }
  .tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--grid);
         border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.16); padding: 7px 10px; font-size: 12.5px; display: none; z-index: 5; }
</style>
</head>
<body>
<main>
  <h1>№15 простими словами: місця на глобусі</h1>
  <p class="lead">Глобус ділиться на квадрати 2° × 2° (~200 × 200 км). Кожен квадрат отримує 12 чисел, по одному на календарний
  місяць: у скільки разів VIIRS бачить більше точок, ніж MODIS, саме тут і саме в цьому місяці. Де своїх даних мало,
  число квадрата тягнеться до числа країни.</p>

  <div class="tiles" id="tiles"></div>

  <h2>Де на глобусі бувають пожежі</h2>
  <p>Кожен кольоровий квадрат — 2° × 2°, де MODIS Aqua за __Y0__–__Y1__ роки бачив хоча б одну пожежу на рослинності.
  Кордонів на карті немає: материки малюють самі квадрати. Наведіть мишку на квадрат.</p>
  <div class="card">
    <div class="legend" id="legend"></div>
    <svg id="map" viewBox="0 0 1080 540" role="img" aria-label="Квадрати 2° з пожежами на карті світу"></svg>
  </div>

  <h2>Як №15 рахує число квадрата</h2>
  <ol>
    <li>Беремо навчальні роки, коли літали обидва супутники.</li>
    <li>Для країни й місяця рахуємо <b>число країни</b>: скільки точок VIIRS на одну точку MODIS (як №2).</li>
    <li>Для квадрата й того самого місяця дивимось, скільки точок MODIS і VIIRS було саме в ньому.</li>
    <li>До даних квадрата додаємо <b>__LAMBDA__ «уявних» точок MODIS</b> з числом країни і ділимо:</li>
  </ol>
  <div class="formula">число квадрата = (VIIRS квадрата + __LAMBDA__ × число країни) / (MODIS квадрата + __LAMBDA__)</div>
  <p>Що більше своїх точок у квадраті, то менше важать уявні: квадрат вірить собі. Що менше — то більше він схожий на країну.</p>
  <div class="card"><table id="weights"></table></div>

  <h2>Приклад: Україна, серпень</h2>
  <p id="exlead"></p>
  <div class="card"><table id="example"></table></div>
  <p class="muted" style="margin-top:8px">Квадрат з однією точкою MODIS дав би «своє» число 1,0 — це шум. №15 дає майже число країни.</p>

  <h2>Скільки квадратів бідні на дані</h2>
  <p>Квадратів багато, але більшість пожеж сидить у небагатьох із них. Числа — за всі __NY__ років разом, на квадрат і місяць:</p>
  <div class="card"><table id="poor"></table></div>
  <p class="muted" style="margin-top:8px">Тобто бідних квадратів багато, але пожеж у них майже немає. Саме для них і потрібне стягування до країни.</p>

  <h2>Як застосунок це використає</h2>
  <ul>
    <li>Таблиця множників маленька: квадрат × місяць ≈ <span id="nrows"></span> рядків. У PostGIS це одна невелика таблиця.</li>
    <li>Кожна точка MODIS отримує <b>вагу</b> — число свого квадрата й місяця.</li>
    <li>Будь-яка область, яку людина намалює на карті, — це <b>сума ваг</b> точок MODIS усередині неї. Тому довільний
      багатокутник працює сам собою, нічого окремо рахувати не треба.</li>
    <li>З 2012 року в ряд іде сам VIIRS, ваги не потрібні.</li>
  </ul>

  <h2>Що ще треба вирішити</h2>
  <ul>
    <li><b>Розмір квадрата.</b> 2° взяли навмання. Менший (1°) точніше ловить місцеві пожежі, але даних у ньому менше.
      Треба перевірити 1°, 2°, 5° так само, на чужих роках.</li>
    <li><b>Сила стягування.</b> __LAMBDA__ уявних точок теж взяли навмання — підібрати перевіркою.</li>
    <li><b>До чого стягувати.</b> Квадрат 2° може лежати в кількох країнах. Батьком може бути країна, регіон, тип
      місцевості або більший квадрат (наприклад, 10°), а над ним — увесь світ. Тоді число є для будь-якого місця.</li>
    <li><b>Terra.</b> До середини 2002 року літав лише Terra (о 10:30, а не о 13:30). Для нього потрібні свої множники.</li>
  </ul>

  <h2>Як відтворити</h2>
  <p>Скрипти поруч: <code>global_cells.py</code> (квадрати з пожежами по всьому архіву MODIS), <code>make_page15.py</code>
  (ця сторінка, приклад рахує з вирізаних файлів України, <code>extract.py</code>). Сирі числа — <code>global_cells.json</code>.</p>
</main>
<div class="tip" id="tip"></div>
<script>
(() => {
const D = __DATA__;
const int = v => Math.round(v).toLocaleString("uk-UA");
const pct = (x, d = 0) => (x * 100).toFixed(d).replace(".", ",") + "%";
const num = (x, d = 2) => x == null ? "—" : x.toFixed(d).replace(".", ",");
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const rich = D.poor.find(p => p.lim === D.lambda);

document.getElementById("tiles").innerHTML = `
  <div class="tile"><div class="k">Квадратів 2° на глобусі</div><div class="v">16 200</div><div class="s">180 × 90</div></div>
  <div class="tile"><div class="k">З них бувають пожежі</div><div class="v">${int(D.n_cells)}</div><div class="s">MODIS Aqua, ${D.years[0]}–${D.years[1]}</div></div>
  <div class="tile"><div class="k">Чисел у таблиці множників</div><div class="v">≈ ${int(D.n_cell_months)}</div><div class="s">квадрат × місяць, де були пожежі</div></div>
  <div class="tile"><div class="k">Точок там, де своїх даних достатньо</div><div class="v">${pct(1 - rich.points)}</div><div class="s">квадрат × місяць зі ${D.lambda}+ точками MODIS</div></div>`;

// map
const CL = [[1, "1–99"], [100, "100–999"], [1000, "1–10 тис."], [10000, "10–100 тис."], [100000, "100 тис.+"]];
document.getElementById("legend").innerHTML = "точок MODIS у квадраті за всі роки:" +
  CL.map(([, label], i) => `<span><i class="sw" style="background:var(--q${i + 1})"></i>${label}</span>`).join("");
const svg = document.getElementById("map"), NS = "http://www.w3.org/2000/svg", S = 6;
const el = (tag, a, p = svg) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); p.appendChild(e); return e; };
const byKey = new Map(D.cells.map(c => [c[0] * 1000 + c[1], c]));
function draw() {
  svg.innerHTML = "";
  el("rect", {x: 0, y: 0, width: 1080, height: 540, fill: css("--surface")});
  const g = el("g", {stroke: css("--grid"), "stroke-width": 1});
  for (let lon = -150; lon <= 150; lon += 30) el("line", {x1: (lon + 180) * 3, x2: (lon + 180) * 3, y1: 0, y2: 540}, g);
  for (let lat = -60; lat <= 60; lat += 30) el("line", {x1: 0, x2: 1080, y1: (90 - lat) * 3, y2: (90 - lat) * 3}, g);
  const cols = CL.map((_, i) => css(`--q${i + 1}`));
  const frag = document.createDocumentFragment();
  for (const [row, col, n] of D.cells) {
    let k = 0; while (k + 1 < CL.length && n >= CL[k + 1][0]) k++;
    const r = document.createElementNS(NS, "rect");
    r.setAttribute("x", col * S); r.setAttribute("y", (89 - row) * S); r.setAttribute("width", S - 0.6); r.setAttribute("height", S - 0.6);
    r.setAttribute("fill", cols[k]); frag.appendChild(r);
  }
  svg.appendChild(frag);
  for (const [lat, label] of [[60, "60° пн."], [30, "30° пн."], [0, "екватор"], [-30, "30° пд."]])
    el("text", {x: 4, y: (90 - lat) * 3 - 3, fill: css("--ink-3"), "font-size": 11}).textContent = label;
}
draw();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
const tip = document.getElementById("tip");
svg.addEventListener("mousemove", ev => {
  const p = svg.createSVGPoint(); p.x = ev.clientX; p.y = ev.clientY;
  const q = p.matrixTransform(svg.getScreenCTM().inverse());
  const col = Math.floor(q.x / S), row = 89 - Math.floor(q.y / S), c = byKey.get(row * 1000 + col);
  if (!c) { tip.style.display = "none"; return; }
  const lat = row * 2 - 90, lon = col * 2 - 180;
  tip.innerHTML = `<b>шир. ${lat}…${lat + 2}°, довг. ${lon}…${lon + 2}°</b><br>точок MODIS за ${D.years[0]}–${D.years[1]}: ${int(c[2])}<br>` +
                  `місяців, де квадрат вірить переважно собі (${D.lambda}+ точок): ${c[3]} з 12`;
  tip.style.display = "block"; tip.style.left = (ev.clientX + 14) + "px"; tip.style.top = (ev.clientY + 14) + "px";
});
svg.addEventListener("mouseleave", () => tip.style.display = "none");

// own weight by points
const W = [0, 10, 30, 100, 300, 1000, 10000];
document.getElementById("weights").innerHTML =
  `<thead><tr><th>Точок MODIS у квадраті за місяць (усі навчальні роки)</th>${W.map(n => `<th>${int(n)}</th>`).join("")}</tr></thead><tbody>` +
  `<tr><td>Скільки важить «своє» число квадрата</td>${W.map(n => `<td>${pct(n / (n + D.lambda))}</td>`).join("")}</tr>` +
  `<tr><td>Скільки важить число країни</td>${W.map(n => `<td>${pct(D.lambda / (n + D.lambda))}</td>`).join("")}</tr></tbody>`;

// worked example
const E = D.example;
document.getElementById("exlead").innerHTML = `Навчальні роки 2012–2016. У серпні по всій Україні VIIRS дав ${int(E.viirs)} точок, MODIS — ${int(E.modis)}.
  <b>Число країни = ${num(E.k_country)}</b>. Ось чотири квадрати:`;
document.getElementById("example").innerHTML =
  `<thead><tr><th>Квадрат</th><th>MODIS</th><th>VIIRS</th><th>«Своє» число</th><th>Вага свого</th><th>Число №15</th></tr></thead><tbody>` +
  E.cells.map(c => `<tr><td>шир. ${c.lat}…${c.lat + 2}°, довг. ${c.lon}…${c.lon + 2}°</td><td>${int(c.m)}</td><td>${int(c.v)}</td>` +
    `<td>${num(c.own)}</td><td>${pct(c.w)}</td><td class="hl">${num(c.k15)}</td></tr>`).join("") + `</tbody>`;

// poor cells
document.getElementById("poor").innerHTML =
  `<thead><tr><th>Квадрат × місяць, де точок MODIS</th><th>частка таких квадратів × місяців</th><th>частка всіх точок у них</th></tr></thead><tbody>` +
  D.poor.map(p => `<tr><td>менше ${int(p.lim)}</td><td>${pct(p.share)}</td><td>${pct(p.points, 1)}</td></tr>`).join("") + `</tbody>`;
document.getElementById("nrows").textContent = int(D.n_cell_months);
})();
</script>
</body>
</html>
"""
html = (html.replace("__DATA__", json.dumps(payload, ensure_ascii=False)).replace("__LAMBDA__", str(LAMBDA))
        .replace("__Y0__", str(g["years"][0])).replace("__Y1__", str(g["years"][1]))
        .replace("__NY__", str(g["years"][1] - g["years"][0] + 1)))
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(html)
print("wrote", OUT)
print("example:", json.dumps(example, ensure_ascii=False))
