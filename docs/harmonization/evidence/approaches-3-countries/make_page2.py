#!/usr/bin/env python3
"""Build a self-contained HTML page from the output of evaluate.py: how the approaches were compared, the
algorithm of each approach as evaluate.py runs it, every approach against every criterion per country, the average
place, and a small chart per approach of its out-of-sample months against VIIRS.

Usage: python3 -I make_page2.py <results.json> <out.html>
"""
import json
import sys

SRC, OUT = sys.argv[1], sys.argv[2]
data = json.load(open(SRC, encoding="utf-8"))
names = {int(k): v for k, v in data["names"].items()}
UA = {"Ukraine": "Україна", "Brazil": "Бразилія", "Australia": "Австралія"}
CRIT = [("err", "low"), ("cell", "low"), ("cal", "high"), ("stab", "low"), ("bias", "abs")]

ranks = {}
for country, block in data["countries"].items():
    res = {int(a): r for a, r in block["results"].items()}
    for key, kind in CRIT:
        vals = {a: r[key] for a, r in res.items() if r[key] is not None}
        order = sorted(vals, key=lambda a: -vals[a] if kind == "high" else abs(vals[a]))
        for place, a in enumerate(order, 1):
            ranks.setdefault(a, {}).setdefault(country, []).append(place)
summary = []
for a in names:
    per = {c: sum(v) / len(v) for c, v in ranks.get(a, {}).items()}
    allr = [x for v in ranks.get(a, {}).values() for x in v]
    summary.append({"a": a, "name": names[a], "per": per, "avg": sum(allr) / len(allr)})
summary.sort(key=lambda s: s["avg"])


def num(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def pairs(key):
    out = []
    for c, block in data["countries"].items():
        runs = block["info"][key]
        out.append(f"{UA[c]} " + " і ".join("/".join(num(w) for w in run) for run in runs))
    return "; ".join(out)


betas = "; ".join(f"{UA[c]} " + " і ".join(num(b) for b in block["info"]["beta10"])
                  for c, block in data["countries"].items())

# The algorithm of each approach, as evaluate.py runs it. M and V are the MODIS (Aqua) and VIIRS (Suomi NPP)
# points of a month, m its calendar month, the sums run over the learning months.
ALG = {
    1: {"idea": "Усі точки MODIS множаться на одне число.",
        "learn": "k = ΣV / ΣM по всіх навчальних місяцях.",
        "predict": "V̂ = k · M.",
        "params": "немає",
        "unit": "точки VIIRS",
        "risk": "Не знає сезону: улітку VIIRS бачить у рази більше, ніж восени."},
    2: {"idea": "Своє число на кожен календарний місяць.",
        "learn": "k<sub>m</sub> = ΣV / ΣM лише по навчальних місяцях m (наприклад, усіх червнях).",
        "predict": "V̂ = k<sub>m</sub> · M.",
        "params": "немає",
        "unit": "точки VIIRS",
        "risk": "Одне число на всю країну: не бачить, що в різних місцях пожежі різні."},
    3: {"idea": "Своє число на кожен квадрат 2° × 2° і календарний місяць.",
        "learn": "Для квадрата c і місяця m: якщо ΣM<sub>c</sub> ≥ 30, то k<sub>c,m</sub> = ΣV<sub>c</sub> / ΣM<sub>c</sub>; "
                 "інакше береться k<sub>m</sub> країни з №2.",
        "predict": "V̂<sub>c</sub> = k<sub>c,m</sub> · M<sub>c</sub>; число країни — сума квадратів.",
        "params": "поріг 30 точок MODIS",
        "unit": "точки VIIRS",
        "risk": "Різкий перескок на порозі: квадрат з 31 точкою вже вірить лише собі, хоча 31 точка — це шум."},
    4: {"idea": "Як №2, але слабка точка MODIS важить інакше, ніж сильна.",
        "learn": "Точки MODIS діляться на слабкі (FRP < 10 МВт) і сильні (≥ 10 МВт). Ваги й множники підбираються по "
                 "черзі 20 разів: при сталих вагах k<sub>m</sub> рахується як у №2; при сталих k<sub>m</sub> ваги — "
                 "найменші квадрати відносної помилки місяця. Вага не менша 0,05; ваги масштабуються так, щоб "
                 "у середньому точка важила 1.",
        "predict": "V̂ = k<sub>m</sub> · (w<sub>слаб</sub> · M<sub>слаб</sub> + w<sub>сильн</sub> · M<sub>сильн</sub>).",
        "params": "межа 10 МВт, 20 кроків, вага ≥ 0,05",
        "unit": "точки VIIRS",
        "risk": "Знайдені ваги (слабкі/сильні) у прогоні 1 і 2: " + pairs("w_frp") +
                ". Ваги стрибають між прогонами: модель підганяє шум."},
    5: {"idea": "Порівнюємо лише те, що бачать обидва: день і вогні від 10 МВт.",
        "learn": "Беруться лише денні рядки. MODIS: точки з FRP ≥ 10 МВт. VIIRS: рядки одного прольоту (новий проліт — "
                 "коли пауза понад 20 хвилин) склеюються в клітинки ~1 км (0,01° широти × 0,01°/cos(широти) довготи), "
                 "FRP у клітинці додається; рахуються клітинки із сумою ≥ 10 МВт. Далі як №2: "
                 "k<sub>m</sub> = ΣV<sup>планка</sup> / ΣM<sup>планка</sup>.",
        "predict": "V̂<sup>планка</sup> = k<sub>m</sub> · M<sup>планка</sup>.",
        "params": "планка 10 МВт, клітинка ~1 км, пауза між прольотами 20 хв",
        "unit": "клітинки VIIRS ~1 км із силою ≥ 10 МВт, лише день",
        "risk": "Ряд лише про сильні денні пожежі: лишається 35–47% точок VIIRS."},
    6: {"idea": "Число вчиться лише на прольотах, де обидва супутники пройшли майже одночасно.",
        "learn": "Прольоти Aqua й Suomi NPP із різницею середнього часу до 10 хвилин утворюють пару. У парах лишаються "
                 "точки ближче до середини смуги: MODIS scan ≤ 1,3 км, VIIRS scan ≤ 0,45 км. "
                 "k<sub>m</sub> = ΣV<sup>пари</sup> / ΣM<sup>пари</sup>.",
        "predict": "V̂ = k<sub>m</sub> · M (на всіх точках MODIS місяця).",
        "params": "10 хвилин, scan ≤ 1,3 і ≤ 0,45",
        "unit": "точки VIIRS",
        "risk": "Межі смуги в даних немає, тому обрізання до середини — наближення. Число з середини смуги "
                "застосовується до всієї смуги."},
    7: {"idea": "Без множника: кожен датчик порівнюється зі своєю нормою.",
        "learn": "Норма датчика N<sub>m</sub> — середнє за 2012–2022 для календарного місяця m, окремо для MODIS і VIIRS.",
        "predict": "Колір місяця з M / N<sub>m</sub><sup>MODIS</sup> порівнюється з кольором з V / N<sub>m</sub><sup>VIIRS</sup>.",
        "params": "межі кольорів 0,5 · 0,8 · 1,25 · 2",
        "unit": "лише колір календаря, чисел немає",
        "risk": "Не каже, скільки горіло; норма рахується на всіх роках, тож це не перевірка на чужих роках."},
    8: {"idea": "Модель вгадує множник місяця з його ознак.",
        "learn": "Ціль — log(V / M) місяця. 7 ознак: log(1 + M), частка точок MODIS ≥ 10 МВт, частка нічних точок MODIS, "
                 "середній scan MODIS, sin і cos календарного місяця, рік. Гребенева регресія (λ = 1) на "
                 "стандартизованих ознаках, по навчальних місяцях.",
        "predict": "V̂ = M · e<sup>прогноз</sup> · поправка (середнє e<sup>залишку</sup> на навчальних місяцях).",
        "params": "λ = 1",
        "unit": "точки VIIRS",
        "risk": "60–72 навчальні місяці на 7 ознак; ознака «рік» тягне прогноз за межі навчальних років."},
    10: {"idea": "Зв'язок не обов'язково пропорційний.",
         "learn": "log V = a<sub>m</sub> + β · log M, найменші квадрати по навчальних місяцях. Знайдені β у прогоні 1 і 2: "
                  + betas + ".",
         "predict": "V̂ = e<sup>a<sub>m</sub></sup> · M<sup>β</sup> · поправка (як у №8).",
         "params": "немає",
         "unit": "точки VIIRS",
         "risk": "β < 1 означає «що більше пожеж, то менше точок VIIRS на точку MODIS»; на чужих роках β змінюється."},
    11: {"idea": "Розподіл місячних чисел MODIS «натягується» на розподіл VIIRS.",
         "learn": "Навчальні місячні M і V (усі календарні місяці разом) сортуються окремо.",
         "predict": "Для місяця перевірки знаходиться місце (квантиль) M серед навчальних M і береться V з того самого "
                    "місця. Поза межами навчальних чисел — множиться на крайнє співвідношення.",
         "params": "немає",
         "unit": "точки VIIRS",
         "risk": "Зіставляє за рангом і не знає сезону: однаково великі березень і серпень отримують однакове число."},
    12: {"idea": "Рахується не кількість точок, а сума сили вогню.",
         "learn": "M<sup>FRP</sup> і V<sup>FRP</sup> — сума FRP усіх точок місяця (МВт); k<sub>m</sub> як у №2.",
         "predict": "V̂<sup>FRP</sup> = k<sub>m</sub> · M<sup>FRP</sup>.",
         "params": "немає",
         "unit": "МВт, сума FRP VIIRS",
         "risk": "Кілька великих пожеж важать більше, ніж тисячі малих."},
    13: {"idea": "Рахується, скільки клітинок ~1 км горіло за день.",
         "learn": "Для кожного датчика — кількість різних пар «день × клітинка ~1 км» з хоча б однією точкою; "
                  "k<sub>m</sub> як у №2.",
         "predict": "V̂<sup>кд</sup> = k<sub>m</sub> · M<sup>кд</sup>.",
         "params": "клітинка ~1 км, доба UTC",
         "unit": "клітинко-дні VIIRS",
         "risk": "Залежить від розміру клітинки; дві пожежі в одній клітинці за день рахуються як одна."},
    14: {"idea": "Як №4, але вага залежить від розміру пікселя MODIS (край смуги).",
         "learn": "Як №4, але класи за scan MODIS: < 1,5 км і ≥ 1,5 км. Знайдені ваги (центр/край) у прогоні 1 і 2: "
                  + pairs("w_scan") + ".",
         "predict": "V̂ = k<sub>m</sub> · (w<sub>центр</sub> · M<sub>центр</sub> + w<sub>край</sub> · M<sub>край</sub>).",
         "params": "межа 1,5 км, 20 кроків, вага ≥ 0,05",
         "unit": "точки VIIRS",
         "risk": "Ті самі стрибки ваг, що й у №4."},
    15: {"idea": "Як №3, але число квадрата плавно тягнеться до числа країни.",
         "learn": "k<sub>c,m</sub> = (ΣV<sub>c</sub> + λ · k<sub>m</sub>) / (ΣM<sub>c</sub> + λ), λ = 100. До даних "
                  "квадрата ніби додаються 100 точок MODIS з множником країни: мало своїх точок — число ≈ країни, "
                  "багато — ≈ своє.",
         "predict": "V̂<sub>c</sub> = k<sub>c,m</sub> · M<sub>c</sub>; число країни — сума квадратів.",
         "params": "λ = 100 точок MODIS (не підбиралось)",
         "unit": "точки VIIRS",
         "risk": "Сила стягування λ взята навмання; для світу треба вирішити, до чого стягувати (країна, регіон, біом)."},
}

payload = {"names": names, "countries": data["countries"], "summary": summary, "ua": UA, "alg": ALG}

html = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>14 підходів гармонізації на трьох країнах</title>
<style>
  :root {
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #6f6e69;
    --grid: #e6e5e0; --rule: #b9b8b1; --best: #e3eefb; --worst: #fbe9e1; --learn: #ecebe6;
    --s1: #2a78d6;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9d9c93;
      --grid: #2e2e2c; --rule: #5a5955; --best: #1c3350; --worst: #44261a; --learn: #2a2a28;
      --s1: #3987e5;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--ink);
         font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 1100px; margin: 0 auto; padding: 32px 20px 56px; }
  h1 { font-size: 28px; line-height: 1.25; margin: 0 0 10px; }
  h2 { font-size: 21px; margin: 44px 0 10px; }
  h3 { font-size: 16px; margin: 0 0 6px; }
  p { margin: 0 0 12px; max-width: 78ch; }
  a { color: var(--s1); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .lead { font-size: 18px; color: var(--ink-2); }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin: 24px 0; }
  .tile, .card { background: var(--surface); border: 1px solid var(--grid); border-radius: 12px; }
  .tile { padding: 14px 16px; }
  .tile .k { font-size: 13px; color: var(--ink-2); }
  .tile .v { font-size: 22px; font-weight: 650; margin-top: 2px; line-height: 1.25; }
  .tile .s { font-size: 13px; color: var(--ink-3); margin-top: 4px; }
  .card { padding: 16px 18px; position: relative; overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; }
  th, td { padding: 6px 7px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  th:first-child, td:first-child, th.l, td.l { text-align: left; }
  th { color: var(--ink-2); font-weight: 600; vertical-align: bottom; }
  td.best { background: var(--best); font-weight: 650; border-radius: 4px; }
  td.worst { background: var(--worst); border-radius: 4px; }
  td.na { color: var(--ink-3); }
  tr.win td { font-weight: 600; }
  .tabs { display: flex; gap: 6px; margin: 0 0 12px; flex-wrap: wrap; position: sticky; top: 0; z-index: 2;
          background: var(--page); padding: 8px 0; }
  .tabs button { font: inherit; font-size: 14px; padding: 6px 14px; border-radius: 999px; border: 1px solid var(--grid);
                 background: var(--surface); color: var(--ink-2); cursor: pointer; }
  .tabs button[aria-pressed="true"] { background: var(--ink); color: var(--surface); border-color: var(--ink); }
  .split { display: grid; grid-template-columns: 110px repeat(11, 1fr); gap: 3px; font-size: 12.5px; margin: 10px 0 4px; max-width: 900px; }
  .split div { padding: 4px 0; text-align: center; border-radius: 4px; }
  .split .lbl { text-align: left; color: var(--ink-2); }
  .split .yr { color: var(--ink-3); }
  .split .learn { background: var(--learn); color: var(--ink-2); }
  .split .test { background: var(--best); color: var(--ink); font-weight: 600; }
  ol, ul { padding-left: 22px; max-width: 82ch; }
  li { margin-bottom: 6px; }
  code { font-size: 13.5px; }
  .muted { color: var(--ink-3); font-size: 13.5px; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13.5px; color: var(--ink-2); margin: 4px 0 10px; }
  .legend span { display: inline-flex; align-items: center; gap: 7px; }
  .sw { width: 14px; height: 3px; border-radius: 2px; display: inline-block; flex: none; }
  .multi { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 12px; }
  .mini { background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 10px 12px 6px; position: relative; }
  .mini h3 { font-size: 14px; }
  .mini .meta { font-size: 12.5px; color: var(--ink-3); margin-bottom: 2px; }
  svg { display: block; width: 100%; height: auto; }
  .axis text { fill: var(--ink-3); font-size: 11px; font-variant-numeric: tabular-nums; }
  .grid line { stroke: var(--grid); }
  .tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink);
         border: 1px solid var(--grid); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.16);
         padding: 7px 10px; font-size: 12.5px; min-width: 200px; display: none; z-index: 5; }
  .tip .y { font-weight: 650; margin-bottom: 3px; }
  .tip .r { display: flex; align-items: center; gap: 8px; }
  .tip .r b { margin-left: auto; font-variant-numeric: tabular-nums; }
  .algs { display: grid; grid-template-columns: repeat(auto-fill, minmax(480px, 1fr)); gap: 12px; }
  .alg { background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 12px 14px; scroll-margin-top: 60px; }
  .alg:target { outline: 2px solid var(--s1); }
  .alg dl { display: grid; grid-template-columns: 112px 1fr; gap: 4px 12px; margin: 6px 0 0; font-size: 14px; }
  .alg dt { color: var(--ink-3); }
  .alg dd { margin: 0; }
  .crit { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; max-width: 980px; }
  .crit dt { font-weight: 650; }
  .crit dd { margin: 0; color: var(--ink-2); }
</style>
</head>
<body>
<main>
  <h1>14 підходів гармонізації на трьох країнах</h1>
  <p class="lead">Кожен підхід бере точки MODIS (Aqua) за місяць і вгадує, скільки за той самий місяць дав би VIIRS (Suomi NPP).
  Перевіряємо лише на роках, яких підхід не бачив. Україна, Бразилія, Австралія, 2012–2022, лише пожежі на рослинності (<code>type = 0</code>).</p>

  <div class="tiles" id="tiles"></div>

  <h2>Як ми порівнювали</h2>
  <ol>
    <li><b>Дані.</b> Готові файли країн з архіву FIRMS (<code>modis_&lt;рік&gt;_all_countries.zip</code>,
      <code>viirs-snpp_&lt;рік&gt;_all_countries.zip</code>), лише рядки з <code>type = 0</code>. З MODIS — лише Aqua:
      він пролітає о ~13:30, як і Suomi NPP. 132 місяці на країну.</li>
    <li><b>Два прогони.</b> Підхід вчиться на одних роках і вгадує інші. Потім навпаки. Так кожен місяць отримує рівно
      одне «чесне» передбачення — з років, яких підхід не бачив.
      <div class="split" id="split"></div></li>
    <li><b>Критерії.</b> Усі рахуються на цих чесних передбаченнях (опис нижче). Для середнього місця підходи ставляться
      на місця 1–13 за кожним з п'яти критеріїв: помилка країни, помилка клітинки, календар, стабільність, зсув.</li>
  </ol>

  <h2>Підсумок: середнє місце</h2>
  <p>Чим менше число, тим краще. Назва веде до алгоритму підходу.</p>
  <div class="card"><table id="summary"></table></div>
  <p class="muted">№7 не дає чисел, лише колір календаря, тому має місце тільки за одним критерієм. №5 бере лише частину вогнів.</p>

  <h2>По країнах</h2>
  <div class="tabs" id="tabs"></div>
  <div class="card"><table id="detail"></table></div>
  <p class="muted">Синім — найкращий у стовпчику, червонуватим — найгірший.</p>

  <h3 style="margin-top:22px">Кожен підхід на графіку</h3>
  <div class="legend">
    <span><i class="sw" style="background:var(--ink-2);height:4px"></i>справжній VIIRS (в одиниці підходу)</span>
    <span><i class="sw" style="background:var(--s1)"></i>що вгадав підхід — на роках, яких не бачив</span>
    <span>пунктир — межа двох прогонів</span>
  </div>
  <div class="multi" id="multi"></div>

  <h2>Що означає кожен критерій</h2>
  <dl class="crit">
    <dt>Помилка, країна</dt><dd>Медіана |вгадане / справжнє − 1| по місяцях, де VIIRS дав 100 і більше точок. Менше — краще.</dd>
    <dt>Помилка, клітинка 2°</dt><dd>Те саме для квадратів 2° × 2° (~200 × 200 км), клітинко-місяці зі 100+ точками VIIRS.
      Так застосунок покаже будь-яке місце. Менше — краще.</dd>
    <dt>Календар</dt><dd>Місяць ділиться на середнє цього календарного місяця за 2012–2022 справжнього ряду. Межі кольорів
      0,5 · 0,8 · 1,25 · 2 (далеко нижче, нижче, звично, вище, далеко вище). Частка місяців, де колір вгаданого збігся
      з кольором справжнього; «±1» — збігся або сусідній. Лише календарні місяці, де VIIRS у середньому дає 100+ точок. Більше — краще.</dd>
    <dt>Стабільність</dt><dd>Стандартне відхилення по 11 роках від log(сума вгаданого за рік / сума справжнього). Велике — підхід ловить шум. Менше — краще.</dd>
    <dt>Зсув</dt><dd>e<sup>середнє log(вгадане / справжнє)</sup> − 1. Стабільне завищення чи заниження — саме воно дає сходинку на стику 2012 року. Ближче до нуля — краще.</dd>
    <dt>Бере вогнів</dt><dd>Яку частку точок VIIRS підхід лишає у своєму ряді. 100% — усі вогні.</dd>
  </dl>

  <h2>Алгоритм кожного підходу</h2>
  <p>Так, як його рахує <code>evaluate.py</code>. M і V — точки MODIS (Aqua) і VIIRS (Suomi NPP) за місяць, m — календарний
  місяць, c — квадрат 2°, Σ — сума по навчальних місяцях, V̂ — вгадане.</p>
  <div class="algs" id="algs"></div>

  <h2>Попередній висновок (ще не рішення)</h2>
  <ul>
    <li><b>№15</b> і <b>№3</b> — найкращі з тих, що беруть усі вогні. №15 має найменшу помилку на клітинках 2° серед них
      в усіх трьох країнах і не має різкого порогу, тому краще поводиться там, де пожеж мало.</li>
    <li><b>№5</b> найточніший, але його ряд — лише сильні денні пожежі (35–47% точок VIIRS).</li>
    <li><b>№7</b> дає колір календаря так само добре, як №2, без жодного множника, але без чисел.</li>
    <li>Вага за силою вогню (№4) і розміром пікселя (№14) не переноситься на інші роки.</li>
  </ul>

  <h2>Застереження</h2>
  <ul>
    <li>№4 і №14: пробували 4 класи й 2 класи; на сторінці 2 класи, вони менше підганяють шум. Ваги стрибають в обох варіантах.</li>
    <li>№6: межі смуги в даних немає, тому обрізання до середини смуги — наближення.</li>
    <li>№8: проста гребенева регресія з 7 ознак, а не велика модель.</li>
    <li>№15: сила стягування — 100 точок MODIS, не підбиралась.</li>
    <li>В Україні лише 36 квадратів 2°, у Бразилії 221, в Австралії 227.</li>
    <li>Різниця менше 1–2 відсоткових пунктів — у межах шуму.</li>
  </ul>

  <h2>Як відтворити</h2>
  <p>Скрипти лежать поруч зі сторінкою: <code>extract.py</code> вирізає рядки трьох країн з річних архівів FIRMS,
  <code>evaluate.py</code> рахує всі підходи, <code>make_page2.py</code> будує цю сторінку. Сирі числа — <code>results.json</code>
  і <code>result_evaluate.txt</code>.</p>
</main>
<div class="tip" id="tip"></div>
<script>
(() => {
const D = __DATA__;
const pct = (x, sign) => x == null ? "—" : (sign && x > 0 ? "+" : "") + (x * 100).toFixed(1).replace(".", ",") + "%";
const COUNTRIES = Object.keys(D.countries);
const IDS = Object.keys(D.names).map(Number);
const link = a => `<a href="#a${a}">${D.names[a]}</a>`;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const UNIT = {5: "клітинки ≥ 10 МВт", 12: "МВт", 13: "клітинко-дні", 7: "частка норми"};
const MONTHS = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"];

// tiles
const res = (c, a) => D.countries[c].results[a];
const avg = a => D.summary.find(s => s.a === a).avg.toFixed(1).replace(".", ",");
const lead = D.summary[0];
document.getElementById("tiles").innerHTML = `
  <div class="tile"><div class="k">Найкращі серед тих, що беруть усі вогні</div>
    <div class="v">№15 і №3, нарівно</div>
    <div class="s">середнє місце ${avg(15)} і ${avg(3)}; №15 має найменшу помилку на клітинках 2° серед них в усіх трьох країнах</div></div>
  <div class="tile"><div class="k">Найкраще середнє місце взагалі</div>
    <div class="v">№${lead.a} ${lead.name}</div>
    <div class="s">але бере лише ${pct(res("Ukraine", lead.a).kept)}–${pct(res("Australia", lead.a).kept)} точок VIIRS</div></div>
  <div class="tile"><div class="k">Найгірші</div>
    <div class="v">№1, №8, №11</div>
    <div class="s">один множник, машинне навчання, квантильне зіставлення</div></div>`;

// the two runs
const sp = document.getElementById("split");
let h = `<div class="lbl"></div>` + Array.from({length: 11}, (_, i) => `<div class="yr">${String(2012 + i).slice(2)}</div>`).join("");
h += `<div class="lbl">Прогін 1</div>` + Array.from({length: 11}, (_, i) => i < 5 ? `<div class="learn">вчимо</div>` : `<div class="test">вгадуємо</div>`).join("");
h += `<div class="lbl">Прогін 2</div>` + Array.from({length: 11}, (_, i) => i < 5 ? `<div class="test">вгадуємо</div>` : `<div class="learn">вчимо</div>`).join("");
sp.innerHTML = h;

// summary
document.getElementById("summary").innerHTML =
  `<thead><tr><th>№</th><th class="l">Підхід</th>${COUNTRIES.map(c => `<th>${D.ua[c]}</th>`).join("")}<th>Разом</th></tr></thead><tbody>` +
  D.summary.map((s, i) => `<tr class="${i < 3 ? "win" : ""}"><td>${s.a}</td><td class="l">${link(s.a)}</td>` +
    COUNTRIES.map(c => `<td>${s.per[c] != null ? s.per[c].toFixed(1).replace(".", ",") : "—"}</td>`).join("") +
    `<td>${s.avg.toFixed(1).replace(".", ",")}</td></tr>`).join("") + "</tbody>";

// detail table
const COLS = [["err", "Помилка,<br>країна", "low"], ["cell", "Помилка,<br>клітинка 2°", "low"], ["cal", "Календар:<br>той самий колір", "high"],
              ["cal1", "Календар:<br>±1 колір", "high"], ["stab", "Стабільність", "low"], ["bias", "Зсув", "abs"], ["kept", "Бере<br>вогнів", "high"]];
function detail(c) {
  const R = D.countries[c].results, ext = {};
  for (const [k, , kind] of COLS) {
    const v = IDS.filter(a => R[a][k] != null).map(a => kind === "abs" ? Math.abs(R[a][k]) : R[a][k]);
    v.sort((p, q) => kind === "high" ? q - p : p - q);
    ext[k] = {best: v[0], worst: v[v.length - 1], kind};
  }
  const cls = (k, x) => {
    if (x == null) return "na";
    const e = ext[k], y = e.kind === "abs" ? Math.abs(x) : x;
    if (e.best === e.worst) return "";
    return Math.abs(y - e.best) < 1e-9 && k !== "kept" ? "best" : Math.abs(y - e.worst) < 1e-9 ? "worst" : "";
  };
  document.getElementById("detail").innerHTML =
    `<thead><tr><th>№</th><th class="l">Підхід</th>${COLS.map(([, t]) => `<th>${t}</th>`).join("")}</tr></thead><tbody>` +
    IDS.map(a => `<tr><td>${a}</td><td class="l">${link(a)}</td>` +
      COLS.map(([k]) => `<td class="${cls(k, R[a][k])}">${pct(R[a][k], k === "bias")}</td>`).join("") + "</tr>").join("") + "</tbody>";
}

// small multiples
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); parent.appendChild(e); return e; };
function niceMax(v) { if (!(v > 0)) return 1; const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p; return 10 * p; }
const short = v => v >= 1e6 ? (v / 1e6).toLocaleString("uk-UA", {maximumFractionDigits: 1}) + " млн" :
                   v >= 1e3 ? (v / 1e3).toLocaleString("uk-UA", {maximumFractionDigits: 1}) + " тис." :
                   v.toLocaleString("uk-UA", {maximumFractionDigits: 2});
const fmt = v => Number.isFinite(v) ? (Math.abs(v) < 20 ? v.toLocaleString("uk-UA", {maximumFractionDigits: 2}) : Math.round(v).toLocaleString("uk-UA")) : "—";
const tip = document.getElementById("tip");

function mini(parent, a, c) {
  const S = D.countries[c].series, R = D.countries[c].results[a];
  const truth = a === 7 ? S.rel7.viirs : S.target[a];
  const guess = a === 7 ? S.rel7.modis : S.pred[a];
  const n = truth.length;
  const box = document.createElement("div");
  box.className = "mini";
  const meta = a === 7 ? `календар ${pct(R.cal)} · одиниця: ${UNIT[7]} (сіра — VIIRS, синя — MODIS)`
                       : `помилка ${pct(R.err)} · календар ${pct(R.cal)} · одиниця: ${UNIT[a] || "точки"}`;
  box.innerHTML = `<h3>№${a} ${link(a)}</h3><div class="meta">${meta}</div>`;
  parent.appendChild(box);
  const W = 340, H = 140, L = 60, Rr = 8, T = 8, B = 20;
  const svg = el("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `№${a}: справжнє і вгадане за місяцями`}, box);
  const vmax = niceMax(Math.max(...truth.filter(Number.isFinite), ...guess.filter(Number.isFinite)) * 1.04);
  const x = i => L + i / (n - 1) * (W - L - Rr), y = v => T + (1 - v / vmax) * (H - T - B);
  const g = el("g", {class: "grid"}, svg), ax = el("g", {class: "axis"}, svg);
  for (const f of [0, 0.5, 1]) { el("line", {x1: L, x2: W - Rr, y1: y(vmax * f), y2: y(vmax * f)}, g);
    el("text", {x: L - 6, y: y(vmax * f) + 4, "text-anchor": "end"}, ax).textContent = f === 0 ? "0" : short(vmax * f); }
  for (const yr of [2012, 2017, 2022]) el("text", {x: x((yr - 2012) * 12 + 6), y: H - 5, "text-anchor": "middle"}, ax).textContent = yr;
  el("line", {x1: x(59.5), x2: x(59.5), y1: T, y2: H - B, stroke: css("--rule"), "stroke-dasharray": "3 3"}, svg);
  if (a === 7 && vmax > 1) el("line", {x1: L, x2: W - Rr, y1: y(1), y2: y(1), stroke: css("--rule"), "stroke-dasharray": "1 3"}, svg);
  const path = (arr, color, w) => { let d = ""; arr.forEach((v, i) => { if (Number.isFinite(v)) d += (d ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1); });
    el("path", {d, fill: "none", stroke: color, "stroke-width": w, "stroke-linejoin": "round"}, svg); };
  path(truth, css("--ink-2"), 1.8); path(guess, css("--s1"), 1.3);
  const cross = el("line", {y1: T, y2: H - B, stroke: css("--rule"), visibility: "hidden"}, svg);
  const hit = el("rect", {x: L, y: T, width: W - L - Rr, height: H - T - B, fill: "transparent"}, svg);
  hit.addEventListener("mousemove", ev => {
    const p = svg.createSVGPoint(); p.x = ev.clientX; p.y = ev.clientY;
    const q = p.matrixTransform(svg.getScreenCTM().inverse());
    const i = Math.max(0, Math.min(n - 1, Math.round((q.x - L) / (W - L - Rr) * (n - 1))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    const off = Number.isFinite(guess[i]) && truth[i] > 0 ? ` (${pct(guess[i] / truth[i] - 1, true)})` : "";
    tip.innerHTML = `<div class="y">${MONTHS[i % 12]} ${2012 + Math.floor(i / 12)} · №${a}</div>` +
      `<div class="r"><i class="sw" style="background:var(--ink-2)"></i>${a === 7 ? "VIIRS / норма" : "справжнє"}<b>${fmt(truth[i])}</b></div>` +
      `<div class="r"><i class="sw" style="background:var(--s1)"></i>${a === 7 ? "MODIS / норма" : "вгадане"}<b>${fmt(guess[i])}${off}</b></div>`;
    tip.style.display = "block";
    let left = ev.clientX + 14; if (left + tip.offsetWidth > innerWidth - 8) left = ev.clientX - tip.offsetWidth - 14;
    tip.style.left = left + "px"; tip.style.top = (ev.clientY + 14) + "px";
  });
  hit.addEventListener("mouseleave", () => { tip.style.display = "none"; cross.setAttribute("visibility", "hidden"); });
}

let current = COUNTRIES[0];
function multi(c) { const m = document.getElementById("multi"); m.innerHTML = ""; for (const a of IDS) mini(m, a, c); }

// algorithms
document.getElementById("algs").innerHTML = IDS.map(a => { const A = D.alg[a]; return `
  <div class="alg" id="a${a}"><h3>№${a} ${D.names[a]}</h3>
    <dl><dt>Ідея</dt><dd>${A.idea}</dd><dt>Чого вчиться</dt><dd>${A.learn}</dd><dt>Як рахує місяць</dt><dd>${A.predict}</dd>
    <dt>Параметри</dt><dd>${A.params}</dd><dt>Одиниця ряду</dt><dd>${A.unit}</dd><dt>Слабке місце</dt><dd>${A.risk}</dd></dl></div>`; }).join("");

const tabs = document.getElementById("tabs");
function select(c) { current = c; for (const b of tabs.children) b.setAttribute("aria-pressed", b.dataset.c === c); detail(c); multi(c); }
for (const c of COUNTRIES) { const b = document.createElement("button"); b.textContent = D.ua[c]; b.dataset.c = c; b.onclick = () => select(c); tabs.appendChild(b); }
select(new URLSearchParams(location.search).get("c") || COUNTRIES[0]);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => multi(current));
})();
</script>
</body>
</html>
"""
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(html.replace("__DATA__", json.dumps(payload, ensure_ascii=False)))
print("wrote", OUT)
for s in summary:
    print(s["a"], s["name"], round(s["avg"], 2), {k: round(v, 1) for k, v in s["per"].items()})
