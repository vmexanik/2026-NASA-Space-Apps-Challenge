"""Builds the self-contained page index.html from results.json of noaa20_probe.py.

Run: python3 -I make_page.py results.json index.html
"""

from __future__ import annotations

import html
import json
import sys

WAYS = {"w1": "вага 1 (версія v1)", "const": "один множник світу", "month": "множник світу на місяць",
        "own": "свій множник квадрата 2° і місяця"}
AREAS = [("0.5", "області 0,5°"), ("2", "квадрати 2°"), ("8", "квадрати 8°"),
         ("Ukraine 2", "Україна, квадрати 2°"), ("Brazil 2", "Бразилія, квадрати 2°"),
         ("Australia 2", "Австралія, квадрати 2°"), ("Ukraine total", "Україна вся"),
         ("Brazil total", "Бразилія вся"), ("Australia total", "Австралія вся")]
COUNTRIES = {"Ukraine": "Україна", "Brazil": "Бразилія", "Australia": "Австралія"}
MONTHS = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"]


def pct(value: float | None) -> str:
    """A share as a percentage with one decimal and a decimal comma."""
    return "—" if value is None else f"{value * 100:.1f}%".replace(".", ",")


def num(value: float | None, digits: int = 3) -> str:
    """A number with a decimal comma."""
    return "—" if value is None else f"{value:.{digits}f}".replace(".", ",")


def table(head: list[str], rows: list[list[str]], marks: list[list[str]] | None = None) -> str:
    """An HTML table; marks holds a CSS class per cell, or an empty string."""
    out = ["<table><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in head) + "</tr>"]
    for i, row in enumerate(rows):
        cells = []
        for j, cell in enumerate(row):
            mark = marks[i][j] if marks else ""
            cells.append(f"<td class=\"{mark}\">{cell}</td>" if mark else f"<td>{cell}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(out) + "</table>"


def main() -> int:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    validation = data["validation"]
    years = [str(y) for y in data["years"]]
    common = sum(d["common"] for d in data["days"].values())

    rows, marks = [], []
    for key, label in AREAS:
        values = {way: validation[way][key]["error"] for way in WAYS}
        best = min(v for v in values.values() if v is not None)
        worst = max(v for v in values.values() if v is not None)
        rows.append([html.escape(label)] + [pct(values[w]) for w in WAYS])
        marks.append([""] + ["best" if values[w] == best else "worst" if values[w] == worst else "" for w in WAYS])
    errors = table(["область"] + list(WAYS.values()), rows, marks)

    calendar = table(["область"] + list(WAYS.values()),
                     [[html.escape(label)] + [pct(validation[w][key]["calendar"]) for w in WAYS]
                      for key, label in AREAS[:3]])

    year_rows = []
    for y in years:
        days = data["days"][y]
        year_rows.append([y, num(data["ratio_year"][y])]
                         + [num(data["ratio_country"][c][y]) for c in COUNTRIES]
                         + [str(days["common"]), str(days["noaa20_only"]), str(days["snpp_only"])])
    by_year = table(["рік", "світ"] + list(COUNTRIES.values())
                    + ["спільних днів", "лише NOAA-20", "лише Suomi NPP"], year_rows)

    by_month = table(["місяць"] + MONTHS, [["NOAA-20 / Suomi NPP"] + [num(r) for r in data["ratio_month"]]])
    by_lat = table(["широта", "NOAA-20, млн точок", "Suomi NPP, млн точок", "NOAA-20 / Suomi NPP"],
                   [[html.escape(band), num(n / 1e6, 2), num(s / 1e6, 2), num(r)]
                    for band, n, s, r in data["ratio_latitude"]])

    own = {row[0]: row for row in data["error_table"]["own"]}
    bounds = [row[0] for row in data["error_table"]["w1"]]
    count_rows = []
    for i, (n_min, rel, samples) in enumerate(data["error_table"]["w1"]):
        upper = f"–{bounds[i + 1] - 1}" if i + 1 < len(bounds) else "+"
        count_rows.append([f"{n_min}{upper}", pct(rel), pct(own[n_min][1]), f"{samples:,}".replace(",", " ")])
    by_count = table(["точок NOAA-20 у зоні за місяць", "похибка, вага 1", "похибка, свій множник",
                      "зон-місяців"], count_rows)

    spread = data["own_factor_spread"]
    w1, own2 = validation["w1"]["2"]["error"], validation["own"]["2"]["error"]
    ratio_all = data["points"]["noaa20"] / data["points"]["snpp"]
    page = f"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NOAA-20 проти Suomi NPP: чи годиться вага 1</title>
<style>
  :root {{ --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --grid: #e6e5e0;
           --best: #e3eefb; --worst: #fbe9e1; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --grid: #2e2e2c;
             --best: #1c3350; --worst: #44261a; }}
  }}
  body {{ margin: 0; background: var(--page); color: var(--ink);
          font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 56px; }}
  h1 {{ font-size: 28px; line-height: 1.25; margin: 0 0 10px; }}
  h2 {{ font-size: 21px; margin: 36px 0 10px; }}
  p {{ margin: 0 0 12px; max-width: 80ch; }}
  .lead {{ font-size: 18px; color: var(--ink-2); }}
  .verdict {{ background: var(--surface); border: 1px solid var(--grid); border-radius: 12px; padding: 14px 18px;
              margin: 20px 0; }}
  .card {{ background: var(--surface); border: 1px solid var(--grid); border-radius: 12px; padding: 12px 16px;
           overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }}
  th, td {{ padding: 5px 8px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ color: var(--ink-2); font-weight: 600; }}
  td.best {{ background: var(--best); font-weight: 650; }}
  td.worst {{ background: var(--worst); }}
  code {{ font-size: 13px; }}
</style>
</head>
<body>
<main>
<h1>NOAA-20 проти Suomi NPP: чи годиться вага 1</h1>
<p class="lead">Етап 6 дорожньої карти. Від 3 листопада 2026 року Suomi NPP мовчить, і ряд веде NOAA-20 з вагою 1.
Ще NOAA-20 заповнює 34 дні 2022–2024 років, коли Suomi NPP не дав жодної точки. Чи рахує NOAA-20 пожежі так само,
як Suomi NPP?</p>

<div class="verdict">
<p><b>Так. Вага 1 лишається.</b> На {common:,} спільних днях 2018–2025 NOAA-20 дав {num(ratio_all)} точки на одну
точку Suomi NPP. Власний множник квадрата 2° і місяця робить гірше, а не краще: помилка на квадратах 2°
{pct(w1)} з вагою 1 і {pct(own2)} зі своїм множником. Один множник світу помилку не змінює.</p>
<p>Що лишається: похибка NOAA-20 як заміни Suomi NPP. Її покаже застосунок: таблиця внизу піде в
<code>firms.method_error</code> замість нуля.</p>
</div>

<h2>Помилка: медіана |вгадане / справжнє − 1|</h2>
<p>Кожен рік вгадується з точок NOAA-20 цього року, множники вчаться на інших роках. Рахуються зони-місяці, де
Suomi NPP дав 100 і більше точок, як у перевірці версії. Синім найменша помилка рядка, червоним найбільша.</p>
<div class="card">{errors}</div>

<h2>Колір календаря збігається</h2>
<p>Частка зон-місяців, де вгадане й справжнє число дають той самий колір календаря.</p>
<div class="card">{calendar}</div>

<h2>Скільки точок NOAA-20 на одну точку Suomi NPP</h2>
<p>Лише пожежі на рослинності (type = 0), без фільтра впевненості, лише в дні, коли обидва супутники дали хоч одну
точку. Архів NOAA-20 починається з квітня 2018 року, тому того року лише {data["days"]["2018"]["common"]} спільних днів.</p>
<div class="card">{by_year}</div>
<h2>За місяцями і за широтою</h2>
<div class="card">{by_month}</div>
<div class="card" style="margin-top:12px">{by_lat}</div>

<h2>Чому свій множник не допомагає</h2>
<p>Множники квадратів, зважені за кількістю точок, лежать між {num(spread["0.1"])} (10%) і {num(spread["0.9"])} (90%),
медіана {num(spread["0.5"])}. Цей розкид дає випадковість, а не справжня різниця між датчиками: на роках, яких множник не бачив,
він вгадує гірше, ніж вага 1.</p>

<h2>Похибка за кількістю точок</h2>
<p>Медіана |справжнє − вгадане| / вгадане для зон-місяців 0,5°, 2° і 8° разом, за кількістю точок NOAA-20 у зоні.
Стовпчик «вага 1» стане рядками NOAA-20 у <code>firms.method_error</code>.</p>
<div class="card">{by_count}</div>

<h2>Як відтворити</h2>
<p>Потрібні річні архіви FIRMS <code>viirs-jpss1_2018…2025</code> і <code>viirs-snpp_2018…2025</code> у
<code>data/raw/archive/</code> теки зі скриптами даних (<code>parser/</code> репозиторію застосунку). Замір читає їх тими самими функціями пакета
<code>harmonize</code>, що й <code>build_factors.py</code>, за {data["seconds"]} с:</p>
<p><code>python3 -I noaa20_probe.py parser results.json</code><br>
<code>python3 -I make_page.py results.json index.html</code></p>
</main>
</body>
</html>
"""
    open(sys.argv[2], "w", encoding="utf-8").write(page.replace(f"{common:,}", f"{common:,}".replace(",", " ")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
