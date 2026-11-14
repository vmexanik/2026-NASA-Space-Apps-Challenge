# Підходи до гармонізації MODIS → VIIRS: що є в літературі

Пошук 2026-11-14. Підходи 1–8 перевірені в розвідці на Україні (`../гармонізація даних nasa/evidence/spike-ukraine/README.md`).
Підходи 9–15 нові, з літератури та власних міркувань, ще не перевірені.

## Нові підходи

| # | Підхід | Звідки | Можна з CSV FIRMS? |
|---|---|---|---|
| 9 | VIIRS 750 м (VNP14 / VJ114) замість 375 м: алгоритм-копія MODIS C6, зроблений саме для неперервності з MODIS 1 км | VNP14 ATBD, Csiszar 2014 | Ні: лише гранули з LAADS |
| 10 | Регресія на спільних роках (нахил і зсув, за біомом чи регіоном), як у QFED: FRP проти Aqua за біомами | CEOS AC-VC QFED (Collow) | Так |
| 11 | Квантильне зіставлення (CDF matching): розподіл MODIS накладаємо на розподіл VIIRS | Kaur 2019 (FRP поза надиром), MRBA60 (площа згарищ) | Так |
| 12 | Сума FRP замість числа точок | Li 2018: FRP двох датчиків близькі, ~20% на клітинках 1° | Так |
| 13 | Клітинко-дні: рахуємо клітинки з вогнем за день, а не пікселі | проєкти Space Apps 2026 (не перевірено) | Так |
| 14 | Поправка MODIS на кут огляду (край смуги бачить гірше) | Li 2018, Kaur 2019, Zheng 2026 | Так (`scan`, `track`) |
| 15 | Стягування до ширшого множника (shrinkage): у місці з малою кількістю точок множник тягнеться до множника країни | проєкти Space Apps 2026, emp. Bayes | Так |

Крок підготовки, не підхід: прибирати повтори VIIRS на перекритті смуг (до 5,4% точок, Li 2018; Zheng 2026).

## Джерела

- Csiszar et al. 2014, JGR Atmospheres 119(2) 803–816, doi:10.1002/2013JD020453 — VIIRS узгоджується з одночасними детекціями MODIS.
- Li, Zhang, Kondragunta, Csiszar 2018, JGR Atmospheres 123(9) 4545–4563, doi:10.1029/2017JD027823 — FRP VIIRS і MODIS порівнянні; MODIS залежить від кута огляду, VIIRS ні.
- Vadrevu & Lasko 2018, Remote Sensing 10(7) 978, doi:10.3390/rs10070978 — Пенджаб: VIIRS бачить у 4,8–6,5 раза більше вогнів, ніж MODIS.
- Kaur et al. 2019, Remote Sensing 11(10) 1205, doi:10.3390/rs11101205 — квантильне зіставлення FRP поза надиром з надиром.
- Zheng et al. 2026, Remote Sensing 18(10) 1650, doi:10.3390/rs18101650 — злиття MYD14 і VNP14IMG на масштабі пікселя MODIS.
- Chen et al. 2023, ESSD 15 5227–5259, doi:10.5194/essd-15-5227-2023 — GFED5: поправки за регіоном і типом землі з точніших знімків.
- Sofiev & Kouznetsov 2026, GMD 19 10123 — оператори спостереження FRP для MODIS і VIIRS (дискусійна версія).
- VNP14 ATBD: https://lpdaac.usgs.gov/documents/133/VNP14_ATBD.pdf
- CAMS: GFAS додає VIIRS з 2025-12-04: https://atmosphere.copernicus.eu/drifting-away-modis-cams-global-fire-assimilation-system
- QFED, масштабування за біомами: https://ceos.org/document_management/Virtual_Constellations/AC-VC/Meetings/AC-VC-22/Presentations/AC-VC_5.17_Collow_version1.pdf
