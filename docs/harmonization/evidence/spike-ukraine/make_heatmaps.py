#!/usr/bin/env python3
"""Build a self-contained HTML page of colour tables: the MODIS -> VIIRS multiplier for every month of
every year. Two pages share the format:

  daynight  daytime passes and night-time passes apart, all vegetation-fire rows
  samebar   daytime passes: all rows, and only fires of 10+ MW on both sides
            (a MODIS row of 10+ MW; VIIRS rows glued into ~1 km cells per pass, cells of 10+ MW)

Usage: python3 -I make_heatmaps.py <folder with modis_*_Ukraine.csv and viirs-snpp_*_Ukraine.csv> <out.html> [daynight|samebar]
"""
import csv
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date

DATA, OUT = sys.argv[1], sys.argv[2]
PAGE = sys.argv[3] if len(sys.argv) > 3 else "daynight"
YEARS = list(range(2012, 2022))
BAR = 10.0  # MW
LAT0, LON0, DLAT, DLON, NLON = 43.0, 21.0, 0.01, 0.015, 2000  # ~1.1 km cells


def load(pattern: str, sat: str | None = None) -> tuple[Counter, Counter]:
    """Counts by (day/night, year, month): every row, and the strong ones.

    A strong MODIS unit is a row of BAR+ MW. A strong VIIRS unit is a ~1 km cell of one pass
    whose rows sum to BAR+ MW. Both functions return (rows, strong rows, strong cells)."""
    rows = []
    for path in sorted(glob.glob(os.path.join(DATA, pattern))):
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["type"] != "0" or (sat and r["satellite"] != sat):
                    continue
                y, m, d = int(r["acq_date"][:4]), int(r["acq_date"][5:7]), int(r["acq_date"][8:10])
                if y not in YEARS:
                    continue
                t = int(r["acq_time"])
                minute = date(y, m, d).toordinal() * 1440 + (t // 100) * 60 + t % 100
                cell = int((float(r["latitude"]) - LAT0) / DLAT) * NLON + int((float(r["longitude"]) - LON0) / DLON)
                rows.append((minute, cell, r["daynight"], y, m, float(r["frp"] or 0)))
    every: Counter = Counter()
    strong_rows: Counter = Counter()
    for _, _, dn, y, m, frp in rows:
        every[dn, y, m] += 1
        if frp >= BAR:
            strong_rows[dn, y, m] += 1
    pid, n, last = {}, -1, -10**12
    for t in sorted({r[0] for r in rows}):
        if t - last > 20:
            n += 1
        pid[t] = n
        last = t
    cells: dict[tuple[int, int], list] = defaultdict(lambda: [0.0, None])
    for minute, cell, dn, y, m, frp in rows:
        c = cells[pid[minute], cell]
        c[0] += frp
        c[1] = (dn, y, m)
    strong_cells: Counter = Counter(key for total, key in cells.values() if total >= BAR)
    return every, strong_rows, strong_cells


a_all, a_strong, _ = load("modis_*_Ukraine.csv", "Aqua")
s_all, _, s_strong = load("viirs-snpp_*_Ukraine.csv")


def table(a: Counter, s: Counter, dn: str) -> dict:
    return {"aqua": {str(y): [a[dn, y, m] for m in range(1, 13)] for y in YEARS},
            "snpp": {str(y): [s[dn, y, m] for m in range(1, 13)] for y in YEARS}}


BLUE = {"cls": "q"}
ORANGE = {"cls": "n"}
if PAGE == "daynight":
    title = "Удень множник тримається від 3 до 8 з року в рік. Уночі MODIS майже не дає з чого рахувати"
    lede = ("Множник — це скільки точок нарахував VIIRS (Suomi NPP) на одну точку MODIS (Aqua) за той самий місяць над Україною. "
            "Дві таблиці одного формату: денні прольоти й нічні. Тільки пожежі рослинності, 2012–2021.")
    foot = "Дані: архів NASA FIRMS, Україна, рядки з type = 0. Колір дня й колір ночі — дві різні шкали: нічні числа приблизно вдесятеро більші."
    panels = [
        dict(BLUE, title="День", word="день", dec=1, edges=[4.5, 6, 8, 10], labels=["менше 4,5", "4,5–6", "6–8", "8–10", "10 і більше"], extra="",
             unit="точок VIIRS на одну точку MODIS", mLabel="точок MODIS (Aqua)", vLabel="точок VIIRS (Suomi NPP)",
             mTotal="Точок MODIS за 10 років", vTotal="Точок VIIRS за 10 років", data=table(a_all, s_all, "D")),
        dict(ORANGE, title="Ніч", word="ніч", dec=1, edges=[35, 45, 60, 90], labels=["менше 35", "35–45", "45–60", "60–90", "90 і більше"],
             extra=" Шкала тут інша, ніж удень: нічні числа приблизно вдесятеро більші.",
             unit="точок VIIRS на одну точку MODIS", mLabel="точок MODIS (Aqua)", vLabel="точок VIIRS (Suomi NPP)",
             mTotal="Точок MODIS за 10 років", vTotal="Точок VIIRS за 10 років", data=table(a_all, s_all, "N")),
    ]
else:
    title = "Якщо лишити тільки вогні від 10 МВт, обидва супутники рахують майже однаково"
    lede = ("Угорі — денний множник на всіх вогнях. Унизу — той самий множник, коли з обох боків лишено тільки сильні вогні: "
            "рядок MODIS від 10 МВт і клітинка VIIRS завбільшки з піксель MODIS (близько 1 км) від 10 МВт. "
            "Україна, пожежі рослинності, денні прольоти, 2012–2021.")
    foot = ("Дані: архів NASA FIRMS, Україна, рядки з type = 0. Дві таблиці мають різні шкали кольору. "
            "Перевірка множника на кожен місяць року (вчимо на п'яти роках, перевіряємо на п'яти інших), типовий промах за місяць: "
            "усі денні вогні 9,6%, тільки вогні від 10 МВт 6,9%.")
    panels = [
        dict(BLUE, title="День, усі вогні", word="день, усі вогні", dec=1, edges=[4.5, 6, 8, 10],
             labels=["менше 4,5", "4,5–6", "6–8", "8–10", "10 і більше"], extra="",
             unit="точок VIIRS на одну точку MODIS", mLabel="точок MODIS (Aqua)", vLabel="точок VIIRS (Suomi NPP)",
             mTotal="Точок MODIS за 10 років", vTotal="Точок VIIRS за 10 років", data=table(a_all, s_all, "D")),
        dict(ORANGE, title="День, тільки вогні від 10 МВт", word="день, від 10 МВт", dec=2, edges=[1.2, 1.4, 1.7, 2.0],
             labels=["менше 1,2", "1,2–1,4", "1,4–1,7", "1,7–2,0", "2,0 і більше"],
             extra=" Шкала тут інша: числа близькі до одиниці.",
             unit="сильних клітинок VIIRS на одну сильну точку MODIS", mLabel="точок MODIS від 10 МВт",
             vLabel="клітинок VIIRS від 10 МВт", mTotal="Сильних точок MODIS за 10 років",
             vTotal="Сильних клітинок VIIRS за 10 років", data=table(a_strong, s_strong, "D")),
    ]

HTML = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Множник MODIS → VIIRS рік за роком</title>
<style>
  html, body { margin: 0; }
  .viz-root {
    color-scheme: light;
    --page: #f9f9f7; --surface-1: #fcfcfb;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
    --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10); --wash: rgba(11,11,11,0.05);
    --q0: #86b6ef; --q1: #5598e7; --q2: #2a78d6; --q3: #1c5cab; --q4: #0d366b;
    --q0-ink: #0b0b0b; --q1-ink: #ffffff; --q2-ink: #ffffff; --q3-ink: #ffffff; --q4-ink: #ffffff;
    --n0: #f39776; --n1: #da7550; --n2: #c54e1c; --n3: #9c390c; --n4: #601f03;
    --n0-ink: #0b0b0b; --n1-ink: #ffffff; --n2-ink: #ffffff; --n3-ink: #ffffff; --n4-ink: #ffffff;
    position: relative; min-height: 100vh; box-sizing: border-box; padding: 24px 16px 40px;
    background: var(--page); color: var(--text-primary);
    font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) .viz-root {
      color-scheme: dark;
      --page: #0d0d0d; --surface-1: #1a1a19;
      --text-primary: #f0efec; --text-secondary: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --wash: rgba(255,255,255,0.07);
      --q0: #184f95; --q1: #256abf; --q2: #3987e5; --q3: #6da7ec; --q4: #b7d3f6;
      --q0-ink: #ffffff; --q1-ink: #ffffff; --q2-ink: #ffffff; --q3-ink: #0b0b0b; --q4-ink: #0b0b0b;
      --n0: #883008; --n1: #af4517; --n2: #d45e2f; --n3: #e38968; --n4: #fec0aa;
      --n0-ink: #ffffff; --n1-ink: #ffffff; --n2-ink: #ffffff; --n3-ink: #ffffff; --n4-ink: #0b0b0b;
    }
  }
  :root[data-theme="dark"] .viz-root {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19;
    --text-primary: #f0efec; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --wash: rgba(255,255,255,0.07);
    --q0: #184f95; --q1: #256abf; --q2: #3987e5; --q3: #6da7ec; --q4: #b7d3f6;
    --q0-ink: #ffffff; --q1-ink: #ffffff; --q2-ink: #ffffff; --q3-ink: #0b0b0b; --q4-ink: #0b0b0b;
    --n0: #883008; --n1: #af4517; --n2: #d45e2f; --n3: #e38968; --n4: #fec0aa;
    --n0-ink: #ffffff; --n1-ink: #ffffff; --n2-ink: #ffffff; --n3-ink: #ffffff; --n4-ink: #0b0b0b;
  }
  .wrap { max-width: 960px; margin: 0 auto; }
  h1 { font-size: 22px; line-height: 1.25; font-weight: 650; margin: 0 0 6px; }
  .lede { color: var(--text-secondary); margin: 0 0 16px; max-width: 78ch; }
  .filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: 0 0 16px; padding: 0; border: 0; }
  .filters legend { float: left; padding: 0; margin-right: 4px; color: var(--text-secondary); font-size: 13px; }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--surface-1); }
  .seg label { position: relative; font-size: 13px; padding: 5px 12px; color: var(--text-secondary); cursor: pointer; border-left: 1px solid var(--border); }
  .seg label:first-child { border-left: 0; }
  .seg label:hover { background: var(--wash); }
  .seg input { position: absolute; opacity: 0; inset: 0; margin: 0; cursor: pointer; }
  .seg label:has(input:checked) { color: var(--text-primary); font-weight: 650; background: var(--wash); }
  .seg label:has(input:focus-visible) { outline: 2px solid var(--text-primary); outline-offset: -2px; }
  .hint { color: var(--muted); font-size: 12.5px; }
  .card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px 16px; margin: 0 0 16px; }
  .card h2 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
  .card .sub { color: var(--text-secondary); font-size: 13px; margin: 0 0 12px; max-width: 90ch; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: separate; border-spacing: 2px; width: 100%; font-variant-numeric: tabular-nums; }
  th { font-weight: 500; color: var(--muted); font-size: 12px; padding: 4px 6px; text-align: center; white-space: nowrap; }
  th[scope="row"] { text-align: left; color: var(--text-secondary); padding-left: 0; }
  td { text-align: center; font-size: 12.5px; padding: 6px 4px; border-radius: 4px; min-width: 44px; outline: none; }
  td.q0 { background: var(--q0); color: var(--q0-ink); } td.q1 { background: var(--q1); color: var(--q1-ink); }
  td.q2 { background: var(--q2); color: var(--q2-ink); } td.q3 { background: var(--q3); color: var(--q3-ink); }
  td.q4 { background: var(--q4); color: var(--q4-ink); }
  td.n0 { background: var(--n0); color: var(--n0-ink); } td.n1 { background: var(--n1); color: var(--n1-ink); }
  td.n2 { background: var(--n2); color: var(--n2-ink); } td.n3 { background: var(--n3); color: var(--n3-ink); }
  td.n4 { background: var(--n4); color: var(--n4-ink); }
  td.low { color: var(--muted); }
  td[tabindex]:hover, td[tabindex]:focus-visible { box-shadow: 0 0 0 2px var(--surface-1), 0 0 0 4px var(--text-primary); }
  tr.plan-row th, tr.plan-row td { font-weight: 650; }
  tr.plan-row th { color: var(--text-primary); }
  tr.gap td, tr.gap th { padding: 3px 0; }
  tr.count td { color: var(--muted); font-size: 11.5px; }
  .scale { display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; margin: 12px 0 0; padding: 0; list-style: none; color: var(--text-secondary); font-size: 12.5px; }
  .scale li { display: flex; align-items: center; gap: 6px; }
  .sw { width: 22px; height: 14px; border-radius: 3px; flex: none; }
  .tip { position: absolute; z-index: 5; pointer-events: none; background: var(--surface-1); color: var(--text-primary); border: 1px solid var(--border);
         border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.14); padding: 8px 10px; font-size: 12.5px; min-width: 190px; max-width: 320px; }
  .tip[hidden] { display: none; }
  .tip .t { color: var(--text-secondary); margin: 0 0 4px; }
  .tip .r { display: flex; align-items: baseline; gap: 8px; margin: 2px 0; }
  .tip b { font-weight: 650; font-variant-numeric: tabular-nums; min-width: 3.2em; text-align: right; }
  .tip .l { color: var(--text-secondary); }
  footer { color: var(--muted); font-size: 12px; margin-top: 4px; max-width: 90ch; }
</style>
</head>
<body>
<div class="viz-root" id="root">
  <div class="wrap">
    <h1 id="h1"></h1>
    <p class="lede" id="lede"></p>
    <fieldset class="filters">
      <legend>Показувати клітинку, якщо MODIS нарахував у ній хоча б</legend>
      <span class="seg" id="seg"></span>
      <span class="hint">Менший поріг відкриває більше клітинок, але числа в них менш надійні.</span>
    </fieldset>
    <div id="panels"></div>
    <footer id="foot"></footer>
  </div>
  <div class="tip" id="tip" role="status" hidden></div>
</div>
<script>
(function () {
  "use strict";
  var params = new URLSearchParams(location.search);
  var theme = params.get("theme");
  if (theme === "dark" || theme === "light") document.documentElement.dataset.theme = theme;

  var SPEC = __SPEC__;
  var YEARS = SPEC.years, PANELS = SPEC.panels;
  document.getElementById("h1").textContent = SPEC.title;
  document.getElementById("lede").textContent = SPEC.lede;
  document.getElementById("foot").textContent = SPEC.foot;
  var MS = ["Січ","Лют","Бер","Кві","Тра","Чер","Лип","Сер","Вер","Жов","Лис","Гру"];
  var MF = ["Січень","Лютий","Березень","Квітень","Травень","Червень","Липень","Серпень","Вересень","Жовтень","Листопад","Грудень"];
  var CHOICES = [50, 20, 10];
  var minPoints = CHOICES.indexOf(Number(params.get("min"))) >= 0 ? Number(params.get("min")) : 50;
  var root = document.getElementById("root"), tip = document.getElementById("tip");

  function fx(v, dec) { return v >= 100 ? String(Math.round(v)) : v.toFixed(dec).replace(".", ","); }
  function fi(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "); }
  function el(name, cls, text, parent) {
    var e = document.createElement(name);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function showTip(title, rows, clientX, clientY) {
    tip.textContent = "";
    el("p", "t", title, tip);
    rows.forEach(function (r) {
      var row = el("div", "r", null, tip);
      el("b", null, r.value == null ? "" : r.value, row);
      el("span", "l", r.label, row);
    });
    tip.hidden = false;
    var box = root.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    var x = clientX - box.left + 14, y = clientY - box.top + 14;
    if (x + w > box.width - 8) x = clientX - box.left - w - 14;
    if (y + h > box.height - 8) y = clientY - box.top - h - 14;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }
  function hideTip() { tip.hidden = true; }
  function cellTip(td, title, rows) {
    td.tabIndex = 0;
    function on(ev) {
      var r = td.getBoundingClientRect(), k = ev.type === "focus";
      showTip(title, rows, k ? r.left + r.width / 2 : ev.clientX, k ? r.bottom : ev.clientY);
    }
    td.addEventListener("pointermove", on); td.addEventListener("focus", on);
    td.addEventListener("pointerleave", hideTip); td.addEventListener("blur", hideTip);
  }

  // one row of filters above everything it scopes
  var seg = document.getElementById("seg");
  CHOICES.forEach(function (n) {
    var lab = el("label", null, null, seg), inp = el("input", null, null, lab);
    inp.type = "radio"; inp.name = "min"; inp.value = String(n); inp.checked = n === minPoints;
    lab.appendChild(document.createTextNode(n + " точок"));
    inp.addEventListener("change", function () { minPoints = n; render(); });
  });

  function render() {
    var host = document.getElementById("panels");
    host.textContent = "";
    hideTip();
    PANELS.forEach(function (cfg) {
      var P = cfg.data;
      function bin(v) { var b = 0; while (b < cfg.edges.length && v >= cfg.edges[b]) b++; return b; }
      function ratio(y, m) { var a = P.aqua[y][m]; return a >= minPoints ? P.snpp[y][m] / a : null; }
      function f1(v) { return fx(v, cfg.dec); }
      var aTot = [], sTot = [], nValid = 0;
      for (var m = 0; m < 12; m++) {
        aTot.push(YEARS.reduce(function (s, y) { return s + P.aqua[y][m]; }, 0));
        sTot.push(YEARS.reduce(function (s, y) { return s + P.snpp[y][m]; }, 0));
      }
      YEARS.forEach(function (y) { for (var m = 0; m < 12; m++) if (ratio(y, m) != null) nValid++; });

      var card = el("figure", "card", null, host);
      card.style.marginLeft = "0"; card.style.marginRight = "0";
      el("h2", null, cfg.title, card);
      el("p", "sub", "Колір клітинки показує розмір множника, шкала під таблицею. Клітинок з даними: " + nValid + " зі 120." + cfg.extra, card);
      var table = el("table", null, null, el("div", "tablewrap", null, card));
      var cap = el("caption", null, "Множник MODIS до VIIRS за кожен місяць кожного року, " + cfg.word, table);
      cap.style.position = "absolute"; cap.style.left = "-9999px";
      var hr = el("tr", null, null, el("thead", null, null, table));
      el("th", null, "Рік", hr).setAttribute("scope", "col");
      MS.forEach(function (name) { el("th", null, name, hr).setAttribute("scope", "col"); });
      var tbody = el("tbody", null, null, table);

      YEARS.forEach(function (y) {
        var tr = el("tr", null, null, tbody);
        el("th", null, String(y), tr).setAttribute("scope", "row");
        for (var m = 0; m < 12; m++) {
          var v = ratio(y, m);
          var td = el("td", v == null ? "low" : cfg.cls + bin(v), v == null ? "·" : f1(v), tr);
          var rows = v == null
            ? [{ value: null, label: "мало даних: менше " + minPoints + " точок MODIS" }]
            : [{ value: f1(v), label: cfg.unit }];
          rows.push({ value: fi(P.aqua[y][m]), label: cfg.mLabel });
          rows.push({ value: fi(P.snpp[y][m]), label: cfg.vLabel });
          if (v == null) td.setAttribute("aria-label", "мало даних");
          cellTip(td, MF[m] + " " + y + ", " + cfg.word, rows);
        }
      });
      var gap = el("tr", "gap", null, tbody);
      el("th", null, "", gap); for (var i = 0; i < 12; i++) el("td", null, "", gap);
      var pr = el("tr", "plan-row", null, tbody);
      el("th", null, "Усі роки разом", pr).setAttribute("scope", "row");
      for (var m2 = 0; m2 < 12; m2++) {
        var pv = aTot[m2] >= minPoints ? sTot[m2] / aTot[m2] : null;
        var ptd = el("td", pv == null ? "low" : cfg.cls + bin(pv), pv == null ? "·" : f1(pv), pr);
        cellTip(ptd, MF[m2] + ", " + cfg.word + ", 2012–2021 разом", [
          { value: pv == null ? null : f1(pv), label: pv == null ? "мало даних: менше " + minPoints + " точок MODIS" : cfg.unit },
          { value: fi(aTot[m2]), label: cfg.mLabel + ", 10 років" },
          { value: fi(sTot[m2]), label: cfg.vLabel + ", 10 років" }]);
      }
      var cr = el("tr", "count", null, tbody);
      el("th", null, cfg.mTotal, cr).setAttribute("scope", "row");
      aTot.forEach(function (n) { el("td", null, fi(n), cr); });
      var cr2 = el("tr", "count", null, tbody);
      el("th", null, cfg.vTotal, cr2).setAttribute("scope", "row");
      sTot.forEach(function (n) { el("td", null, fi(n), cr2); });

      var scale = el("ul", "scale", null, card);
      cfg.labels.forEach(function (label, b) {
        var li = el("li", null, null, scale), sw = el("span", "sw", null, li);
        sw.style.background = "var(--" + cfg.cls + b + ")";
        el("span", null, label, li);
      });
      el("span", null, "·  мало даних: менше " + minPoints + " точок MODIS за місяць", el("li", null, null, scale));
    });
  }
  render();
})();
</script>
</body>
</html>
"""

spec = {"years": YEARS, "title": title, "lede": lede, "foot": foot, "panels": panels}
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(HTML.replace("__SPEC__", json.dumps(spec, ensure_ascii=False)))
print("wrote", OUT, "page:", PAGE)
if PAGE == "samebar":
    tot_a = sum(a_strong["D", y, m] for y in YEARS for m in range(1, 13))
    tot_s = sum(s_strong["D", y, m] for y in YEARS for m in range(1, 13))
    print(f"strong day units: MODIS rows {tot_a}, VIIRS cells {tot_s}, ratio {tot_s / tot_a:.2f}")
