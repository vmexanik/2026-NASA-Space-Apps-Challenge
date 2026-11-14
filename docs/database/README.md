# База FIRMS для бекенду й фронтенду

Ця записка для того, хто пише частину застосунку на Laravel і Vue. У ній сказано:

- звідки береться база з даними FIRMS;
- які функції бази викликати;
- що змінюється в контракті `HotspotRepository`;
- що потрібно від календаря, карти й адмінки.

Як рахуються множники гармонізації, описано в [docs/harmonization/README.md](../harmonization/README.md).

## 1. Звідки береться база

Дані FIRMS лежать у схемі `firms` тієї самої бази PostgreSQL `we_charge`. Міграції Laravel цю схему не створюють і не чіпають. Тому `php artisan migrate:fresh` її не зітре: він чистить лише схему `public` (`web/config/database.php`, `search_path`).

Схему й дані створює скрипт `restore.sh` з пакета дампу. Пакет готують скрипти даних: вони завантажують FIRMS, рахують множники й пишуть пакет. Пакет — це тека з файлами SQL, стиснутими даними, `manifest.json` і `restore.sh`.

Файли SQL схеми й `restore.sh` лежать у [parser/firmsdb/](../../parser/firmsdb/README.md). Порожню схему без даних можна створити вже зараз: як саме, сказано там.

Як розгорнути пакет на машині з застосунком:

1. Підняти застосунок, застосувати міграції й запустити сідер:

   ```bash
   docker compose up -d --build
   docker compose exec php php artisan migrate --seed
   ```

2. Скопіювати пакет у контейнер бази й запустити `restore.sh` там. У контейнері вже є `bash`, `psql`, `gzip` і PostGIS:

   ```bash
   docker compose exec db rm -rf /tmp/firms-dump
   docker cp <тека пакета>/. wc_db:/tmp/firms-dump
   docker compose exec db bash -c 'cd /tmp/firms-dump && PGUSER=we_charge PGDATABASE=we_charge ./restore.sh --jobs 4'
   ```

   Перша команда прибирає пакет, скопійований раніше. Без неї файли старого й нового пакетів змішалися б в одній теці. Шлях `<тека пакета>/.` копіює вміст теки, а не саму теку.

   Радимо саме спосіб з контейнером. Запустити скрипт можна й ззовні: `PGHOST=127.0.0.1 PGPORT=5432 PGUSER=we_charge PGPASSWORD=secret PGDATABASE=we_charge ./restore.sh`. Тоді на машині потрібні bash, `psql` і `gzip`. Скрипт перевіряють лише в Linux, тож на macOS він може не спрацювати.

3. Дочекатися рядка `OK`. Він означає, що кількість рядків у базі збіглася з маніфестом пакета.

Міграції й сідер мають відпрацювати до `restore.sh`. Тоді `restore.sh` запише в журнал адмінки (`ingest_runs`) рядок на кожне джерело даних. Сідер теж потрібен: він створює джерела в `data_sources`, на які посилаються рядки журналу (`data_source_id`).

Тестовий пакет лежить у [parser/testdata/test-ukraine/](../../parser/testdata/test-ukraine/) і містить лише Україну з 2000-11-01 до 2026-11-14: 2 357 190 пожеж і 349 023 точки нерухомих джерел тепла, як-от заводів. Пакет займає 62 МБ і несе дві версії методу: `v1-2026-11-14` і `v0-raw`. Розгортання займає ≈20 секунд, після нього база займає ≈0.9 ГБ. Щоб розгорнути його, у командах вище замість `<тека пакета>` треба підставити `parser/testdata/test-ukraine`.

**База з раннього пакета.** Пакети, зібрані до коміту d98691b, як-от тестовий пакет з коміту 5f5054d, мають іншу `01_tables.sql`: у новій є таблиця `firms.square_month_series`. Тому `restore.sh` нового пакета в базу з такого пакета зупиняється на кроці `2. schema` з кодом 1. Він пише `restore.sh: schema/01_tables.sql differs from the file the tables of this database were made with` і далі, як це виправити. Дані бази при цьому лишаються як були.

Простіше за все видалити схему `firms` і розгорнути новий пакет повністю, як у кроці 2, без `--only-year`:

```bash
docker compose exec db psql -U we_charge -d we_charge -c 'DROP SCHEMA firms CASCADE'
```

`DROP SCHEMA firms CASCADE` видаляє всі таблиці, функції й дані схеми `firms`. PostGIS, схема `public` і журнал `ingest_runs` лишаються. Якби поза схемою `firms` були об'єкти, що від неї залежать, CASCADE видалив би й їх. У застосунку таких нема, і їх не має бути: `restore.sh` зупиняється, коли щось поза схемою залежить від її функцій чи представлень (`parser/firmsdb/sql/02_functions.sql`).

Інші країни або весь світ розробник збирає сам: завантажує дані FIRMS з сайту NASA й запускає скрипти даних. Скрипти лежать у теці [parser/](../../parser/README.md), а кожен крок описує інструкція [parser/docs/deploy.md](../../parser/docs/deploy.md).

У пакеті кількох країн є дві особливості. Точки 2026 року з API FIRMS не мають країни, тому в пакет потрапляють усі точки в клітинках 0.25°, де є архівні точки цих країн. Отже, у клітинках на кордоні є й точки сусідів: у 2026 році це ≈7% понад точки самої країни. Сума по полігону країни від цього не змінюється, бо межові клітинки рахуються поточково, а карта на дрібному масштабі цю сходинку покаже. Крім того, `firms.day_source` такого пакета не має днів на краях року, коли в країні не було жодної точки. `firms.coverage()` від цього не змінюється.

## 2. Як перемкнути застосунок на базу

> **Зроблено (2026-11-15).** Застосунок читає лише базу: синтетичних даних і `WE_CHARGE_DATA_DRIVER` більше нема, `FakeHotspotRepository` лишився тільки в тестах (`web/tests/Support`). Метод гармонізації один: «Метод приведення за площею та місяцем». Його ключ у базі `v1-2026-11-14` записано в `web/config/we_charge.php` (`harmonization.version`), налаштування версії в адмінці нема. Поки в базі нема даних, API відповідає 503, а сайт пише, що даних ще нема.

- `App\Repositories\PostgisHotspotRepository implements HotspotRepository`, його реєструє `AppServiceProvider`.
- Усі функції бази, крім `dataset_info()`, приймають версію методу. Репозиторій бере її з `config('we_charge.harmonization.version')`.
- Якщо `firms.method_info(version)` або `firms.coverage(version)` не дають даних, репозиторій кидає `App\Exceptions\DataUnavailable` (відповідь 503 з назвою версії).

Тестовий пакет має дві версії методу:

- `v1-2026-11-14` — гармонізовані числа з `count_error`, неповними місяцями й `own_share`;
- `v0-raw` — числа без гармонізації, з вагою 1 у кожної точки, лише для порівняння.

Журі `v0-raw` показувати не можна: у ній видно стрибок 2012 року, коли ряд переходить з Aqua на Suomi NPP. Якщо `v1-2026-11-14` зміниться після остаточної перевірки, може прийти перезібраний пакет.

## 3. Що змінюється в контракті `HotspotRepository`

**`monthlyCounts()`.** Кожен рядок отримує два нові ключі:

- `count_error` (int або null) — типова похибка гармонізованого числа, тобто медіана відхилення в перевірці методу. Свою частку похибки додає кожен супутник місяця, крім Suomi NPP: ряд іде в його одиницях. Тому місяць лише з точками Suomi NPP має `count_error` 0. Для версії `v0-raw` — null, бо гармонізації там нема.
- `incomplete` (bool) — у місяці є дні, коли жоден супутник не дав даних, наприклад у роки Terra 2001–2002. Це інше, ніж `partial`, який каже, що місяць ще не закінчився.

Решта ключів не змінюється. `count` — гармонізоване число, `count_raw` — кількість точок, `source` — `modis` або `viirs`.

**Календар і зведення.** Обидва нові ключі треба показати людині. `FireAnalytics::calendar` уже передає їх у JSON без змін, бо лише додає свої ключі до рядка. Решту треба дописати:

- Календар мусить показувати похибку біля числа, наприклад «26 ± 5». Якщо в клітинці мало місця, похибку можна показати лише в рядку під календарем, де вже стоїть кількість пожеж місяця (`web/resources/js/components/CalendarHeatmap.vue`).
- Календар мусить позначати неповні місяці (`incomplete`), наприклад штриховкою. Штриховка `url(#hatch)` у `CalendarHeatmap.vue` уже позначає `partial`, тож для `incomplete` потрібна інша, наприклад у другий бік.
- `FireAnalytics::summary` складає в річні суми й у `totals.hotspots` лише `count`. Він мусить переносити туди й похибку. Найпростіше — сума `count_error` місяців: вона дає просту оцінку похибки року зверху. Для `v0-raw` похибка року теж має бути null. Звичайний `array_sum` дав би тут 0.

**`hotspots()`.** Ті самі 10 ключів, плюс `brightness`, `brightness_2`, `scan`, `track`, `firms_version` і `weight`.

- `acq_time` завжди з 4 цифр, наприклад `0028`.
- `firms_version` — версії продукту FIRMS у файлі, з якого взято точку, наприклад `6.03` або `2.0NRT`. Якщо у файлі трапилося кілька версій, тут буде їх список через кому. Це не версія методу гармонізації.
- Функція віддає тільки точки, які рахує календар (вага більше нуля).
- `X-Export-Expected-Rows`, який `ExportController` рахує з `count_raw`, збігається з кількістю рядків CSV лише для цілих місяців. `monthly_counts` бере місяці цілими, а `hotspots_in` — точно дні запиту. Інтерфейс дає вибрати будь-який день (`web/resources/js/App.vue`, `type="date"`), тож заголовок буває більшим за кількість рядків. `X-Export-Truncated` рахується з того самого числа, тож для неповних місяців він може повідомити про обрізку, якої не було.
- CSV пише лише 10 колонок контракту (`ExportController::COLUMNS`). Пропозиція: додати шість нових. Вони потрібні науковцям.

**`coverage()`** бере дати з `firms.coverage(version)`.

**`isDemo()`** повертає false.

**Кеш.** `FireAnalytics` бере повний ряд зони на кожен запит календаря і зведення, хоч би які дати вибрав користувач. Тому результат `monthlyCounts` варто тримати в кеші. Ключ — `Aoi::fingerprint()`, версія методу й дати запиту.

Після кожного `restore.sh` кеш треба чистити: `docker compose exec php php artisan cache:clear`. Кінець `coverage` у ключі цього не замінює: пакет, перезібраний з тією самою назвою версії, і `restore.sh --only-year` можуть змінити числа, не зсунувши його. Замість очищення можна додати в ключ `firms.dataset_info()->>'built_at'`: `restore.sh` переписує його з маніфесту пакета.

Щоб писати фронтенд до появи бази, варто додати `count_error` і `incomplete` у `FakeHotspotRepository`.

## 4. Функції бази

Усі функції лежать у схемі `firms`. Зону (AOI) приймають лише `monthly_counts` і `hotspots_in`, як текст GeoJSON Polygon: `json_encode($aoi->toGeoJson())`.

`DB::select` віддає рядки як об'єкти `stdClass`, а контракт і `FireAnalytics` чекають масиви. Тому кожен рядок треба перетворити: `(array) $row`. PDO віддає jsonb рядком JSON, тож його треба розібрати через `json_decode(..., true)`.

### `firms.monthly_counts(aoi text, d_from date, d_to date, version text)`

Повертає `(year int, month int, count bigint, count_raw bigint, source text, partial boolean, count_error bigint, incomplete boolean)`.

- Місяці беруться цілими. Кожен місяць діапазону є у відповіді, навіть якщо пожеж нема.
- Діапазон обрізається до дат, для яких є дані (`firms.coverage`).

```php
$rows = DB::select(
    'select * from firms.monthly_counts(?, ?::date, ?::date, ?)',
    [json_encode($aoi->toGeoJson()), $from->toDateString(), $to->toDateString(), $version],
);

return array_map(fn ($r) => (array) $r, $rows);
```

### `firms.hotspots_in(aoi text, d_from date, d_to date, version text, max_rows int)`

Повертає `(latitude float8, longitude float8, acq_date text, acq_time text, satellite text, instrument text, confidence text, frp real, daynight text, source text, brightness real, brightness_2 real, scan real, track real, firms_version text, weight float8)`.

- Рядки йдуть місяць за місяцем, а всередині місяця — за датою й часом.
- Функція віддає не більше `max_rows` рядків. Сюди передається `csv_export_max_rows`.
- `satellite` має значення FIRMS: `Terra`, `Aqua`, `N`, `N20`, `N21`.
- `confidence` — відсоток для MODIS (`59`) і літера для VIIRS (`l`, `n`, `h`).

Рядків може бути 100 000, тож їх варто читати курсором, пачками. Приклад:

```php
DB::beginTransaction();
try {
    DB::statement(
        'declare hs no scroll cursor for select * from firms.hotspots_in(?, ?::date, ?::date, ?, ?)',
        [json_encode($aoi->toGeoJson()), $from->toDateString(), $to->toDateString(), $version, $max],
    );
    while ($rows = DB::select('fetch 5000 from hs')) {
        foreach ($rows as $row) {
            yield (array) $row;
        }
    }
} finally {
    DB::rollBack();
}
```

### `firms.coverage(version text)`

Повертає `(d_from date, d_to date)` — перший і останній день, для яких є дані. Для версії без даних функція повертає один рядок з NULL. `CarbonImmutable::parse(null)` дав би тоді поточний час, тож приклад кидає помилку.

```php
$row = DB::selectOne('select d_from, d_to from firms.coverage(?)', [$version]);
if ($row->d_from === null) {
    throw new RuntimeException("Harmonization method version '{$version}' has no data in the firms schema");
}

return ['from' => CarbonImmutable::parse($row->d_from), 'to' => CarbonImmutable::parse($row->d_to)];
```

### `firms.method_info(version text)`

Повертає jsonb з ключами `version`, `label`, `params` і `created_at`. Якщо такої версії нема, функція повертає NULL. У `params` записано, як побудована версія. Наприклад, `confidence_filter: null` означає «без фільтра впевненості».

```php
$json = DB::scalar('select firms.method_info(?)', [$version]);
if ($json === null) {
    throw new RuntimeException("Harmonization method version '{$version}' is not in the firms schema");
}
$method = json_decode($json, true);
```

### `firms.dataset_info()`

Повертає jsonb з ключами `name`, `scope` (`world` або `countries`), `countries` і `built_at`. З нього видно, які країни є в базі.

```php
$dataset = json_decode(DB::scalar('select firms.dataset_info()'), true);
```

### `firms.map_features(west float8, south float8, east float8, north float8, zoom int, d_from date, d_to date, version text, max_points int)`

Повертає `(kind text, lon float8, lat float8, cell_west float8, cell_south float8, cell_east float8, cell_north float8, satellite text, acq_date date, frp real, weight float8, n_raw bigint, n_harm float8, own_share real)`.

Межі клітинки у відповіді звуться `cell_west`…`cell_north`, бо PL/pgSQL не дає назвати вихід так само, як вхід.

- **Масштаб 9 і більший:** `kind = point`. Заповнені `lon`, `lat`, `satellite`, `acq_date`, `frp`, `weight` і `own_share`. Точок не більше `max_points`. Вони йдуть від найновіших (`acq_date DESC, acq_time DESC`), тож коли точок більше за `max_points`, відповідь лишає найсвіжіші пожежі.
- **Масштаб менший за 9:** `kind = cell`. Заповнені межі клітинки (`cell_west`, `cell_south`, `cell_east`, `cell_north`), `n_raw` і `n_harm`. Розмір клітинки залежить від масштабу: 0.25° на масштабах 7–8, 0.5° на 6, 1° на 5 і 2° на масштабах 4 і менших. Дати тут беруться цілими місяцями.
- `satellite` має значення FIRMS, як у `hotspots_in`.
- `own_share` каже, на скільки множник квадрата спирається на його власні дані. Він береться з `firms.method_factor`, а де рядка множника нема, дорівнює NULL: у точок VIIRS і в усіх точок версії `v0-raw`.
- Якщо не виконано `-180 <= west < east <= 180` і `-90 <= south < north <= 90`, функція кидає помилку. Так само на масштабі 9 і більшому, якщо bbox зачіпає понад 20 000 клітинок по 0.25° (розділ 5).

```php
$rows = DB::select(
    'select * from firms.map_features(?, ?, ?, ?, ?, ?::date, ?::date, ?, ?)',
    [$west, $south, $east, $north, $zoom, $from->toDateString(), $to->toDateString(), $version, $maxPoints],
);
```

## 5. Карта

**Запит.** Для карти потрібен новий маршрут `POST /api/map` з тілом `{"bbox": [west, south, east, north], "zoom": 7, "date_from": "2020-01-01", "date_to": "2020-12-31"}`. Відповідь — GeoJSON FeatureCollection з `firms.map_features`:

- точка — `Point` з властивостями `satellite`, `acq_date`, `frp`, `weight` і `own_share`;
- клітинка — `Polygon` (прямокутник з `cell_west`…`cell_north`) з властивостями `n_harm` (за ним колір) і `n_raw`.

**Скільки точок.** Ціль для `firms.map_features` — до ≈20 000 об'єктів на відповідь, тож `max_points` радимо ставити 20 000. Функція не каже, чи обрізала точки. Щоб це знати, можна передати `max_points + 1`: якщо точок прийшло більше за `max_points`, зайву треба відкинути й попросити користувача наблизити карту.

**Розмір bbox.** З масштабу 9 bbox може зачепити не більше 20 000 клітинок по 0.25°, тобто квадрат до 35° × 35°, а на більший функція кидає помилку. Вікно карти до цієї межі не доходить (екран 4K на масштабі 9 зачіпає ≈1 000 клітинок), тож бекенд має перевірити bbox разом із масштабом ще до виклику й відхилити такий запит як помилку клієнта.

**Ліміт запитів.** Новий маршрут варто покласти в групу `throttle:public-api` у `web/routes/api.php`, як решту API. Ця група пускає з однієї IP-адреси `api_rate_limit_per_minute` запитів за хвилину (типово 60) на всі свої маршрути разом. Тому карта має слати запит лише через ≈300 мс після останньої події (debounce).

**Шар Leaflet.** Шар малюється на canvas (`L.canvas()`) і оновлюється після події `moveend` і після зміни дат. Окремо слухати `zoomend` не треба: Leaflet шле `moveend` і після кожної зміни масштабу, тож другий слухач подвоїв би запити. Межі беруться з `map.getBounds()`. Коли на екрані видно лінію зміни дат, довгота меж виходить за ±180, тож перед запитом її треба обрізати до [−180, 180].

**Колір точок.** Точки старих датчиків MODIS (`satellite` — `Terra` або `Aqua`) мають інший колір, ніж точки VIIRS. Так видно, що їх перераховано множником. Колір вибирається за `satellite`, а не за вагою: у `v0-raw` вага всіх точок дорівнює 1. У підказці точки треба показати її справжню вагу, а коли `own_share` не null — і його.

## 6. Адмінка і `/api/meta`

- **Фільтр якості.** Схвалений метод гармонізації не фільтрує точки за впевненістю. Типові значення в `web/config/we_charge.php` треба змінити: `modis_min_confidence` на 0, `viirs_confidence_levels` на `[l, n, h]`. Якщо сторінку Settings уже зберігали, ці поля треба змінити й в адмінці: вона пише в базу всі поля разом, і типові значення з конфігу після цього не діють.
- **Що означають ці поля.** Це вхід для наступної версії методу: множники вчаться на вже відфільтрованих точках. Зміна в адмінці не змінює чисел, доки не ввімкнуть нову версію. Тому `/api/meta` має показувати параметри активної версії з `firms.method_info(version)`, а не значення з налаштувань.
- **Текст про метод.** `method.p3` у `web/resources/js/i18n.js` каже «Quality filter: MODIS confidence ≥ {modis}; VIIRS confidence {viirs}», і так само українською. Якщо `params.confidence_filter` — null, текст має казати «без фільтра».
- **`grid_step`.** Це поле не впливає на числа: база рахує точно для будь-якої зони. Його можна прибрати або лишити як опис.
- **NOAA-20.** Джерела `VIIRS_NOAA20_SP` і `VIIRS_NOAA20_NRT` треба ввімкнути в `web/database/seeders/DatabaseSeeder.php`. Сідер не змінює джерел, які вже є в базі (`firstOrCreate`), тож на розгорнутому застосунку їх треба ввімкнути й в адмінці: список джерел даних у групі Data collection, перемикач `enabled`. Після 2026-11-02 Suomi NPP не дає даних, і ряд тримається на NOAA-20.

## 7. Банер охоплення

Якщо `firms.dataset_info()->>'scope'` дорівнює `countries`, над картою треба показати, наприклад, «Дані лише для: Україна». Поза переліченими країнами функції повертають нулі.

Список береться з `countries`. Назви там англійські, як у файлах FIRMS: для тестового пакета це `["Ukraine"]`. Інтерфейс двомовний (`en` і `uk` у `web/resources/js/i18n.js`), тож назви треба перекладати.

`isDemo()` для цього не годиться: її банер каже, що числа синтетичні, а тут вони справжні.

## 8. Помилки й обмеження

- Функції кидають помилку на невідому версію методу (`there is no method version '<v>'`), на порожню зону або зону, що не є Polygon чи MultiPolygon, і на NULL або від'ємні `max_rows`, `zoom`, `max_points`. Тож неправильне налаштування в адмінці видно одразу, а не як календар нулів.
- Не створюйте в базі застосунку подань, функцій чи колонок, які спираються на функції або подання схеми `firms`. Якщо такі є, `restore.sh` зупиняється й називає їх, бо інакше нове розгортання стерло б їх.
- Рядок журналу `ingest_runs` зі статусом `failed` і текстом «the data is in and checked…» означає, що дані залито й перевірено, а журнал застосунку не прийняв лічильники.

## 9. Приклади відповідей

Узято з тестового пакета України, зона — квадрат 30–31° сх. д., 50–51° пн. ш. біля Києва.

`firms.monthly_counts` для серпня 2008 року (ряд MODIS) і серпня 2021 року (ряд VIIRS):

```
 year | month | count | count_raw | source | partial | count_error | incomplete
------+-------+-------+-----------+--------+---------+-------------+------------
 2008 |     8 |   407 |        58 | modis  | f       |          83 | f
 2021 |     8 |    26 |        26 | viirs  | f       |           0 | f
```

У 2008 році 58 точок MODIS стали 407 точками в одиницях Suomi NPP, похибка ±83. У 2021 році ряд уже з VIIRS, тож `count` дорівнює `count_raw`.

`firms.hotspots_in` (один рядок, частина колонок):

```
 latitude | longitude |  acq_date  | acq_time | satellite | confidence | frp  | daynight | source | weight
----------+-----------+------------+----------+-----------+------------+------+----------+--------+-------
  50.6682 |   30.9406 | 2008-08-04 | 1028     | Aqua      | 84         | 36.6 | D        | modis  | 7.010
```

`firms.map_features` на масштабі 7 (клітинка) і 10 (точка):

```
 kind  | cell_west | cell_south | cell_east | cell_north | n_raw | n_harm
-------+-----------+------------+-----------+------------+-------+-------
 cell  |     31.00 |      50.50 |     31.25 |      50.75 |    20 |  140.2

 kind  |   lon   |   lat   | satellite |  acq_date  | frp  | weight | own_share
-------+---------+---------+-----------+------------+------+--------+----------
 point | 30.9406 | 50.6682 | Aqua      | 2008-08-04 | 36.6 |  7.010 |     0.639
```

`own_share` 0.639 означає, що множник цього квадрата на 64% спирається на його власні точки.

## 10. Що буде далі

- Перезібраний тестовий пакет, якщо `v1-2026-11-14` зміниться після остаточної перевірки (розділ 2).
- Заміри швидкості на великій зоні й розмір бази для всього світу — в `parser/docs/deploy.md`.
