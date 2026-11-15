"""Builds the self-contained page index.html from results.json of joins_probe.py.

Run: python3 -I make_page.py results.json index.html
"""

from __future__ import annotations

import html
import json
import sys

REGIONS = {"world": "Світ", "Ukraine": "Україна", "Brazil": "Бразилія", "Australia": "Австралія"}
LINES = [("terra", "Terra, гармонізована"), ("aqua", "Aqua, гармонізована"), ("snpp", "Suomi NPP")]
FIRST = 12
STARTS = {"terra": 10, "aqua": 30, "snpp": 144}


def pct(value: float) -> str:
    """A share as a signed percentage with one decimal and a decimal comma."""
    return f"{value * 100:+.1f}%".replace(".", ",").replace("-", "−")


def rolling(values: list[float]) -> list[float | None]:
    """The sum of each month and the 11 before it, None until 12 months exist."""
    out: list[float | None] = []
    for i in range(len(values)):
        out.append(sum(values[i - 11:i + 1]) if i >= 11 else None)
    return out


def table(head: list[str], rows: list[list[str]]) -> str:
    """An HTML table of already escaped cells."""
    return ("<table><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in head) + "</tr>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>")


def main() -> int:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    charts = {}
    for key in REGIONS:
        harm = data["regions"][key]["harmonized"]
        lines = {}
        for sat, _ in LINES:
            values = rolling(harm[sat])
            first_full = STARTS[sat] + 11
            lines[sat] = [None if i < first_full or values[i] is None else round(values[i])
                          for i in range(FIRST, len(values))]
        charts[key] = lines

    steps = [[html.escape(REGIONS[k]), pct(r["step_2002_raw"]), pct(r["step_2002"]), pct(r["step_2012_raw"]),
              pct(r["step_2012"])] for k, r in data["regions"].items()]
    years = list(range(2012, 2023))
    by_year = [[html.escape(REGIONS[k])] + [pct(r["snpp_over_aqua_by_year"][str(y)]) for y in years]
               for k, r in data["regions"].items()]
    backups = [[m, f"{v['series'] / 1e6:.3f}".replace(".", ","), f"{v['noaa20'] / 1e6:.3f}".replace(".", ","),
                pct(v["series"] / v["noaa20"] - 1)] for m, v in sorted(data["backup_months"].items())]
    payload = json.dumps({"charts": charts, "regions": REGIONS, "lines": LINES}, ensure_ascii=False)

    page = f"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Стики супутників: чи стрибає гармонізований ряд</title>
<style>
  :root {{ --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6f6e69;
           --grid: #e6e5e0; --rule: #b9b8b1; --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9d9c93;
             --grid: #2e2e2c; --rule: #5a5955; --s1: #3987e5; --s2: #d95926; --s3: #199e70; }}
  }}
  body {{ margin: 0; background: var(--page); color: var(--ink);
          font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 56px; }}
  h1 {{ font-size: 28px; line-height: 1.25; margin: 0 0 10px; }}
  h2 {{ font-size: 21px; margin: 36px 0 10px; }}
  h3 {{ font-size: 15px; margin: 0 0 6px; }}
  p {{ margin: 0 0 12px; max-width: 80ch; }}
  .lead {{ font-size: 18px; color: var(--ink-2); }}
  .card {{ background: var(--surface); border: 1px solid var(--grid); border-radius: 12px; padding: 12px 16px;
           overflow-x: auto; position: relative; }}
  .grid4 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr)); gap: 12px; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--ink-2); margin: 0 0 10px; }}
  .legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
  .ln {{ width: 16px; height: 3px; border-radius: 2px; display: inline-block; }}
  svg {{ display: block; width: 100%; height: auto; }}
  svg text {{ fill: var(--ink-3); font-size: 11px; font-variant-numeric: tabular-nums; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }}
  th, td {{ padding: 5px 8px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ color: var(--ink-2); font-weight: 600; }}
  .tip {{ position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--rule);
          border-radius: 8px; padding: 6px 10px; font-size: 12.5px; display: none; white-space: nowrap; }}
</style>
</head>
<body>
<main>
<h1>Стики супутників: чи стрибає гармонізований ряд</h1>
<p class="lead">Ряд календаря складає Terra до 3 липня 2002 року, Aqua до 19 січня 2012 року і Suomi NPP після.
Якщо гармонізація працює, на кожному стику дві лінії збігаються, і календар не показує зміни супутника.</p>

<h2>Стрибок на стику</h2>
<p>Відношення двох супутників у 12 місяцях від стику, лише в дні, коли летіли обидва: Aqua до Terra з липня 2002
року, Suomi NPP до Aqua з січня 2012 року. Число 0% означає, що стику не видно.</p>
<div class="card">{table(["область", "2002 без гармонізації", "2002 з гармонізацією", "2012 без гармонізації",
                          "2012 з гармонізацією"], steps)}</div>
<p style="margin-top:12px">Стик 2012 року майже не видно ніде. Стик 2002 року на світі малий, але в Бразилії
гармонізований ряд стрибає на +38,6%. Множник Terra вчиться на 2012–2021 роках, а в 2000-х роках у Бразилії
Aqua бачила відносно Terra на 20–49% більше, ніж потім. Тому місяці лише з Terra (листопад 2000 – липень 2002)
у Бразилії можуть бути занижені приблизно на третину, а в Україні й Австралії завищені приблизно на десяту
частину.</p>

<h2>Суми за 12 місяців</h2>
<div class="legend"><span><i class="ln" style="background:var(--s1)"></i>Terra, гармонізована</span>
<span><i class="ln" style="background:var(--s2)"></i>Aqua, гармонізована</span>
<span><i class="ln" style="background:var(--s3)"></i>Suomi NPP</span></div>
<p>Кожна точка — сума пожеж на рослинності за місяць і 11 місяців перед ним, у всі дні. Сірі вертикальні
лінії — стики 2002 і 2012 років. Наведіть на графік, щоб побачити числа.</p>
<div class="grid4" id="charts"></div>

<h2>Suomi NPP до гармонізованої Aqua за роками</h2>
<p>Ті самі дні, коли летіли обидва. Множники вчилися на 2012–2022 роках, тож це відхилення окремого року від
середнього.</p>
<div class="card">{table(["область"] + [str(y) for y in years], by_year)}</div>

<h2>Місяці, які заповнив NOAA-20</h2>
<p>У дні, коли Suomi NPP не дав жодної точки, ряд бере NOAA-20. Заповнений місяць світу має збігатися з самим
NOAA-20 за цей місяць. У липні 2024 року Suomi NPP дав частину точок у кілька днів, а такі дні не
заповнюються, тому місяць нижчий.</p>
<div class="card">{table(["місяць", "ряд, млн точок", "NOAA-20, млн точок", "різниця"], backups)}</div>

<h2>Як відтворити</h2>
<p>Потрібні річні архіви FIRMS 2000–2025 у <code>data/raw/archive/</code> теки зі скриптами даних і файли
версії методу. Замір читає їх функціями пакета <code>harmonize</code>, за дві хвилини:</p>
<p><code>python3 -I joins_probe.py parser parser/data/harmonization/{html.escape(data["version"])} results.json</code><br>
<code>python3 -I make_page.py results.json index.html</code></p>
</main>
<script>
(() => {{
  const D = {payload};
  const MONTHS = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"];
  const COLORS = ["var(--s1)", "var(--s2)", "var(--s3)"];
  const W = 540, H = 250, L = 72, R = 76, T = 12, B = 26;
  const first = 12, n = D.charts.world.snpp.length;
  const label = i => MONTHS[(i + first) % 12] + " " + (2000 + Math.floor((i + first) / 12));
  const fmt = v => v >= 1e6 ? (v / 1e6).toFixed(2).replace(".", ",") + " млн" : Math.round(v / 1e3) + " тис.";
  const box = document.getElementById("charts");
  for (const [key, name] of Object.entries(D.regions)) {{
    const lines = D.charts[key];
    const all = D.lines.flatMap(([s]) => lines[s].filter(v => v !== null));
    const top = Math.max(...all) * 1.08;
    const x = i => L + (W - L - R) * i / (n - 1);
    const y = v => T + (H - T - B) * (1 - v / top);
    const card = document.createElement("div");
    card.className = "card";
    let svg = `<h3>${{name}}</h3><svg viewBox="0 0 ${{W}} ${{H}}" role="img" aria-label="${{name}}: суми за 12 місяців">`;
    for (let k = 0; k <= 4; k++) {{
      const v = top * k / 4, yy = y(v);
      svg += `<line x1="${{L}}" x2="${{W - R}}" y1="${{yy}}" y2="${{yy}}" stroke="var(--grid)"/>`;
      svg += `<text x="${{L - 6}}" y="${{yy + 4}}" text-anchor="end">${{k ? fmt(v) : 0}}</text>`;
    }}
    for (let yr = 2001; yr <= 2025; yr += 4) {{
      const xx = x((yr - 2000) * 12 - first);
      svg += `<text x="${{xx}}" y="${{H - 8}}" text-anchor="middle">${{yr}}</text>`;
    }}
    for (const [m, txt] of [[(2002 - 2000) * 12 + 6, "2002"], [(2012 - 2000) * 12, "2012"]]) {{
      const xx = x(m - first);
      svg += `<line x1="${{xx}}" x2="${{xx}}" y1="${{T}}" y2="${{H - B}}" stroke="var(--rule)" stroke-dasharray="4 3"/>`;
    }}
    const ends = [];
    D.lines.forEach(([s, title], j) => {{
      let d = "", pen = false, last = null;
      lines[s].forEach((v, i) => {{
        if (v === null) {{ pen = false; return; }}
        d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
        pen = true; last = [i, v];
      }});
      svg += `<path d="${{d}}" fill="none" stroke="${{COLORS[j]}}" stroke-width="2" stroke-linejoin="round"/>`;
      if (last) ends.push({{x: x(last[0]) + 6, y: y(last[1]) + 4, text: title.split(",")[0]}});
    }});
    ends.sort((a, b) => a.y - b.y);
    for (let k = 1; k < ends.length; k++) ends[k].y = Math.max(ends[k].y, ends[k - 1].y + 13);
    for (const e of ends) svg += `<text x="${{e.x}}" y="${{e.y}}" style="fill:var(--ink-2)">${{e.text}}</text>`;
    svg += `<line class="cross" y1="${{T}}" y2="${{H - B}}" stroke="var(--ink-3)" visibility="hidden"/>`;
    svg += `<rect x="${{L}}" y="${{T}}" width="${{W - L - R}}" height="${{H - T - B}}" fill="transparent"/></svg>`;
    card.innerHTML = svg + `<div class="tip"></div>`;
    box.appendChild(card);
    const el = card.querySelector("svg"), cross = el.querySelector(".cross"), tip = card.querySelector(".tip");
    el.addEventListener("mousemove", ev => {{
      const pt = el.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
      const p = pt.matrixTransform(el.getScreenCTM().inverse());
      const i = Math.max(0, Math.min(n - 1, Math.round((p.x - L) / (W - L - R) * (n - 1))));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      tip.innerHTML = `<b>${{label(i)}}</b><br>` + D.lines.map(([s, t]) => lines[s][i] === null ? "" :
        `${{t}}: ${{fmt(lines[s][i])}}`).filter(Boolean).join("<br>");
      tip.style.display = "block";
      const r = card.getBoundingClientRect();
      tip.style.left = Math.min(ev.clientX - r.left + 14, r.width - 220) + "px";
      tip.style.top = (ev.clientY - r.top + 14) + "px";
    }});
    el.addEventListener("mouseleave", () => {{ cross.setAttribute("visibility", "hidden"); tip.style.display = "none"; }});
  }}
}})();
</script>
</body>
</html>
"""
    open(sys.argv[2], "w", encoding="utf-8").write(page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
