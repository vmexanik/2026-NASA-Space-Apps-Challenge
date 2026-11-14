# Скрипти даних FIRMS

У цій теці лежать скрипти, які завантажують точки пожеж FIRMS з сайту NASA, рахують множники гармонізації MODIS
і VIIRS і збирають пакет дампу. З пакета скрипт `restore.sh` розгортає схему `firms` у базі застосунку.
Застосунок читає дані лише з цієї схеми.

Як зібрати власну базу для будь-яких країн або для всього світу, крок за кроком описано в
[docs/deploy.md](docs/deploy.md). Як застосунок читає базу, описано в
[../docs/database/README.md](../docs/database/README.md).

| Шлях | Що робить |
|---|---|
| `fetch_archive.py` | Завантажує річні архіви FIRMS усього світу в `data/raw/archive/`. MAP_KEY не потрібен |
| `fetch_current_year.py` | Завантажує поточний рік з API FIRMS у `data/raw/api/`. Потрібен `FIRMS_MAP_KEY` у змінній середовища або в `parser/.env` |
| `firms_client.py` | Командний рядок для API FIRMS: стан ключа, доступні дати, точки однієї області |
| `build_factors.py` | Рахує множники гармонізації й пише версію методу в `data/harmonization/<версія>/` |
| `export_dump.py` | Збирає пакет дампу для світу або вибраних країн у `data/dump/<назва>/` |
| `make_test_dump.sh` | Збирає тестовий пакет України в `data/dump/test-ukraine/` |
| `firms/` | Клієнт API FIRMS, завантаження архівів, моделі даних |
| `harmonize/` | Код `build_factors.py`: підрахунки, множники, ряд, перевірка |
| `firmsdb/` | Код `export_dump.py`, файли SQL схеми `firms` і `restore.sh` |
| `tests/` | Тести: `python3 -m unittest discover tests`. Тести SQL потребують Docker |
| `testdata/test-ukraine/` | Готовий тестовий пакет України |
| `docs/deploy.md` | Інструкція розгортання |
| `docs/data-standard.md` | Колонки файлів FIRMS, їхні одиниці й документи NASA, що їх описують (англійською) |

Тека `data/` з сирими файлами, множниками й пакетами в git не входить.
