# We Charge — NASA Space Apps: Burning Activity Calendar

Веб-застосунок, що гармонізує дані супутникових hotspot-ів (MODIS / VIIRS) у календар активності горіння.

## Структура

```
we_charge/
├── docker-compose.yml
├── docker/
│   ├── php/     # php:8.4-fpm + pdo_pgsql, composer
│   ├── nginx/   # конфіг віртуального хоста (localhost / we-charge.test)
│   └── db/      # postgres:17 + PostGIS (arm64-сумісний)
├── web/         # Laravel 13 (API + SPA)
├── parser/      # схема бази FIRMS (firmsdb/) і тестовий пакет даних (testdata/)
└── setup.sh     # розгортання однією командою
```

## Документація

- [docs/harmonization/README.md](docs/harmonization/README.md) — як гармонізація зводить MODIS і VIIRS в один ряд, з доказами на даних NASA.
- [docs/database/README.md](docs/database/README.md) — схема бази FIRMS і функції, які читає бекенд.

## Контейнери

| Сервіс | Контейнер  | Порт на хості | Призначення                 |
|--------|------------|---------------|-----------------------------|
| nginx  | wc_nginx   | 80            | веб-сервер                  |
| php    | wc_php     | —             | PHP-FPM 8.4 (Laravel)       |
| db     | wc_db      | 5432          | PostgreSQL 17 + PostGIS     |
| node   | wc_node    | 5173          | Vite dev server (профіль `dev`) |

## Запуск однією командою

Потрібен лише Docker (Docker Desktop на macOS/Windows). PHP, Composer і Node на машині не потрібні.

```bash
./setup.sh
```

Скрипт:
1. піднімає контейнери;
2. створює `web/.env`, ставить пакети, генерує `APP_KEY`;
3. робить міграції та сідер (адмін, продукти FIRMS, швидкі області);
4. збирає фронтенд;
5. розгортає тестовий пакет даних FIRMS по Україні (`parser/testdata/test-ukraine`, ≈1 хв);
6. чистить кеші.

Повторний запуск безпечний: що вже зроблено, пропускається. Дані перезаливаються, лише якщо в базі інший пакет або пакет з іншою схемою. Наприклад, після `git pull`, що оновив `schema/*.sql` пакета: тоді скрипт сам видаляє схему `firms` (лише її, таблиці застосунку в `public` лишаються) і розгортає пакет наново.

Після `Done.` відкрий http://localhost (адмінка: http://localhost/admin, `admin@we-charge.test` / `admin`).

Інший пакет даних (наприклад, на весь світ) або лише застосунок без даних:

```bash
./setup.sh path/to/package
```

```bash
./setup.sh --no-data
```

Якщо в терміналі `docker: command not found` на macOS, додай у `~/.zshrc`:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

Порти 80 і 5432 мають бути вільні (див. «Якщо не працює» нижче).

## Що де

| URL | Що це |
|---|---|
| http://we-charge.test | Публічна SPA (Vue 3 + Leaflet): вибір AOI, календар, аналітика, експорт |
| http://we-charge.test/admin | Адмінка (Filament 5): FIRMS MAP_KEY, продукти, регіони, журнал завантажень, адміни |
| `/api/meta`, `/api/calendar`, `/api/summary`, `/api/map`, `/api/export/csv` | Публічне API (контракт: `web/app/Contracts/HotspotRepository.php`, `web/app/Http/Requests/AoiQueryRequest.php`) |

**Вхід в адмінку локально:** `admin@we-charge.test` / `admin` (з `ADMIN_EMAIL` / `ADMIN_PASSWORD` у `.env`). Змініть пароль у профілі після першого входу.

**Дані** застосунок читає зі схеми `firms` у PostgreSQL через її функції (`web/app/Repositories/PostgisHotspotRepository.php`, опис у [docs/database/README.md](docs/database/README.md)). Схему і дані створює `restore.sh` з пакета дампу, а не міграції Laravel. Поки даних нема, API відповідає 503, а сайт пише, що даних ще нема.

**Швидкі області** (кнопки над картою) зберігає адмін: увійди в `/admin`, намалюй область на публічній карті й натисни «Save as quick area». Перейменувати (зокрема українською), впорядкувати чи сховати їх можна в адмінці, розділ Quick areas.

**MAP_KEY** зберігається в таблиці `settings` зашифрованим (`APP_KEY`). Якщо там порожньо, береться `FIRMS_MAP_KEY` з `.env`. Скрипти даних у `parser/` цього налаштування не читають: ключ вони беруть зі змінної середовища `FIRMS_MAP_KEY`, а якщо її нема, то з `parser/.env` (`parser/firms/config.py`). Докладніше — у розділі MAP_KEY [parser/docs/deploy.md](parser/docs/deploy.md#map_key).

**Підкладки карти** (без ключів): OpenStreetMap (за замовчуванням), Esri Light Gray і Esri World Imagery. CARTO basemaps тепер вимагають API-ключ, тому їх не використовуємо.

Тести:

```bash
docker compose exec php php artisan test
```

## Домен we-charge.test (необов'язково)

Застосунок працює на http://localhost. Якщо хочеш домен, macOS не знає про `we-charge.test`, тому треба вручну сказати, що цей домен = твій комп'ютер.

1. Відкрий файл hosts (попросить пароль від мака):

   ```bash
   sudo nano /etc/hosts
   ```

2. В кінці файлу додай рядок:

   ```
   127.0.0.1   we-charge.test
   ```

3. Збережи: `Ctrl+O` → `Enter` → вийди: `Ctrl+X`.

4. Скинь DNS-кеш (без цього мак може ще довго «не бачити» зміни):

   ```bash
   sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder
   ```

5. Перевір:

   ```bash
   ping -c 1 we-charge.test
   ```

   Має бути `PING we-charge.test (127.0.0.1)`.

Однією командою замість кроків 1–4:

```bash
echo "127.0.0.1   we-charge.test" | sudo tee -a /etc/hosts && sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
```

### Якщо не працює

- **Браузер відкриває пошук Google замість сайту** — набери адресу повністю: `http://we-charge.test` (з `http://`).
- **Chrome/Safari редіректить на https** — `.test` ми не підписуємо сертифікатом; відкрий у приватному вікні або очисть HSTS для домену в `chrome://net-internals/#hsts`.
- **Порт 80 зайнятий** (`bind: address already in use`) — подивись хто: `sudo lsof -i :80`. Часто це вбудований Apache: `sudo apachectl stop`.
- **Увімкнений VPN / корпоративний проксі** — додай `we-charge.test` у виключення проксі або вимкни VPN.
- Не використовуй домен `.local` — на маці він зарезервований під Bonjour і буде гальмувати по 5 секунд.

## Корисні команди

```bash
docker compose exec php php artisan tinker
```

```bash
docker compose exec db psql -U we_charge -d we_charge
```

```bash
docker compose logs -f nginx php
```

```bash
docker compose down
```

Фронтенд (Vite з hot reload):

```bash
docker compose --profile dev up -d node
```

Підключення до БД з DBeaver / TablePlus / PhpStorm: `127.0.0.1:5432`, база `we_charge`, юзер `we_charge`, пароль `secret`.
