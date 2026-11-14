-- Tables of the firms schema (web database design, 6.2-6.5; factors design, 6.4).
--
-- The column order of every table that a dump package carries is the column order of its TSV files (the shared
-- package format), so restore.sh copies the files with a plain \copy. Running the file again keeps every table and
-- its rows. The parts of firms.hotspot and firms.hotspot_static are made by restore.sh from the manifest.

-- Satellites: 1 terra, 2 aqua (MODIS), 3 snpp, 4 noaa20, 5 noaa21 (VIIRS).
CREATE TABLE IF NOT EXISTS firms.satellite (
    id          smallint PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    firms_value text NOT NULL,              -- the satellite column of FIRMS files: Terra, Aqua, N, N20, N21
    instrument  text NOT NULL,              -- MODIS or VIIRS
    label       text NOT NULL
);

-- One row per raw file the exporter read: a yearly archive zip or a CSV of the FIRMS API.
CREATE TABLE IF NOT EXISTS firms.load_batch (
    id           integer PRIMARY KEY,
    source_code  text NOT NULL,             -- MODIS_SP, VIIRS_SNPP_NRT, ...
    is_nrt       boolean NOT NULL,
    file         text NOT NULL,             -- path from the root of the raw data
    member_count integer,                   -- country files read from a zip
    file_size    bigint,
    file_mtime   timestamptz,
    versions     text[],                    -- values of the FIRMS version column met in the file
    date_from    date,
    date_to      date,
    rows_fire    integer,
    rows_static  integer
);

-- The file that holds each day of each satellite: SP before NRT, and the newer file among files of one kind.
CREATE TABLE IF NOT EXISTS firms.day_source (
    satellite smallint NOT NULL,
    day       date NOT NULL,
    is_nrt    boolean NOT NULL,
    batch_id  integer NOT NULL,
    PRIMARY KEY (satellite, day)
);

-- 0.25-degree cells with an archive point of any type: the footprint of the country files.
CREATE TABLE IF NOT EXISTS firms.archive_cell (
    cell_id integer PRIMARY KEY
);

-- One fire per row. Parts: hotspot_<year> by acq_date, split by satellite into hotspot_<year>_<code>.
CREATE TABLE IF NOT EXISTS firms.hotspot (
    acq_date     date NOT NULL,             -- UTC
    acq_time     smallint NOT NULL,         -- HHMM, UTC
    satellite    smallint NOT NULL,         -- firms.satellite
    cell_id      integer NOT NULL,          -- firms.cell_id_e5(lat_e5, lon_e5)
    lat_e5       integer NOT NULL,          -- degrees x 100 000
    lon_e5       integer NOT NULL,
    frp          real,                      -- MW
    brightness   real,                      -- K: brightness (MODIS) or bright_ti4 (VIIRS)
    brightness_2 real,                      -- K: bright_t31 (MODIS) or bright_ti5 (VIIRS)
    scan         real,                      -- km
    track        real,                      -- km
    conf_class   "char" NOT NULL,           -- l, n or h
    conf_pct     smallint,                  -- MODIS confidence 0-100, NULL for VIIRS
    is_day       boolean NOT NULL,
    is_nrt       boolean NOT NULL,
    batch_id     integer NOT NULL           -- firms.load_batch
) PARTITION BY RANGE (acq_date);

-- Points that are not fires, set aside rather than deleted. Parts: hotspot_static_<year>.
CREATE TABLE IF NOT EXISTS firms.hotspot_static (
    acq_date     date NOT NULL,
    acq_time     smallint NOT NULL,
    satellite    smallint NOT NULL,
    cell_id      integer NOT NULL,
    lat_e5       integer NOT NULL,
    lon_e5       integer NOT NULL,
    frp          real,
    brightness   real,
    brightness_2 real,
    scan         real,
    track        real,
    conf_class   "char" NOT NULL,
    conf_pct     smallint,
    is_day       boolean NOT NULL,
    is_nrt       boolean NOT NULL,
    batch_id     integer NOT NULL,
    type         smallint NOT NULL          -- 1 volcano, 2 other static land source, 3 offshore, 9 static source map
) PARTITION BY RANGE (acq_date);

-- The map of static sources that the harmonization step will build; empty until then.
CREATE TABLE IF NOT EXISTS firms.static_cell (
    instrument text NOT NULL,
    step       real NOT NULL,
    cell       bigint NOT NULL,
    PRIMARY KEY (instrument, step, cell)
);

-- Versions of the harmonization method. params holds confidence_filter: null means no filter, otherwise
-- {"modis_min_confidence": <0-100>, "viirs_confidence_levels": ["n", "h"]}, either key optional.
CREATE TABLE IF NOT EXISTS firms.method (
    version    text PRIMARY KEY,
    label      text,
    params     jsonb,
    created_at timestamptz
);

-- Weights of fires: which satellite makes the series on which days, and its factor per 2-degree square and
-- calendar month. is_day NULL means day and night. A fire without a row is not in the series.
CREATE TABLE IF NOT EXISTS firms.method_weight (
    version        text NOT NULL,
    satellite      smallint NOT NULL,
    date_from      date NOT NULL,
    date_to        date,                    -- NULL: no end
    cell2_id       integer NOT NULL,
    calendar_month smallint NOT NULL,
    is_day         boolean,
    weight         double precision NOT NULL,
    -- Two rows for one fire would count it twice.
    CONSTRAINT method_weight_key UNIQUE NULLS NOT DISTINCT
        (version, satellite, cell2_id, calendar_month, date_from, is_day)
);

-- How each MODIS factor was made (factors design, 6.4).
CREATE TABLE IF NOT EXISTS firms.method_factor (
    version        text NOT NULL,
    satellite      smallint NOT NULL,
    cell2_id       integer NOT NULL,
    calendar_month smallint NOT NULL,
    factor         double precision,
    own_modis      integer,
    own_viirs      integer,
    own_share      real,
    cross_factor   double precision,
    cross_modis    integer,
    square8_factor double precision,
    world_factor   double precision,
    PRIMARY KEY (version, satellite, cell2_id, calendar_month)
);

-- Typical relative error of a harmonized count: the row with the largest n_min not above the count of fires.
CREATE TABLE IF NOT EXISTS firms.method_error (
    version   text NOT NULL,
    source    text NOT NULL,                -- modis or viirs
    satellite smallint,
    n_min     integer NOT NULL,
    rel_error real NOT NULL,
    CONSTRAINT method_error_key UNIQUE NULLS NOT DISTINCT (version, source, satellite, n_min)
);

-- Days when the series has no satellite: their months are incomplete.
CREATE TABLE IF NOT EXISTS firms.method_gap (
    version text NOT NULL,
    day     date NOT NULL,
    PRIMARY KEY (version, day)
);

-- The 1 036 800 cells of 0.25 degrees; restore.sh fills it with firms.cell_geom.
CREATE TABLE IF NOT EXISTS firms.grid_cell (
    cell_id integer PRIMARY KEY,
    geom    geometry(Polygon, 4326) NOT NULL
);

-- Sums of the series per 0.25-degree cell, month and satellite, built by firms.build_series.
CREATE TABLE IF NOT EXISTS firms.cell_month_series (
    version   text NOT NULL,
    cell_id   integer NOT NULL,
    month     date NOT NULL,                -- the first day of the month
    satellite smallint NOT NULL,
    n_raw     integer NOT NULL,             -- fires with a weight above 0
    n_harm    double precision NOT NULL,    -- the sum of their weights
    PRIMARY KEY (version, cell_id, month, satellite)
);

-- The source of the series in each month: viirs when a VIIRS satellite has a weight above 0 in it, else modis.
CREATE TABLE IF NOT EXISTS firms.method_month (
    version text NOT NULL,
    month   date NOT NULL,
    source  text NOT NULL,
    PRIMARY KEY (version, month)
);

-- The package the database was restored from: what it covers.
CREATE TABLE IF NOT EXISTS firms.dataset (
    name      text PRIMARY KEY,
    scope     text NOT NULL,                -- world or countries
    countries text[],                       -- NULL for the world
    built_at  timestamptz,
    manifest  jsonb
);

-- The schema files restore.sh ran.
CREATE TABLE IF NOT EXISTS firms.schema_migrations (
    file       text PRIMARY KEY,
    sha256     text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
