#!/usr/bin/env python3
"""Build a self-contained HTML page: what the same power bar (approach 5) loses — VIIRS points by night and weak by
day, fire events it never sees by their duration, how well the bar predicts all fires, and two factors at once.

Usage: python3 -I make_bar_page.py <bar_events_gap1.json> <bar_events_gap2.json> <bar_to_all.json> <results.json>
       <split_approach.json> <out.html>
"""
import json
import sys

G1, G2, TOALL, RESULTS, SPLIT, OUT = sys.argv[1:7]
gap1 = json.load(open(G1, encoding="utf-8"))["countries"]
gap2 = json.load(open(G2, encoding="utf-8"))["countries"]
toall = json.load(open(TOALL, encoding="utf-8"))
res = json.load(open(RESULTS, encoding="utf-8"))["countries"]
split = json.load(open(SPLIT, encoding="utf-8"))
UA = {"Ukraine": "Україна", "Brazil": "Бразилія", "Australia": "Австралія"}
payload = {
    "ua": UA, "gap1": gap1, "gap2": gap2, "toall": toall, "split": split,
    "own5": {c: {"err": res[c]["results"]["5"]["err"], "cal": res[c]["results"]["5"]["cal"]} for c in res},
}

html = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Що губить однакова планка (№5)</title>
<style>
  :root {
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6f6e69;
    --grid: #e6e5e0; --rule: #b9b8b1; --best: #e3eefb;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
    --part1: #52514e; --part2: #b9b8b1; --part3: #e6e5e0; --part1-text: #fcfcfb;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9d9c93;
      --grid: #2e2e2c; --rule: #5a5955; --best: #1c3350;
      --s1: #3987e5; --s2: #d95926; --s3: #199e70;
      --part1: #c3c2b7; --part2: #6f6e69; --part3: #383835; --part1-text: #1a1a19;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--ink);
         font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 1000px; margin: 0 auto; padding: 32px 20px 56px; }
  h1 { font-size: 28px; line-height: 1.25; margin: 0 0 10px; }
  h2 { font-size: 21px; margin: 40px 0 10px; }
  p { margin: 0 0 12px; max-width: 76ch; }
  .lead { font-size: 18px; color: var(--ink-2); }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin: 24px 0; }
  .tile, .card { background: var(--surface); border: 1px solid var(--grid); border-radius: 12px; }
  .tile { padding: 14px 16px; }
  .tile .k { font-size: 13px; color: var(--ink-2); display: flex; align-items: center; gap: 8px; }
  .tile .v { font-size: 30px; font-weight: 650; margin-top: 2px; font-variant-numeric: tabular-nums; }
  .tile .s { font-size: 13px; color: var(--ink-3); margin-top: 2px; }
  .card { padding: 16px 18px; position: relative; overflow-x: auto; }
  .sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; flex: none; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13.5px; color: var(--ink-2); margin: 0 0 12px; }
  .legend span { display: inline-flex; align-items: center; gap: 7px; }
  .stack-row { display: grid; grid-template-columns: 100px 1fr; align-items: center; gap: 12px; margin: 8px 0; }
  .stack-row .c { font-size: 14px; color: var(--ink-2); }
  .stack { display: flex; height: 34px; gap: 2px; }
  .stack div { display: flex; align-items: center; justify-content: center; font-size: 13px; font-variant-numeric: tabular-nums;
               white-space: nowrap; overflow: hidden; }
  .stack div:first-child { border-radius: 4px 0 0 4px; }
  .stack div:last-child { border-radius: 0 4px 4px 0; }
  svg { display: block; width: 100%; height: auto; }
  .axis text { fill: var(--ink-3); font-size: 12px; font-variant-numeric: tabular-nums; }
  .grid line { stroke: var(--grid); }
  .val { fill: var(--ink-2); font-size: 11.5px; font-variant-numeric: tabular-nums; }
  table { border-collapse: collapse; width: 100%; font-size: 13.5px; font-variant-numeric: tabular-nums; }
  th, td { padding: 6px 9px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--ink-2); font-weight: 600; vertical-align: bottom; }
  td.hl { background: var(--best); font-weight: 650; border-radius: 4px; }
  ul, ol { padding-left: 22px; max-width: 80ch; }
  li { margin-bottom: 6px; }
  code { font-size: 13.5px; }
  .muted { color: var(--ink-3); font-size: 13.5px; }
  .tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--grid);
         border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.16); padding: 7px 10px; font-size: 12.5px; display: none; z-index: 5; }
</style>
</head>
<body>
<main>
  <h1>Що губить однакова планка (№5)</h1>
  <p class="lead">Планка лишає тільки денні точки VIIRS у клітинках ~1 км, які за один проліт набрали 10 МВт і більше.
  Питання: скільки пожеж вона не бачить зовсім, і чи це лише короткі пожежі. VIIRS Suomi NPP, пожежі на рослинності
  (<code>type = 0</code>), 2012–2022.</p>

  <div class="tiles" id="tiles"></div>

  <h2>1. Які точки викидає планка</h2>
  <div class="card">
    <div class="legend">
      <span><i class="sw" style="background:var(--part1)"></i>лишаються: день, клітинка ≥ 10 МВт</span>
      <span><i class="sw" style="background:var(--part2)"></i>викинуті: день, слабше 10 МВт</span>
      <span><i class="sw" style="background:var(--part3);outline:1px solid var(--rule)"></i>викинуті: ніч</span>
    </div>
    <div id="stacks"></div>
  </div>
  <p class="muted" style="margin-top:8px">В Україні планка викидає найбільше не через ніч, а через слабкі денні вогні.</p>

  <h2>2. Скільки пожеж планка бачить хоча б раз</h2>
  <p>Пожежа — це точки в сусідніх клітинках ~1 км у сусідні дні (як збирали — у розділі 6). Пожежу «видно», якщо хоча б одна
  її точка пройшла планку. Стовпчик — частка пожеж такої тривалості, які планка побачила.</p>
  <div class="card">
    <div class="legend" id="clegend"></div>
    <svg id="bars" viewBox="0 0 900 340" role="img" aria-label="Частка пожеж, які бачить планка, за тривалістю"></svg>
  </div>
  <div class="card" style="margin-top:12px"><table id="dur"></table></div>
  <p class="muted" style="margin-top:8px">«Частка пожеж» і «частка точок» — від усіх пожеж і всіх точок країни.</p>

  <h2>3. Чи це лише короткі пожежі</h2>
  <ul id="short"></ul>

  <h2>4. А якщо планкою вгадувати всі пожежі</h2>
  <p>Твоя ідея: планка ловить пожежу, а показуємо всю активність. Тоді сильні денні точки MODIS треба перераховувати в
  <b>усі</b> точки VIIRS. Порівняння на тих самих роках і критеріях, що й 14 підходів:</p>
  <div class="card"><table id="toall"></table></div>
  <p class="muted" style="margin-top:8px">Точність №5 — це точність для сильних денних пожеж. Для всіх пожеж сигнал планки не кращий за простий №2.</p>

  <h2>5. А якщо два способи разом</h2>
  <p>Ідея: сильні денні точки перераховувати одним множником, а короткі й нічні — іншим. Але до 2012 року є лише MODIS,
  тож ділити можна тільки точки MODIS. А короткі слабкі й нічні пожежі — це саме те, чого MODIS майже не бачить.</p>
  <div class="card"><table id="shares"></table></div>
  <p class="muted" style="margin-top:8px">Планка викидає лише 20–32% точок MODIS, але 53–66% точок VIIRS: різниця між датчиками
  сидить саме в слабких і нічних вогнях.</p>
  <p>Спробували два гібриди, нічого не викидаючи: окремий множник для сильних денних точок MODIS і для решти; окремий
  множник для дня й для ночі. Усі вгадують усі точки VIIRS, на тих самих роках і критеріях:</p>
  <div class="card"><table id="split"></table></div>
  <p class="muted" style="margin-top:8px">Другий множник множить мало точок MODIS на велике число (в Україні «решта» — 32% точок MODIS
  проти 66% точок VIIRS, множник ~12), тому шум зростає. У Бразилії гібрид трохи кращий, в Україні значно гірший.</p>

  <h2>6. Як рахували</h2>
  <ol>
    <li>Точки VIIRS Suomi NPP з файлів країн архіву FIRMS, <code>type = 0</code>, 2012–2022.</li>
    <li>Планка — як у №5: денні точки одного прольоту (новий проліт — пауза понад 20 хвилин) склеюються в клітинки
      ~1 км (0,01° широти × 0,01°/cos(широти) довготи); точка лишається, якщо її клітинка за проліт набрала ≥ 10 МВт.</li>
    <li>Пожежа: дві точки належать одній пожежі, якщо їхні клітинки ~1 км збігаються або торкаються (8 сусідів) і між
      їхніми днями не більше доби. День — за місцевим сонячним часом, щоб нічний проліт (~01:30) і денний (~13:30)
      не розпадались на різні дати. Зв'язки йдуть ланцюжком: A–B і B–C дають одну пожежу A–B–C.</li>
    <li>Тривалість — скільки різних днів між першою й останньою точкою пожежі.</li>
    <li>Перевірка правила: з «до двох діб» замість «до доби» числа майже ті самі (<span id="gapnote"></span>).</li>
  </ol>
  <p class="muted">Ланцюжок може злити сусідні поля, що горіли день за днем, в одну «пожежу». Це робить пожежі довшими й
  більшими, тобто грає на користь планки; справжня частка пропущених пожеж може бути трохи більшою.</p>

  <h2>Висновок (ще не рішення)</h2>
  <ul>
    <li><b>Гіпотеза «довга пожежа все одно з'явиться вдень із силою від 10 МВт»</b> справджується в Бразилії й Австралії:
      пожежі від 4 днів планка бачить у 92–99% випадків. В Україні — лише у 67–73%, бо українські пожежі слабкі.</li>
    <li><b>Коротких пожеж дуже багато.</b> Пожежі одного дня — це 74–92% усіх пожеж. Планка бачить лише кожну третю-четверту з них.</li>
    <li><b>Допуск «лише для некоротких пожеж» по-різному коштує різним країнам.</b> В Австралії планка пропускає пожежі з 9%
      точок — це прийнятно. У Бразилії 25%. В Україні 48%: там короткі пожежі (палять поля) і є основна частина горіння.</li>
    <li><b>Гібрид не допомагає.</b> Окремий множник для сильних денних точок MODIS і для решти дає в Україні помилку 21% проти 12%
      в одного множника на місяць: решту пожеж MODIS майже не бачить, тож її можна додати лише в середньому.</li>
    <li>Тому для головного календаря, який показує всі пожежі, планка не годиться. Її можна дати окремим шаром «сильні
      денні пожежі»: там її точність чесна.</li>
  </ul>

  <h2>Як відтворити</h2>
  <p>Скрипти поруч: <code>bar_events.py</code> (точки й пожежі), <code>bar_to_all.py</code> (планка → усі пожежі),
  <code>split_approach.py</code> (два множники разом),
  <code>make_bar_page.py</code> (ця сторінка). Вхід — ті самі вирізані файли, що й для 14 підходів (<code>extract.py</code>).
  Сирі числа — <code>bar_events_gap1.json</code>, <code>bar_events_gap2.json</code>, <code>bar_to_all.json</code>, <code>split_approach.json</code>.</p>
</main>
<div class="tip" id="tip"></div>
<script>
(() => {
const D = __DATA__;
const C = Object.keys(D.gap1);
const COLOR = {Ukraine: "--s1", Brazil: "--s2", Australia: "--s3"};
const pct = (x, d = 0) => x == null ? "—" : (x * 100).toFixed(d).replace(".", ",") + "%";
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tip = document.getElementById("tip");

document.getElementById("tiles").innerHTML = C.map(c => { const g = D.gap1[c]; return `
  <div class="tile"><div class="k"><i class="sw" style="background:var(${COLOR[c]})"></i>${D.ua[c]}: планка не бачить</div>
    <div class="v">${pct(1 - g.seen_events)} пожеж</div>
    <div class="s">у цих пожежах ${pct(g.lost_points)} усіх точок VIIRS; з них ${pct(g.lost_single_point)} — одна точка</div></div>`; }).join("");

document.getElementById("stacks").innerHTML = C.map(c => { const g = D.gap1[c];
  const seg = (v, bg, fg) => `<div style="width:${v * 100}%;background:var(${bg});color:var(${fg})">${v >= 0.06 ? pct(v) : ""}</div>`;
  return `<div class="stack-row"><div class="c">${D.ua[c]}</div><div class="stack">` +
    seg(g.kept, "--part1", "--part1-text") + seg(g.day_weak, "--part2", "--ink") + seg(g.night, "--part3", "--ink") + `</div></div>`; }).join("");

// grouped bars: share of events seen, by duration
document.getElementById("clegend").innerHTML = C.map(c => `<span><i class="sw" style="background:var(${COLOR[c]})"></i>${D.ua[c]}</span>`).join("");
const svg = document.getElementById("bars"), NS = "http://www.w3.org/2000/svg";
const el = (tag, a, p = svg) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); p.appendChild(e); return e; };
function bars() {
  svg.innerHTML = "";
  const W = 900, H = 340, L = 50, R = 10, T = 16, B = 40, groups = D.gap1[C[0]].by_duration.map(b => b.label);
  const y = v => T + (1 - v) * (H - T - B);
  const g = el("g", {class: "grid"}), ax = el("g", {class: "axis"});
  for (let v = 0; v <= 1.0001; v += 0.25) { el("line", {x1: L, x2: W - R, y1: y(v), y2: y(v)}, g);
    el("text", {x: L - 8, y: y(v) + 4, "text-anchor": "end"}, ax).textContent = Math.round(v * 100) + "%"; }
  const gw = (W - L - R) / groups.length, bw = Math.min(56, (gw - 40) / C.length);
  groups.forEach((label, gi) => {
    const x0 = L + gi * gw + (gw - bw * C.length - 2 * (C.length - 1)) / 2;
    el("text", {x: L + gi * gw + gw / 2, y: H - B + 24, "text-anchor": "middle"}, ax).textContent = label;
    C.forEach((c, ci) => {
      const b = D.gap1[c].by_duration[gi], v = b.seen ?? 0, x = x0 + ci * (bw + 2);
      const r = el("path", {d: `M${x},${y(0)} V${y(v) + 4} Q${x},${y(v)} ${x + 4},${y(v)} H${x + bw - 4} Q${x + bw},${y(v)} ${x + bw},${y(v) + 4} V${y(0)} Z`,
                            fill: css(COLOR[c])});
      el("text", {x: x + bw / 2, y: y(v) - 5, "text-anchor": "middle", class: "val"}).textContent = pct(v);
      r.addEventListener("mousemove", ev => {
        tip.innerHTML = `<b>${D.ua[c]}, ${label}</b><br>планка бачить ${pct(v, 1)} таких пожеж<br>це ${pct(b.share_events, 1)} усіх пожеж і ${pct(b.share_points, 1)} усіх точок`;
        tip.style.display = "block"; tip.style.left = (ev.clientX + 14) + "px"; tip.style.top = (ev.clientY + 14) + "px"; });
      r.addEventListener("mouseleave", () => tip.style.display = "none");
    });
  });
}
bars();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", bars);

// duration table
const groups = D.gap1[C[0]].by_duration.map(b => b.label);
document.getElementById("dur").innerHTML =
  `<thead><tr><th>Тривалість</th>${C.map(c => `<th colspan="3" style="text-align:center">${D.ua[c]}</th>`).join("")}</tr>` +
  `<tr><th></th>${C.map(() => `<th>частка<br>пожеж</th><th>частка<br>точок</th><th>планка<br>бачить</th>`).join("")}</tr></thead><tbody>` +
  groups.map((label, gi) => `<tr><td>${label}</td>` + C.map(c => { const b = D.gap1[c].by_duration[gi];
    return `<td>${pct(b.share_events, 1)}</td><td>${pct(b.share_points, 1)}</td><td>${pct(b.seen, 1)}</td>`; }).join("") + `</tr>`).join("") +
  `<tr><td><b>Усі</b></td>` + C.map(c => { const g = D.gap1[c];
    return `<td>100%</td><td>100%</td><td><b>${pct(g.seen_events, 1)}</b></td>`; }).join("") + `</tr></tbody>`;

// short fires
const one = c => D.gap1[c].by_duration[0];
const longSeen = c => { const b = D.gap1[c].by_duration; return [b[2].seen, b[3].seen]; };
document.getElementById("short").innerHTML = C.map(c => { const o = one(c), ls = longSeen(c), g = D.gap1[c]; return `
  <li><b>${D.ua[c]}.</b> Пожежі одного дня — ${pct(o.share_events)} усіх пожеж і ${pct(o.share_points)} усіх точок; планка бачить
  ${pct(o.seen)} з них. Пожежі від 4 днів планка бачить у ${pct(ls[0])}–${pct(ls[1])} випадків. Разом планка пропускає
  пожежі, у яких ${pct(g.lost_points)} точок.</li>`; }).join("");

// bar to all fires
document.getElementById("toall").innerHTML =
  `<thead><tr><th>Що чим вгадуємо</th>${C.map(c => `<th colspan="2" style="text-align:center">${D.ua[c]}</th>`).join("")}</tr>` +
  `<tr><th></th>${C.map(() => `<th>помилка</th><th>календар</th>`).join("")}</tr></thead><tbody>` +
  `<tr><td>№2: усі точки MODIS → усі точки VIIRS</td>${C.map(c => `<td>${pct(D.toall[c].all.err, 1)}</td><td>${pct(D.toall[c].all.cal, 1)}</td>`).join("")}</tr>` +
  `<tr><td>Планка MODIS → <b>усі</b> точки VIIRS</td>${C.map(c => `<td>${pct(D.toall[c].bar.err, 1)}</td><td>${pct(D.toall[c].bar.cal, 1)}</td>`).join("")}</tr>` +
  `<tr><td>№5: планка MODIS → планка VIIRS</td>${C.map(c => `<td>${pct(D.own5[c].err, 1)}</td><td>${pct(D.own5[c].cal, 1)}</td>`).join("")}</tr></tbody>`;

// shares of points and the two-factor variants
const sh = (o) => `<td>${pct(o.day_bar)}</td><td>${pct(o.day_weak)}</td><td>${pct(o.night)}</td>`;
document.getElementById("shares").innerHTML =
  `<thead><tr><th>Точки</th>${C.map(c => `<th colspan="3" style="text-align:center">${D.ua[c]}</th>`).join("")}</tr>` +
  `<tr><th></th>${C.map(() => `<th>день,<br>≥ 10 МВт</th><th>день,<br>слабші</th><th>ніч</th>`).join("")}</tr></thead><tbody>` +
  `<tr><td>MODIS (Aqua)</td>${C.map(c => sh(D.split[c].modis_shares)).join("")}</tr>` +
  `<tr><td>VIIRS (Suomi NPP)</td>${C.map(c => sh(D.split[c].viirs_shares)).join("")}</tr></tbody>`;
const ROWS = [["all", "№2: один множник на місяць"], ["bar", "Лише планка (решту MODIS викидаємо)"],
              ["split", "Планка + решта, окремі множники"], ["daynight", "День + ніч, окремі множники"]];
document.getElementById("split").innerHTML =
  `<thead><tr><th>Як перераховуємо MODIS</th>${C.map(c => `<th colspan="2" style="text-align:center">${D.ua[c]}</th>`).join("")}</tr>` +
  `<tr><th></th>${C.map(() => `<th>помилка</th><th>календар</th>`).join("")}</tr></thead><tbody>` +
  ROWS.map(([k, label]) => `<tr><td>${label}</td>` + C.map(c => {
    const best = Math.min(...ROWS.map(([kk]) => D.split[c][kk].err));
    const s = D.split[c][k];
    return `<td class="${s.err === best ? "hl" : ""}">${pct(s.err, 1)}</td><td>${pct(s.cal, 1)}</td>`; }).join("") + `</tr>`).join("") + `</tbody>`;

document.getElementById("gapnote").textContent = C.map(c =>
  `${D.ua[c]}: планка бачить ${pct(D.gap1[c].seen_events, 1)} пожеж проти ${pct(D.gap2[c].seen_events, 1)}`).join("; ");
})();
</script>
</body>
</html>
"""
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(html.replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
print("wrote", OUT)
