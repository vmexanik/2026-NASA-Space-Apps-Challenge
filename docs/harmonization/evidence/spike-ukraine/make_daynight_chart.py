#!/usr/bin/env python3
"""Build a self-contained HTML page: the MODIS -> VIIRS multiplier by calendar month, day and night apart.

Usage: python3 -I make_daynight_chart.py <folder with modis_*_Ukraine.csv and viirs-snpp_*_Ukraine.csv> <out.html>
"""
import csv
import glob
import json
import os
import sys
from collections import Counter

DATA, OUT = sys.argv[1], sys.argv[2]
YEARS = list(range(2012, 2022))
MIN_POINTS = 50   # a month with fewer MODIS points gives no trustworthy ratio


def counts(pattern: str, sat: str | None = None) -> Counter:
    c: Counter = Counter()
    for path in sorted(glob.glob(os.path.join(DATA, pattern))):
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["type"] != "0" or (sat and r["satellite"] != sat):
                    continue
                c[r["daynight"], int(r["acq_date"][:4]), int(r["acq_date"][5:7])] += 1
    return c


aqua, snpp = counts("modis_*_Ukraine.csv", "Aqua"), counts("viirs-snpp_*_Ukraine.csv")


def panel(dn: str) -> dict:
    a_tot = [sum(aqua[dn, y, m] for y in YEARS) for m in range(1, 13)]
    s_tot = [sum(snpp[dn, y, m] for y in YEARS) for m in range(1, 13)]
    return {
        "aqua": {str(y): [aqua[dn, y, m] for m in range(1, 13)] for y in YEARS},
        "snpp": {str(y): [snpp[dn, y, m] for m in range(1, 13)] for y in YEARS},
        "aquaTotal": a_tot,
        "snppTotal": s_tot,
        "pooled": [s / a if a >= MIN_POINTS else None for a, s in zip(a_tot, s_tot)],
        "sumAqua": sum(a_tot),
        "sumSnpp": sum(s_tot),
    }


data = {"years": YEARS, "minPoints": MIN_POINTS, "day": panel("D"), "night": panel("N")}

HTML = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Множник MODIS → VIIRS: день і ніч окремо</title>
<style>
  html, body { margin: 0; }
  .viz-root {
    color-scheme: light;
    --page: #f9f9f7; --surface-1: #fcfcfb;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
    --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6; --context: #898781;
    --q0: #86b6ef; --q1: #5598e7; --q2: #2a78d6; --q3: #1c5cab; --q4: #0d366b;
    --q0-ink: #0b0b0b; --q1-ink: #ffffff; --q2-ink: #ffffff; --q3-ink: #ffffff; --q4-ink: #ffffff;
    position: relative; min-height: 100vh; box-sizing: border-box; padding: 24px 16px 40px;
    background: var(--page); color: var(--text-primary);
    font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) .viz-root {
      color-scheme: dark;
      --page: #0d0d0d; --surface-1: #1a1a19;
      --text-primary: #f0efec; --text-secondary: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
      --series-1: #3987e5; --context: #898781;
      --q0: #184f95; --q1: #256abf; --q2: #3987e5; --q3: #6da7ec; --q4: #b7d3f6;
      --q0-ink: #ffffff; --q1-ink: #ffffff; --q2-ink: #ffffff; --q3-ink: #0b0b0b; --q4-ink: #0b0b0b;
    }
  }
  :root[data-theme="dark"] .viz-root {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19;
    --text-primary: #f0efec; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --context: #898781;
    --q0: #184f95; --q1: #256abf; --q2: #3987e5; --q3: #6da7ec; --q4: #b7d3f6;
    --q0-ink: #ffffff; --q1-ink: #ffffff; --q2-ink: #ffffff; --q3-ink: #0b0b0b; --q4-ink: #0b0b0b;
  }
  .wrap { max-width: 960px; margin: 0 auto; }
  h1 { font-size: 22px; line-height: 1.25; font-weight: 650; margin: 0 0 6px; }
  .lede { color: var(--text-secondary); margin: 0 0 16px; max-width: 72ch; }
  .tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 0 0 16px; }
  @media (max-width: 720px) { .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
  .tile .lab { color: var(--text-secondary); font-size: 12.5px; }
  .tile .num { font-size: 28px; line-height: 1.15; font-weight: 600; margin: 2px 0; }
  .tile .sm { color: var(--muted); font-size: 12px; }
  .card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px 16px; margin: 0 0 16px; }
  .card h2 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
  .card h3 { font-size: 13.5px; font-weight: 600; margin: 18px 0 2px; }
  .card .sub { color: var(--text-secondary); font-size: 13px; margin: 0 0 12px; max-width: 86ch; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 20px; margin: 0 0 6px; padding: 0; list-style: none; color: var(--text-secondary); font-size: 13px; }
  .legend li { display: flex; align-items: center; gap: 8px; }
  .key { width: 22px; height: 0; border-top: 2px solid var(--series-1); position: relative; flex: none; }
  .key.ctx { border-top: 1.5px solid var(--context); opacity: .6; }
  .key.dot::after { content: ""; position: absolute; left: 7px; top: -5px; width: 8px; height: 8px; border-radius: 50%; background: var(--series-1); }
  svg { display: block; width: 100%; height: auto; overflow: visible; }
  svg text { font: 12px system-ui, -apple-system, "Segoe UI", sans-serif; fill: var(--muted); font-variant-numeric: tabular-nums; }
  svg text.val { fill: var(--text-primary); font-weight: 600; paint-order: stroke; stroke: var(--surface-1); stroke-width: 4px; stroke-linejoin: round; }
  .grid { stroke: var(--grid); stroke-width: 1; }
  .base { stroke: var(--axis); stroke-width: 1; }
  .yr { fill: none; stroke: var(--context); stroke-width: 1.5; stroke-linejoin: round; stroke-linecap: round; opacity: .5; }
  .yrdot { fill: var(--context); opacity: .55; }
  .plan { fill: none; stroke: var(--series-1); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
  .plandot { fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2; }
  .plandot.weak { fill: var(--surface-1); stroke: var(--series-1); }
  .ring { width: 8px; height: 8px; border-radius: 50%; border: 2px solid var(--series-1); background: var(--surface-1); flex: none; margin: 0 5px; }
  .cross { stroke: var(--muted); stroke-width: 1; visibility: hidden; }
  .hit { fill: transparent; outline: none; cursor: default; }
  .hit:focus-visible { stroke: var(--series-1); stroke-width: 1; }
  .note { color: var(--text-secondary); font-size: 13px; margin: 10px 0 0; max-width: 80ch; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: separate; border-spacing: 2px; width: 100%; font-variant-numeric: tabular-nums; }
  th { font-weight: 500; color: var(--muted); font-size: 12px; padding: 4px 6px; text-align: center; white-space: nowrap; }
  th[scope="row"] { text-align: left; color: var(--text-secondary); padding-left: 0; }
  td { text-align: center; font-size: 12.5px; padding: 6px 4px; border-radius: 4px; min-width: 44px; outline: none; }
  td.q0 { background: var(--q0); color: var(--q0-ink); } td.q1 { background: var(--q1); color: var(--q1-ink); }
  td.q2 { background: var(--q2); color: var(--q2-ink); } td.q3 { background: var(--q3); color: var(--q3-ink); }
  td.q4 { background: var(--q4); color: var(--q4-ink); }
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
         border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.14); padding: 8px 10px; font-size: 12.5px; min-width: 190px; max-width: 290px; }
  .tip[hidden] { display: none; }
  .tip .t { color: var(--text-secondary); margin: 0 0 4px; }
  .tip .r { display: flex; align-items: baseline; gap: 8px; margin: 2px 0; }
  .tip .k { width: 14px; border-top: 2px solid var(--series-1); align-self: center; flex: none; }
  .tip .k.ctx { border-top-color: var(--context); }
  .tip .k.none { border-top-color: transparent; }
  .tip b { font-weight: 650; font-variant-numeric: tabular-nums; }
  .tip .l { color: var(--text-secondary); }
  footer { color: var(--muted); font-size: 12px; margin-top: 4px; max-width: 90ch; }
</style>
</head>
<body>
<div class="viz-root" id="root">
  <div class="wrap">
    <h1>Удень множник спокійний, від 3 до 8. Уночі MODIS майже сліпий</h1>
    <p class="lede">Множник — це скільки точок нарахував VIIRS (Suomi NPP) на одну точку MODIS (Aqua) за той самий місяць над Україною. Тут він порахований окремо для денних і для нічних прольотів. Тільки пожежі рослинності, 2012–2021.</p>
    <div class="tiles" id="tiles"></div>
    <div id="panels"></div>
    <footer id="foot"></footer>
  </div>
  <div class="tip" id="tip" role="status" hidden></div>
</div>
<script>
(function () {
  "use strict";
  var theme = new URLSearchParams(location.search).get("theme");
  if (theme === "dark" || theme === "light") document.documentElement.dataset.theme = theme;

  var D = __DATA__;
  var MS = ["Січ","Лют","Бер","Кві","Тра","Чер","Лип","Сер","Вер","Жов","Лис","Гру"];
  var MF = ["Січень","Лютий","Березень","Квітень","Травень","Червень","Липень","Серпень","Вересень","Жовтень","Листопад","Грудень"];
  var EDGES = [4.5, 6, 8, 10];
  var BIN_LABELS = ["менше 4,5", "4,5–6", "6–8", "8–10", "10 і більше"];
  var NS = "http://www.w3.org/2000/svg";
  var root = document.getElementById("root"), tip = document.getElementById("tip");

  function f1(v) { return v >= 100 ? String(Math.round(v)) : v.toFixed(1).replace(".", ","); }
  function fi(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "); }
  function pct(v) { return String(Math.round(v * 100)) + "%"; }
  function bin(v) { var b = 0; while (b < EDGES.length && v >= EDGES[b]) b++; return b; }
  function svg(name, attrs, parent) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
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
      el("span", "k " + (r.key || "none"), null, row);
      if (r.value != null) el("b", null, r.value, row);
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

  // ------------------------------------------------------------------ tiles
  var day = D.day, night = D.night;
  var tiles = document.getElementById("tiles");
  [["Множник удень", f1(day.sumSnpp / day.sumAqua), fi(day.sumAqua) + " точок MODIS, " + fi(day.sumSnpp) + " точок VIIRS"],
   ["Множник уночі", f1(night.sumSnpp / night.sumAqua), fi(night.sumAqua) + " точок MODIS, " + fi(night.sumSnpp) + " точок VIIRS"],
   ["Нічних точок у MODIS", pct(night.sumAqua / (night.sumAqua + day.sumAqua)), "з усіх його пожеж за 10 років"],
   ["Нічних точок у VIIRS", pct(night.sumSnpp / (night.sumSnpp + day.sumSnpp)), "з усіх його пожеж за 10 років"]
  ].forEach(function (t) {
    var d = el("div", "tile", null, tiles);
    el("div", "lab", t[0], d); el("div", "num", t[1], d); el("div", "sm", t[2], d);
  });

  // ------------------------------------------------------------------ panel
  function panel(P, cfg) {
    function ratio(y, m) { var a = P.aqua[y][m]; return a >= D.minPoints ? P.snpp[y][m] / a : null; }
    var card = el("figure", "card", null, document.getElementById("panels"));
    card.style.marginLeft = "0"; card.style.marginRight = "0";
    el("h2", null, cfg.title, card);
    el("p", "sub", cfg.sub, card);
    var lg = el("ul", "legend", null, card);
    var li1 = el("li", null, null, lg); el("span", "key dot", null, li1); el("span", null, "усі десять років разом", li1);
    var li2 = el("li", null, null, lg); el("span", "key ctx", null, li2); el("span", null, "окремі роки", li2);
    var li3 = el("li", null, null, lg); el("span", "ring", null, li3); el("span", null, "менше 500 точок MODIS за 10 років, число ненадійне", li3);

    var W = 920, H = 340, L = 44, R = 16, T = 26, B = 34;
    var chart = svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": cfg.aria }, card);
    var step = (W - L - R) / 12, maxV = 0, nValid = 0;
    P.pooled.forEach(function (v) { if (v != null && v > maxV) maxV = v; });
    D.years.forEach(function (y) { for (var m = 0; m < 12; m++) { var v = ratio(y, m); if (v != null) { nValid++; if (v > maxV) maxV = v; } } });
    var tick = [1, 2, 5, 10, 20, 50, 100, 200].filter(function (s) { return maxV * 1.05 / s <= 6; })[0] || 500;
    var yMax = Math.ceil(maxV * 1.05 / tick) * tick;
    function X(m) { return L + (m + 0.5) * step; }
    function Y(v) { return T + (1 - v / yMax) * (H - T - B); }

    for (var g = 0; g <= yMax + 1e-9; g += tick) {
      svg("line", { x1: L, x2: W - R, y1: Y(g), y2: Y(g), "class": g === 0 ? "base" : "grid" }, chart);
      svg("text", { x: L - 8, y: Y(g) + 4, "text-anchor": "end" }, chart).textContent = String(g);
    }
    svg("text", { x: 0, y: 12 }, chart).textContent = "точок VIIRS на одну точку MODIS";
    MS.forEach(function (name, m) { svg("text", { x: X(m), y: H - 10, "text-anchor": "middle" }, chart).textContent = name; });

    D.years.forEach(function (y) {
      var d = "", open = false;
      for (var m = 0; m < 12; m++) {
        var v = ratio(y, m);
        if (v == null) { open = false; continue; }
        d += (open ? "L" : "M") + X(m).toFixed(1) + " " + Y(v).toFixed(1) + " ";
        open = true;
        svg("circle", { cx: X(m), cy: Y(v), r: 2.5, "class": "yrdot" }, chart);
      }
      if (d) svg("path", { d: d, "class": "yr" }, chart);
    });

    var cross = svg("line", { y1: T, y2: H - B, "class": "cross" }, chart);
    var pd = "", popen = false, defined = [];
    P.pooled.forEach(function (v, m) {
      if (v == null) { popen = false; return; }
      pd += (popen ? "L" : "M") + X(m).toFixed(1) + " " + Y(v).toFixed(1) + " ";
      popen = true; defined.push(m);
    });
    svg("path", { d: pd, "class": "plan" }, chart);
    var STRONG = 10 * D.minPoints;
    defined.forEach(function (m) {
      svg("circle", { cx: X(m), cy: Y(P.pooled[m]), r: 4.5, "class": P.aquaTotal[m] < STRONG ? "plandot weak" : "plandot" }, chart);
    });
    var strong = defined.filter(function (m) { return P.aquaTotal[m] >= STRONG; });
    var pool = strong.length >= 2 ? strong : defined;
    var iMax = pool.reduce(function (a, b) { return P.pooled[b] > P.pooled[a] ? b : a; });
    var iMin = pool.reduce(function (a, b) { return P.pooled[b] < P.pooled[a] ? b : a; });
    [[iMax, -12], [iMin, 20]].forEach(function (p) {
      svg("text", { x: X(p[0]), y: Y(P.pooled[p[0]]) + p[1], "text-anchor": "middle", "class": "val" }, chart).textContent = f1(P.pooled[p[0]]);
    });

    function monthRows(m) {
      var vals = D.years.map(function (y) { return ratio(y, m); }).filter(function (v) { return v != null; });
      var rows = [];
      if (P.pooled[m] != null) rows.push({ key: "", value: f1(P.pooled[m]), label: "усі десять років разом" });
      else rows.push({ key: "", value: null, label: "за десять років не набралося " + D.minPoints + " точок MODIS" });
      if (vals.length) rows.push({ key: "ctx", value: f1(Math.min.apply(null, vals)) + "–" + f1(Math.max.apply(null, vals)),
                                   label: "окремі роки (" + vals.length + " з " + D.years.length + ")" });
      else rows.push({ key: "ctx", value: null, label: "у жодному році не набралося " + D.minPoints + " точок MODIS" });
      rows.push({ key: "none", value: fi(P.aquaTotal[m]), label: "точок MODIS за 10 років" });
      rows.push({ key: "none", value: fi(P.snppTotal[m]), label: "точок VIIRS за 10 років" });
      return rows;
    }
    MS.forEach(function (name, m) {
      var hit = svg("rect", { x: L + m * step, y: T, width: step, height: H - T - B, "class": "hit", tabindex: 0,
                              "aria-label": MF[m] + ", " + cfg.word + (P.pooled[m] != null ? ": множник " + f1(P.pooled[m]) : ": мало даних") }, chart);
      function on(ev) {
        cross.setAttribute("x1", X(m)); cross.setAttribute("x2", X(m)); cross.style.visibility = "visible";
        var r = hit.getBoundingClientRect(), k = ev.type === "focus";
        showTip(MF[m] + ", " + cfg.word, monthRows(m), k ? r.left + r.width / 2 : ev.clientX, k ? r.top + 20 : ev.clientY);
      }
      function off() { cross.style.visibility = "hidden"; hideTip(); }
      hit.addEventListener("pointermove", on); hit.addEventListener("focus", on);
      hit.addEventListener("pointerleave", off); hit.addEventListener("blur", off);
    });
    el("p", "note", cfg.note, card);

    // table
    el("h3", null, "Ті самі числа таблицею", card);
    el("p", "sub", cfg.tableSub.replace("{n}", String(nValid)), card);
    var wrap = el("div", "tablewrap", null, card), table = el("table", null, null, wrap);
    var hr = el("tr", null, null, el("thead", null, null, table));
    el("th", null, "Рік", hr).setAttribute("scope", "col");
    MS.forEach(function (name) { el("th", null, name, hr).setAttribute("scope", "col"); });
    var tbody = el("tbody", null, null, table);
    function cellTip(td, title, rows) {
      td.tabIndex = 0;
      function on(ev) {
        var r = td.getBoundingClientRect(), k = ev.type === "focus";
        showTip(title, rows, k ? r.left + r.width / 2 : ev.clientX, k ? r.bottom : ev.clientY);
      }
      td.addEventListener("pointermove", on); td.addEventListener("focus", on);
      td.addEventListener("pointerleave", hideTip); td.addEventListener("blur", hideTip);
    }
    D.years.forEach(function (y) {
      var tr = el("tr", null, null, tbody);
      el("th", null, String(y), tr).setAttribute("scope", "row");
      for (var m = 0; m < 12; m++) {
        var v = ratio(y, m);
        var td = el("td", v == null ? "low" : (cfg.shade ? "q" + bin(v) : ""), v == null ? "·" : f1(v), tr);
        var rows = v == null
          ? [{ key: "none", value: null, label: "мало даних: менше " + D.minPoints + " точок MODIS" }]
          : [{ key: "none", value: f1(v), label: "точок VIIRS на одну точку MODIS" }];
        rows.push({ key: "none", value: fi(P.aqua[y][m]), label: "точок MODIS (Aqua)" });
        rows.push({ key: "none", value: fi(P.snpp[y][m]), label: "точок VIIRS (Suomi NPP)" });
        if (v == null) td.setAttribute("aria-label", "мало даних");
        cellTip(td, MF[m] + " " + y + ", " + cfg.word, rows);
      }
    });
    var gap = el("tr", "gap", null, tbody);
    el("th", null, "", gap); for (var i = 0; i < 12; i++) el("td", null, "", gap);
    var pr = el("tr", "plan-row", null, tbody);
    el("th", null, "Усі роки разом", pr).setAttribute("scope", "row");
    P.pooled.forEach(function (v, m) {
      var td = el("td", v == null ? "low" : (cfg.shade ? "q" + bin(v) : ""), v == null ? "·" : f1(v), pr);
      cellTip(td, MF[m] + ", " + cfg.word + ", 2012–2021 разом", [
        { key: "", value: v == null ? null : f1(v), label: v == null ? "мало даних" : "точок VIIRS на одну точку MODIS" },
        { key: "none", value: fi(P.aquaTotal[m]), label: "точок MODIS за 10 років" },
        { key: "none", value: fi(P.snppTotal[m]), label: "точок VIIRS за 10 років" }]);
    });
    var cr = el("tr", "count", null, tbody);
    el("th", null, "Точок MODIS за 10 років", cr).setAttribute("scope", "row");
    P.aquaTotal.forEach(function (n) { el("td", null, fi(n), cr); });
    var cr2 = el("tr", "count", null, tbody);
    el("th", null, "Точок VIIRS за 10 років", cr2).setAttribute("scope", "row");
    P.snppTotal.forEach(function (n) { el("td", null, fi(n), cr2); });

    var scale = el("ul", "scale", null, card);
    if (cfg.shade) BIN_LABELS.forEach(function (label, b) {
      var li = el("li", null, null, scale), sw = el("span", "sw", null, li);
      sw.style.background = "var(--q" + b + ")";
      el("span", null, label, li);
    });
    el("span", null, "·  мало даних: менше " + D.minPoints + " точок MODIS за місяць", el("li", null, null, scale));
  }

  panel(day, {
    word: "день", shade: true,
    title: "День: хвиля нижча й рівніша",
    sub: "Кожна сіра лінія — окремий рік. Синя — усі десять років разом.",
    aria: "Денний множник MODIS до VIIRS за місяцями року, окремо для кожного року 2012–2021 і для всіх років разом",
    note: "Удень множник ходить від 3 у жовтні до 8 у червні; січень і грудень тримаються на сотні-двох точок. Великий літній пік із загальної картинки, до 13, робить ніч: улітку VIIRS бачить багато нічних вогнів, а MODIS їх майже не бачить.",
    tableSub: "Колір клітинки показує розмір множника, шкала під таблицею. Клітинок з даними: {n} зі 120."
  });
  panel(night, {
    word: "ніч", shade: false,
    title: "Ніч: MODIS майже нічого не бачить",
    sub: "Шкала тут у багато разів більша, ніж у денному графіку. Сірі точки — місяці окремих років, де MODIS нарахував хоча б 50 нічних точок.",
    aria: "Нічний множник MODIS до VIIRS за місяцями року, окремо для кожного року 2012–2021 і для всіх років разом",
    note: "За десять років MODIS нарахував уночі " + fi(night.sumAqua) + " точок, VIIRS — " + fi(night.sumSnpp) + ". На одну нічну точку MODIS припадає близько 50 точок VIIRS, а у більшості місяців MODIS не дає й 50 точок. Множник на таких числах не тримається.",
    tableSub: "Без кольору: чисел мало, і вони в іншому масштабі, ніж удень. Клітинок з даними: {n} зі 120."
  });

  document.getElementById("foot").textContent =
    "Дані: архів NASA FIRMS, Україна, рядки з type = 0. Перевірка множника на кожен місяць року " +
    "(вчимо на п'яти роках, перевіряємо на п'яти інших), типовий промах за місяць: день 9–11%, " +
    "день і ніч разом 12%, ніч 60–90%.";
})();
</script>
</body>
</html>
"""

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(HTML.replace("__DATA__", json.dumps(data)))
print("wrote", OUT)
for name in ("day", "night"):
    p = data[name]
    print(name, "pooled:", " ".join("  n/a" if v is None else f"{v:5.1f}" for v in p["pooled"]), "| Aqua", p["sumAqua"], "SNPP", p["sumSnpp"])
