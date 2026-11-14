#!/usr/bin/env python3
"""Build a self-contained HTML page from the output of square_stability.py: is the factor of a square and calendar
month the same in every year, for six square sizes, and what error a person would see on fixed areas.

Usage: python3 -I make_size_page.py <square_stability.json> <out.html>
"""
import json
import sys

SRC, OUT = sys.argv[1], sys.argv[2]
data = json.load(open(SRC, encoding="utf-8"))
UA = {"Ukraine": "Україна", "Brazil": "Бразилія", "Australia": "Австралія"}
payload = {"data": data, "ua": UA, "keys": [str(float(x)) for x in data["sizes"]]}

html = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Розмір квадрата: чи однаковий множник з року в рік</title>
<style>
  :root {
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6f6e69;
    --grid: #e6e5e0; --rule: #b9b8b1; --best: #e3eefb;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
    --c-same: #52514e; --c-real: #9d9c93; --c-chance: #d6d5cf; --c-few: #ecebe6; --c-same-text: #fcfcfb;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9d9c93;
      --grid: #2e2e2c; --rule: #5a5955; --best: #1c3350;
      --s1: #3987e5; --s2: #d95926; --s3: #199e70;
      --c-same: #e6e5e0; --c-real: #8a897f; --c-chance: #4a4a46; --c-few: #2e2e2c; --c-same-text: #1a1a19;
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
  .row3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--ink-2); margin: 0 0 10px; }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; flex: none; }
  .ln { width: 16px; height: 3px; border-radius: 2px; display: inline-block; }
  svg { display: block; width: 100%; height: auto; }
  .axis text { fill: var(--ink-3); font-size: 11.5px; font-variant-numeric: tabular-nums; }
  .grid line { stroke: var(--grid); }
  table { border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; }
  th, td { padding: 5px 8px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--ink-2); font-weight: 600; vertical-align: bottom; }
  td.hl { background: var(--best); font-weight: 650; border-radius: 4px; }
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
  <h1>Розмір квадрата: чи однаковий множник з року в рік</h1>
  <p class="lead">Для кожного квадрата й календарного місяця рахуємо множник окремо за кожен рік 2012–2022 і порівнюємо його
  з множником, вивченим на інших 10 роках. «Однаковий» — якщо типова зміна між роками не більша за 10%.
  Шість розмірів квадрата, три країни.</p>

  <div class="tiles" id="tiles"></div>

  <h2>1. Яка частка пожеж має «однаковий» множник</h2>
  <p>Кожна смуга — усі пожежі (точки VIIRS) країни, поділені за тим, як поводиться множник їхнього квадрата й місяця.</p>
  <div class="card">
    <div class="legend">
      <span><i class="sw" style="background:var(--c-same)"></i>однаковий: змінюється не більше ніж на 10%</span>
      <span><i class="sw" style="background:var(--c-real)"></i>справді змінюється між роками</span>
      <span><i class="sw" style="background:var(--c-chance)"></i>не видно: пожеж замало, розкид як від випадковості</span>
      <span><i class="sw" style="background:var(--c-few);outline:1px solid var(--rule)"></i>пожежі лише в 1–2 роках</span>
    </div>
    <div class="row3" id="stacks"></div>
  </div>

  <h2>2. Наскільки множник гуляє між роками</h2>
  <p>Типова зміна множника квадрата за місяць між роками (половина пожеж — у квадратах з меншою зміною). Пунктир — твій поріг 10%.</p>
  <div class="card">
    <div class="legend" id="legend2"></div>
    <svg id="change" viewBox="0 0 900 300" role="img" aria-label="Типова зміна множника за розміром квадрата"></svg>
  </div>

  <h2>3. Яку помилку побачить людина</h2>
  <p>Інше питання: не чи стабільний множник, а наскільки точно вийде число для місця. Кожен рік вгадуємо множниками,
  вивченими на інших 10 роках, і перевіряємо на однакових областях. Тоді квадрати різних розмірів порівнюються чесно.</p>
  <div class="row3">
    <div class="card"><h3>Області ~55 км (0,5°)</h3><div class="legend" id="legend3a"></div>
      <svg id="err05" viewBox="0 0 440 260" role="img" aria-label="Помилка на областях 0,5° за розміром квадрата"></svg></div>
    <div class="card"><h3>Області ~220 км (2°)</h3><div class="legend" id="legend3b"></div>
      <svg id="err2" viewBox="0 0 440 260" role="img" aria-label="Помилка на областях 2° за розміром квадрата"></svg></div>
  </div>
  <p class="muted" style="margin-top:8px">Типова помилка за місяць по областях, де VIIRS дав 100+ точок. Обведена точка — найменша помилка для країни.</p>

  <h2>4. Усі числа</h2>
  <div class="card"><table id="table"></table></div>

  <h2>Як рахували</h2>
  <ol>
    <li>Точки Aqua (MODIS) і Suomi NPP (VIIRS) з файлів країн архіву FIRMS, <code>type = 0</code>, 2012–2022.</li>
    <li>Квадрати нарізані з усього глобуса: рядок = ⌊(широта + 90) / розмір⌋, стовпчик = ⌊(довгота + 180) / розмір⌋.
      Квадрати різних розмірів вкладаються один в одного.</li>
    <li>Для квадрата, календарного місяця m і року y: множник року k<sub>y</sub> = V<sub>y</sub> / M<sub>y</sub>;
      множник решти K = (сума V за інші 10 років) / (сума M за них); зміна = |k<sub>y</sub> / K − 1|.
      Типова зміна квадрата-місяця — медіана по роках. Потрібні точки MODIS хоча б у 3 роках.</li>
    <li>Скільки розкиду дає сама випадковість: √(1/M<sub>y</sub> + 1/V<sub>y</sub> + 1/M<sub>решти</sub> + 1/V<sub>решти</sub>);
      типова зміна від випадковості — 0,674 × її медіана. «Справді змінюється» — зміна понад 10% і понад 1,5 × випадкову.</li>
    <li>Помилка для людини: кожен рік кожної клітинки 0,25° вгадується множником її квадрата, вивченим на інших 10 роках
      (якщо в інших роках MODIS там нічого не бачив — множником усієї країни на цей місяць); суми по областях 0,5° і 2°
      порівнюються зі справжнім VIIRS.</li>
    <li>Дрейф: щороку справжні точки VIIRS ділимо на те, що очікують множники за всі роки; тренд цього ряду — у відсотках на рік.</li>
  </ol>

  <h2>Висновок (ще не рішення)</h2>
  <ul id="concl"></ul>

  <h2>Як відтворити</h2>
  <p>Скрипти поруч: <code>square_stability.py</code> (розрахунок) і <code>make_size_page.py</code> (ця сторінка). Вхід — вирізані файли
  трьох країн (<code>extract.py</code>). Сирі числа — <code>square_stability.json</code>.</p>
</main>
<div class="tip" id="tip"></div>
<script>
(() => {
const P = __DATA__, D = P.data, C = Object.keys(D.countries), SZ = P.keys;
const COLOR = {Ukraine: "--s1", Brazil: "--s2", Australia: "--s3"};
const pct = (x, d = 0) => x == null ? "—" : (x * 100).toFixed(d).replace(".", ",") + "%";
const deg = s => (+s).toString().replace(".", ",") + "°";
const KM = {"0.25": "~28 км", "0.5": "~55 км", "1.0": "~110 км", "2.0": "~220 км", "4.0": "~440 км", "8.0": "~900 км"};
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tip = document.getElementById("tip");
const R = (c, s) => D.countries[c][s];
const NS = "http://www.w3.org/2000/svg";
const el = (tag, a, p) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); p.appendChild(e); return e; };
const showTip = (ev, html) => { tip.innerHTML = html; tip.style.display = "block"; tip.style.left = (ev.clientX + 14) + "px"; tip.style.top = (ev.clientY + 14) + "px"; };
const hideTip = () => tip.style.display = "none";
const best = (c, q) => SZ.reduce((b, s) => R(c, s).area_error[q].error < R(c, b).area_error[q].error ? s : b, SZ[0]);

// tiles
const same8 = C.map(c => pct(R(c, "8.0").share_same)).join(" / ");
const same2 = C.map(c => pct(R(c, "2.0").share_same)).join(" / ");
const drift = C.map(c => (R(c, "2.0").drift.per_year * 100).toFixed(1).replace(".", ",")).join(" / ");
document.getElementById("tiles").innerHTML = `
  <div class="tile"><div class="k">Ідеал «±10% в усі роки»</div><div class="v">лише у великих квадратах і лише для частини пожеж</div>
    <div class="s">квадрат 8°: ${same8} пожеж; квадрат 2°: ${same2} (Україна / Бразилія / Австралія)</div></div>
  <div class="tile"><div class="k">Для точності на місцях</div><div class="v">розмір майже не важить, найкраще ~2°</div>
    <div class="s">2° — найкращий або гірший за найкращий щонайбільше на 0,5 пункту для всіх трьох країн і обох розмірів областей</div></div>
  <div class="tile"><div class="k">Дрейф з роками</div><div class="v">малий: ${drift}% на рік</div>
    <div class="s">квадрат 2°; за 10 років назад це ~2–5% зсуву</div></div>`;

// stacked bars per country
document.getElementById("stacks").innerHTML = C.map(c => `<div><h3>${P.ua[c]}</h3>` + SZ.map(s => { const r = R(c, s);
  const seg = (v, bg, fg) => `<div style="width:${v * 100}%;background:var(${bg});color:var(${fg});display:flex;align-items:center;justify-content:center;font-size:11.5px;overflow:hidden;white-space:nowrap">${v >= 0.09 ? pct(v) : ""}</div>`;
  return `<div style="display:grid;grid-template-columns:70px 1fr;gap:8px;align-items:center;margin:5px 0"><div style="font-size:12.5px;color:var(--ink-2)">${deg(s)} <span style="color:var(--ink-3)">${KM[s]}</span></div>` +
    `<div style="display:flex;height:24px;gap:1px;border-radius:4px;overflow:hidden">` +
    seg(r.share_same, "--c-same", "--c-same-text") + seg(r.share_real, "--c-real", "--ink") + seg(r.share_chance, "--c-chance", "--ink") + seg(r.share_few, "--c-few", "--ink") +
    `</div></div>`; }).join("") + `</div>`).join("");

// line chart helper
function lines(svg, W, H, getY, ymax, tipFn, refLine, markBest) {
  svg.innerHTML = "";
  const L = 46, Rr = 30, T = 12, B = 34;
  const x = i => L + i * (W - L - Rr) / (SZ.length - 1), y = v => T + (1 - v / ymax) * (H - T - B);
  const g = el("g", {class: "grid"}, svg), ax = el("g", {class: "axis"}, svg);
  for (let k = 0; k <= 5; k++) { const v = ymax * k / 5; el("line", {x1: L, x2: W - Rr, y1: y(v), y2: y(v)}, g);
    el("text", {x: L - 6, y: y(v) + 4, "text-anchor": "end"}, ax).textContent = Math.round(v * 100) + "%"; }
  SZ.forEach((s, i) => { el("text", {x: x(i), y: H - B + 16, "text-anchor": "middle"}, ax).textContent = deg(s);
    el("text", {x: x(i), y: H - B + 29, "text-anchor": "middle", "font-size": 10}, ax).textContent = KM[s]; });
  if (refLine != null) el("line", {x1: L, x2: W - Rr, y1: y(refLine), y2: y(refLine), stroke: css("--ink-2"), "stroke-dasharray": "4 4"}, svg);
  for (const c of C) {
    const col = css(COLOR[c]);
    el("path", {d: SZ.map((s, i) => (i ? "L" : "M") + x(i) + "," + y(getY(c, s))).join(""), fill: "none", stroke: col, "stroke-width": 2}, svg);
    const bs = markBest ? markBest(c) : null;
    SZ.forEach((s, i) => {
      const dot = el("circle", {cx: x(i), cy: y(getY(c, s)), r: s === bs ? 6 : 4, fill: s === bs ? css("--surface") : col,
                                stroke: s === bs ? col : css("--surface"), "stroke-width": s === bs ? 2.5 : 1.5}, svg);
      const hit = el("circle", {cx: x(i), cy: y(getY(c, s)), r: 11, fill: "transparent"}, svg);
      hit.addEventListener("mousemove", ev => showTip(ev, tipFn(c, s)));
      hit.addEventListener("mouseleave", hideTip);
    });
  }
}
const legend = C.map(c => `<span><i class="ln" style="background:var(${COLOR[c]})"></i>${P.ua[c]}</span>`).join("");
for (const id of ["legend2", "legend3a", "legend3b"]) document.getElementById(id).innerHTML = legend;
function drawAll() {
  lines(document.getElementById("change"), 900, 300, (c, s) => R(c, s).typical_change, 0.5,
    (c, s) => `<b>${P.ua[c]}, квадрат ${deg(s)}</b><br>типова зміна між роками: ${pct(R(c, s).typical_change, 1)}<br>однаковий множник: ${pct(R(c, s).share_same, 1)} пожеж`, 0.10, null);
  for (const [id, q] of [["err05", "0.5"], ["err2", "2.0"]])
    lines(document.getElementById(id), 440, 260, (c, s) => R(c, s).area_error[q].error, 0.3,
      (c, s) => `<b>${P.ua[c]}, квадрат ${deg(s)}</b><br>помилка на областях ${deg(q)}: ${pct(R(c, s).area_error[q].error, 1)}`, null, c => best(c, q));
}
drawAll();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawAll);

// table
document.getElementById("table").innerHTML =
  `<thead><tr><th>Країна, квадрат</th><th>квадратів</th><th>квадрат ×<br>місяць</th><th>однаковий</th><th>справді<br>змінюється</th><th>не видно</th><th>1–2 роки</th>` +
  `<th>типова<br>зміна</th><th>помилка,<br>області 0,5°</th><th>помилка,<br>області 2°</th><th>дрейф<br>на рік</th></tr></thead><tbody>` +
  C.map(c => SZ.map(s => { const r = R(c, s), b05 = best(c, "0.5"), b2 = best(c, "2.0");
    return `<tr><td>${P.ua[c]}, ${deg(s)}</td><td>${r.squares.toLocaleString("uk-UA")}</td><td>${r.square_months.toLocaleString("uk-UA")}</td>` +
      `<td>${pct(r.share_same, 1)}</td><td>${pct(r.share_real, 1)}</td><td>${pct(r.share_chance, 1)}</td><td>${pct(r.share_few, 1)}</td>` +
      `<td>${pct(r.typical_change, 1)}</td><td class="${s === b05 ? "hl" : ""}">${pct(r.area_error["0.5"].error, 1)}</td>` +
      `<td class="${s === b2 ? "hl" : ""}">${pct(r.area_error["2.0"].error, 1)}</td><td>${(r.drift.per_year * 100).toFixed(1).replace(".", ",")}%</td></tr>`; }).join("")).join("") + `</tbody>`;

// conclusions
const tc = s => C.map(c => pct(R(c, s).typical_change)).join(" / ");
document.getElementById("concl").innerHTML = `
  <li><b>Ідеал «±10% в усі роки» досягається лише частково.</b> Навіть у квадратах 8° однаковий множник мають лише
    ${same8} пожеж (Україна / Бразилія / Австралія). Типова зміна між роками: 0,25° — ${tc("0.25")}, 2° — ${tc("2.0")}, 8° — ${tc("8.0")}.</li>
  <li><b>У малих квадратах зміни здебільшого випадкові:</b> там замало пожеж, щоб побачити, однаковий множник чи ні.</li>
  <li><b>У великих квадратах решта змін справжня:</b> множник того самого квадрата й місяця справді гуляє між роками,
    бо щороку інша суміш пожеж (більше дрібних чи більше великих). Це межа точності будь-якої гармонізації.</li>
  <li><b>Для точності на місцях розмір майже не важить.</b> Найкраще ~2°: найкращий або майже найкращий для всіх трьох
    країн. Більший квадрат стабільніший, але гірше знає місцеві пожежі, тому точніше не стає.</li>
  <li><b>Дрейф малий</b> (${drift}% на рік), тож множники 2012–2022 можна застосовувати до 2002–2011.</li>`;
})();
</script>
</body>
</html>
"""
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(html.replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
print("wrote", OUT)
