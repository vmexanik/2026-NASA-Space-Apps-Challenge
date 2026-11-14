# We Charge — NASA Space Apps: Burning Activity Calendar

Веб-застосунок, що гармонізує дані супутникових hotspot-ів (MODIS / VIIRS) у календар активності горіння.

## Структура

```
we_charge/
├── docker-compose.yml
├── docker/
│   ├── php/     # php:8.4-fpm + pdo_pgsql, composer
│   ├── nginx/   # конфіг віртуального хоста we-charge.test
│   └── db/      # postgres:17 + PostGIS (arm64-сумісний)
├── web/         # Laravel 13 (API + SPA)
└── parser/      # (далі) Python-парсер FIRMS даних
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

## Перший запуск

1. Запусти Docker Desktop. Якщо в терміналі `docker: command not found`, додай у `~/.zshrc`:

   ```bash
   export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
   ```

2. Підніми контейнери:

   ```bash
   docker compose up -d --build
   ```

3. Якщо проєкт склонований з git (немає `web/vendor` і `web/.env`):

   ```bash
   cp web/.env.example web/.env
   ```

   ```bash
   docker compose exec php composer install
   ```

   ```bash
   docker compose exec php php artisan key:generate
   ```

4. Міграції та початкові дані (адмін, продукти FIRMS, регіон «Ukraine»):

   ```bash
   docker compose exec php php artisan migrate --seed
   ```

5. Зібрати фронтенд (`public/build` не в git):

   ```bash
   docker compose run --rm --no-deps node sh -c "npm install && npm run build"
   ```

6. Пропиши хост (див. нижче) і відкрий http://we-charge.test

## Що де

| URL | Що це |
|---|---|
| http://we-charge.test | Публічна SPA (Vue 3 + Leaflet): вибір AOI, календар, аналітика, експорт |
| http://we-charge.test/admin | Адмінка (Filament 5): FIRMS MAP_KEY, продукти, регіони, журнал завантажень, адміни |
| `/api/meta`, `/api/calendar`, `/api/summary`, `/api/export/csv` | Публічне API (контракт: `web/app/Contracts/HotspotRepository.php`, `web/app/Http/Requests/AoiQueryRequest.php`) |

**Вхід в адмінку локально:** `admin@we-charge.test` / `admin` (з `ADMIN_EMAIL` / `ADMIN_PASSWORD` у `.env`). Змініть пароль у профілі після першого входу.

**Дані поки синтетичні.** `WE_CHARGE_DATA_DRIVER=fake` віддає детерміновані демо-дані (`FakeHotspotRepository`), у UI показано банер «Demo data». Коли схема БД парсера буде готова, треба додати реалізацію `HotspotRepository` на PostGIS і перемкнути драйвер. Аналітика, API й фронтенд при цьому не змінюються.

**MAP_KEY** зберігається в таблиці `settings` зашифрованим (`APP_KEY`). Якщо там порожньо, береться `FIRMS_MAP_KEY` з `.env`. Як парсер читатиме налаштування, ще не вирішено.

**Підкладки карти** (без ключів): OpenStreetMap (за замовчуванням), Esri Light Gray і Esri World Imagery. CARTO basemaps тепер вимагають API-ключ, тому їх не використовуємо.

Тести:

```bash
docker compose exec php php artisan test
```

## Налаштування hosts на macOS

macOS не знає про `we-charge.test`, тому треба вручну сказати, що цей домен = твій комп'ютер.

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
