-- Functions and views of the firms schema: the application reads the data only through them (web database
-- design, 6.5-6.6; factors design, 6.5).
--
-- restore.sh runs this file in one transaction. It first drops the functions and views of the schema, so that a
-- package with a changed signature or result replaces them instead of failing on CREATE OR REPLACE. Functions in
-- plain SQL are bound to their tables when they are created. The PL/pgSQL ones name every table with its schema
-- and keep the search_path of the restore, which finds PostGIS whatever the caller's search_path is.

DO $$
DECLARE
    item text;
    outside text;
BEGIN
    -- CASCADE is only for what depends on these objects inside the schema. Objects elsewhere (a view of the
    -- application over firms.coverage, a function returning rows of firms.v_series_point, a column of that type)
    -- stop the restore, so that nothing outside firms is dropped. A view brings its row type and the array of it.
    WITH referenced (classid, objid) AS (
        SELECT 'pg_proc'::regclass, p.oid FROM pg_proc p WHERE p.pronamespace = 'firms'::regnamespace
        UNION ALL
        SELECT 'pg_class'::regclass, c.oid FROM pg_class c
        WHERE c.relnamespace = 'firms'::regnamespace AND c.relkind = 'v'
        UNION ALL
        SELECT 'pg_type'::regclass, c.reltype FROM pg_class c
        WHERE c.relnamespace = 'firms'::regnamespace AND c.relkind = 'v'
        UNION ALL
        SELECT 'pg_type'::regclass, t.typarray FROM pg_class c JOIN pg_type t ON t.oid = c.reltype
        WHERE c.relnamespace = 'firms'::regnamespace AND c.relkind = 'v' AND t.typarray <> 0
    )
    SELECT string_agg(DISTINCT pg_describe_object(d.classid, d.objid, d.objsubid), '; ')
      INTO outside
    FROM pg_depend d
    JOIN referenced r ON r.classid = d.refclassid AND r.objid = d.refobjid
    WHERE d.deptype = 'n'
      AND coalesce(CASE d.classid
                       WHEN 'pg_rewrite'::regclass THEN (SELECT c.relnamespace FROM pg_rewrite r
                                                         JOIN pg_class c ON c.oid = r.ev_class WHERE r.oid = d.objid)
                       WHEN 'pg_proc'::regclass THEN (SELECT p.pronamespace FROM pg_proc p WHERE p.oid = d.objid)
                       WHEN 'pg_class'::regclass THEN (SELECT c.relnamespace FROM pg_class c WHERE c.oid = d.objid)
                       WHEN 'pg_attrdef'::regclass THEN (SELECT c.relnamespace FROM pg_attrdef a
                                                         JOIN pg_class c ON c.oid = a.adrelid WHERE a.oid = d.objid)
                       WHEN 'pg_constraint'::regclass THEN (SELECT n.connamespace FROM pg_constraint n
                                                            WHERE n.oid = d.objid)
                       WHEN 'pg_trigger'::regclass THEN (SELECT c.relnamespace FROM pg_trigger t
                                                         JOIN pg_class c ON c.oid = t.tgrelid WHERE t.oid = d.objid)
                       WHEN 'pg_type'::regclass THEN (SELECT t.typnamespace FROM pg_type t WHERE t.oid = d.objid)
                   END, 0) <> 'firms'::regnamespace;
    IF outside IS NOT NULL THEN
        RAISE EXCEPTION 'objects outside the schema firms depend on its functions, views or their row types: %', outside
            USING HINT = 'The restore replaces every function and view of firms. Drop these objects, restore, '
                         'then create them again.';
    END IF;
    FOREACH item IN ARRAY coalesce((SELECT array_agg(c.oid::regclass::text) FROM pg_class c
                                    WHERE c.relnamespace = 'firms'::regnamespace AND c.relkind = 'v'), '{}')
    LOOP
        EXECUTE 'DROP VIEW IF EXISTS ' || item || ' CASCADE';
    END LOOP;
    FOREACH item IN ARRAY coalesce((SELECT array_agg(p.oid::regprocedure::text) FROM pg_proc p
                                    WHERE p.pronamespace = 'firms'::regnamespace), '{}')
    LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS ' || item || ' CASCADE';
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------------------------------------------
-- Grid (design, 6.2). Cells of 0.25 degrees, ix 0-1439 from lon -180, iy 0-719 from lat -90. Points on lon 180 or
-- lat 90 fall in the last column or row. Every function takes (lat, lon) in this order, like the FIRMS columns.

-- The cell of a point in degrees x 100 000.
CREATE FUNCTION firms.cell_id_e5(lat_e5 int, lon_e5 int) RETURNS int
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    RETURN least((lat_e5 + 9000000) / 25000, 719) * 1440 + least((lon_e5 + 18000000) / 25000, 1439);

-- The cell of a point in degrees. The degrees are rounded to whole 1e-5 first, as firms.grid.cell_id does in
-- Python, so a value read from the text of a FIRMS file lands in the cell of its exact coordinates.
CREATE FUNCTION firms.cell_id(lat float8, lon float8) RETURNS int
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    RETURN firms.cell_id_e5(round(lat * 100000)::int, round(lon * 100000)::int);

-- The 2-degree square of a cell: 8 x 8 cells, 180 squares in a row.
CREATE FUNCTION firms.cell2_id(cell_id int) RETURNS int
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    RETURN (cell_id / 1440 / 8) * 180 + (cell_id % 1440) / 8;

-- The square of a cell, in SRID 4326.
CREATE FUNCTION firms.cell_geom(cell_id int) RETURNS geometry
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    RETURN ST_MakeEnvelope((cell_id % 1440) * 0.25 - 180, (cell_id / 1440) * 0.25 - 90,
                           (cell_id % 1440) * 0.25 - 179.75, (cell_id / 1440) * 0.25 - 89.75, 4326);

-- The zone of a request: a GeoJSON Polygon or MultiPolygon in WGS 84, made valid, its areas only. Anything else,
-- NULL included, is an error rather than a zone without fires.
CREATE FUNCTION firms.aoi_geom(aoi text) RETURNS geometry
    LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE
    SET search_path FROM CURRENT
AS $$
DECLARE
    zone geometry;
BEGIN
    IF aoi IS NULL THEN
        RAISE EXCEPTION 'firms: the zone (aoi) is NULL';
    END IF;
    zone := ST_SetSRID(ST_GeomFromGeoJSON(aoi), 4326);
    IF GeometryType(zone) NOT IN ('POLYGON', 'MULTIPOLYGON') THEN
        RAISE EXCEPTION 'firms: the zone (aoi) must be a GeoJSON Polygon or MultiPolygon, not %', GeometryType(zone);
    END IF;
    RETURN ST_CollectionExtract(ST_MakeValid(zone), 3);
END
$$;

-- Stops a request for a method version the database does not have: its answer would be empty, not zero.
CREATE FUNCTION firms.check_version(version text) RETURNS void
    LANGUAGE plpgsql STABLE PARALLEL SAFE
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM firms.method m WHERE m.version = check_version.version) THEN
        RAISE EXCEPTION 'firms: there is no method version %', coalesce(quote_literal(check_version.version), 'NULL');
    END IF;
END
$$;

-- The cells under a zone. The zone covers the inner ones, so they take the ready sums; the fires of the others are
-- tested one by one.
CREATE FUNCTION firms.aoi_cells(zone geometry) RETURNS TABLE(cell_id int, is_inner boolean)
    LANGUAGE sql STABLE PARALLEL SAFE
BEGIN ATOMIC
    SELECT g.cell_id, ST_Covers(aoi_cells.zone, g.geom)
    FROM firms.grid_cell g
    WHERE ST_Intersects(aoi_cells.zone, g.geom);
END;

-- ---------------------------------------------------------------------------------------------------------------
-- The series (design, 6.5).

-- The one place of the rule of the series. A fire joins its weight row by satellite, 2-degree square, calendar
-- month, the days of the row and day or night; it is in the series when the weight is above 0 and the fire passes
-- the confidence filter of the version (params->'confidence_filter', null: no filter). The sums, the border cells
-- of a zone, the CSV and the map read the fires through this view, so their numbers agree.
CREATE VIEW firms.v_series_point AS
SELECT w.version, h.acq_date, h.acq_time, h.satellite, h.cell_id, h.lat_e5, h.lon_e5, h.frp, h.brightness,
       h.brightness_2, h.scan, h.track, h.conf_class, h.conf_pct, h.is_day, h.is_nrt, h.batch_id, w.weight
FROM firms.hotspot h
JOIN firms.method_weight w
  ON w.satellite = h.satellite
 AND w.cell2_id = firms.cell2_id(h.cell_id)
 AND w.calendar_month = extract(month FROM h.acq_date)::int
 AND h.acq_date >= w.date_from
 AND h.acq_date <= coalesce(w.date_to, 'infinity'::date)
 AND (w.is_day IS NULL OR w.is_day = h.is_day)
JOIN firms.method m ON m.version = w.version
WHERE w.weight > 0
  AND (jsonb_typeof(m.params -> 'confidence_filter') IS DISTINCT FROM 'object'
       -- MODIS fires carry a percent, VIIRS fires only a class.
       OR CASE WHEN h.conf_pct IS NOT NULL
               THEN h.conf_pct >= coalesce((m.params #>> '{confidence_filter,modis_min_confidence}')::int, 0)
               ELSE coalesce((m.params #> '{confidence_filter,viirs_confidence_levels}') ? h.conf_class::text, true)
          END);

-- The day ranges in which a version gives a satellite a weight above 0, one row per satellite and range; an open
-- end is 'infinity'. A skip scan over method_weight_segment_idx reads a few index entries per range instead of
-- the 780 000 rows of a version.
CREATE FUNCTION firms.series_segments(version text) RETURNS TABLE(satellite smallint, date_from date, date_to date)
    LANGUAGE sql STABLE PARALLEL SAFE
BEGIN ATOMIC
    WITH RECURSIVE seg(satellite, date_from, date_to) AS (
        (SELECT w.satellite, w.date_from, coalesce(w.date_to, 'infinity'::date)
         FROM firms.method_weight w
         WHERE w.version = series_segments.version AND w.weight > 0
         ORDER BY w.satellite, w.date_from, coalesce(w.date_to, 'infinity'::date)
         LIMIT 1)
        UNION ALL
        SELECT nxt.satellite, nxt.date_from, nxt.date_to
        FROM seg
        CROSS JOIN LATERAL (
            SELECT w.satellite, w.date_from, coalesce(w.date_to, 'infinity'::date) AS date_to
            FROM firms.method_weight w
            WHERE w.version = series_segments.version AND w.weight > 0
              AND (w.satellite, w.date_from, coalesce(w.date_to, 'infinity'::date))
                  > (seg.satellite, seg.date_from, seg.date_to)
            ORDER BY w.satellite, w.date_from, coalesce(w.date_to, 'infinity'::date)
            LIMIT 1) nxt
    )
    SELECT seg.satellite, seg.date_from, seg.date_to FROM seg;
END;

-- The first and last day with data of a version's series: the days of firms.day_source of a satellite inside the
-- ranges where the version gives it a weight above 0. NULLs when there are none.
CREATE FUNCTION firms.coverage(version text) RETURNS TABLE(d_from date, d_to date)
    LANGUAGE sql STABLE PARALLEL SAFE
BEGIN ATOMIC
    SELECT min((SELECT min(ds.day) FROM firms.day_source ds
                WHERE ds.satellite = sg.satellite AND ds.day >= sg.date_from AND ds.day <= sg.date_to)),
           max((SELECT max(ds.day) FROM firms.day_source ds
                WHERE ds.satellite = sg.satellite AND ds.day >= sg.date_from AND ds.day <= sg.date_to))
    FROM firms.series_segments(coverage.version) sg;
END;

-- Rebuilds firms.cell_month_series, firms.square_month_series and firms.method_month of a version for the months
-- from month_from to month_to (whole months; NULL: no bound). It checks the weight rows first: a fire in the days
-- of its satellite's rows needs a row for its 2-degree square and calendar month, else the build stops with the
-- list of the gaps instead of counting the fire as 0.
CREATE FUNCTION firms.build_series(version text, month_from date DEFAULT NULL, month_to date DEFAULT NULL)
    RETURNS void
    LANGUAGE plpgsql VOLATILE
    SET search_path FROM CURRENT
    SET work_mem = '256MB'
AS $$
DECLARE
    v_version text := build_series.version;
    lo date := coalesce(date_trunc('month', build_series.month_from::timestamp)::date, '-infinity'::date);
    hi date := coalesce((date_trunc('month', build_series.month_to::timestamp) + interval '1 month')::date,
                        'infinity'::date);
    seg record;
    overlap_rows text[];
    overlap_count bigint;
    gaps text[] := '{}';
    gap_count bigint := 0;
    found_gaps text[];
    found_count bigint;
    cov_from date;
    cov_to date;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM firms.method m WHERE m.version = v_version) THEN
        RAISE EXCEPTION 'firms.build_series: there is no method version %', v_version;
    END IF;

    -- Two rows with a weight above 0 for the same satellite, square and calendar month whose days and day-or-night
    -- meet would put a fire into the series twice.
    SELECT count(*), array_agg(format('%s square %s month %s: %s..%s%s and %s..%s%s', st.code, o.cell2_id,
                                      o.calendar_month, o.from1, coalesce(o.to1::text, ''),
                                      coalesce(' ' || CASE WHEN o.day1 THEN 'day' ELSE 'night' END, ''),
                                      o.from2, coalesce(o.to2::text, ''),
                                      coalesce(' ' || CASE WHEN o.day2 THEN 'day' ELSE 'night' END, ''))
                               ORDER BY o.satellite, o.cell2_id, o.calendar_month, o.from1)
      INTO overlap_count, overlap_rows
    FROM (SELECT w1.satellite, w1.cell2_id, w1.calendar_month, w1.date_from AS from1, w1.date_to AS to1,
                 w1.is_day AS day1, w2.date_from AS from2, w2.date_to AS to2, w2.is_day AS day2
          FROM firms.method_weight w1
          JOIN firms.method_weight w2
            ON w2.version = w1.version AND w2.satellite = w1.satellite AND w2.cell2_id = w1.cell2_id
           AND w2.calendar_month = w1.calendar_month AND w1.ctid < w2.ctid
          WHERE w1.version = v_version AND w1.weight > 0 AND w2.weight > 0
            AND w1.date_from <= coalesce(w2.date_to, 'infinity'::date)
            AND w2.date_from <= coalesce(w1.date_to, 'infinity'::date)
            AND (w1.is_day IS NULL OR w2.is_day IS NULL OR w1.is_day = w2.is_day)) o
    JOIN firms.satellite st ON st.id = o.satellite;
    IF overlap_count > 0 THEN
        RAISE EXCEPTION 'firms.build_series(%): % pairs of weight rows overlap, so their fires would count twice: %',
            v_version, overlap_count,
            array_to_string(overlap_rows[1:20], '; ') || CASE WHEN overlap_count > 20 THEN '; ...' ELSE '' END;
    END IF;

    -- A range and calendar month whose rows hold all 16 200 squares cannot miss one, so the fires are read only
    -- for the ranges and calendar months that do not.
    FOR seg IN
        WITH seg_month AS (
            SELECT w.satellite, w.date_from, coalesce(w.date_to, 'infinity'::date) AS date_to, w.calendar_month,
                   count(DISTINCT w.cell2_id) FILTER (WHERE w.cell2_id BETWEEN 0 AND 16199) AS squares
            FROM firms.method_weight w
            WHERE w.version = v_version
            GROUP BY w.satellite, w.date_from, coalesce(w.date_to, 'infinity'::date), w.calendar_month
        ), segment AS (
            SELECT DISTINCT sm.satellite, sm.date_from, sm.date_to FROM seg_month sm
        )
        SELECT s.satellite, s.date_from, s.date_to, array_agg(cm.m ORDER BY cm.m) AS months
        FROM segment s
        CROSS JOIN generate_series(1, 12) AS cm(m)
        LEFT JOIN seg_month sm ON sm.satellite = s.satellite AND sm.date_from = s.date_from
                              AND sm.date_to = s.date_to AND sm.calendar_month = cm.m
        WHERE coalesce(sm.squares, 0) < 16200 AND s.date_from < hi AND s.date_to >= lo
        GROUP BY s.satellite, s.date_from, s.date_to
    LOOP
        WITH missing AS (
            SELECT h.satellite, firms.cell2_id(h.cell_id) AS cell2,
                   date_trunc('month', h.acq_date::timestamp)::date AS mon, count(*) AS fires
            FROM firms.hotspot h
            WHERE h.satellite = seg.satellite
              AND h.acq_date >= greatest(seg.date_from, lo) AND h.acq_date <= seg.date_to AND h.acq_date < hi
              AND extract(month FROM h.acq_date)::int = ANY (seg.months)
              AND NOT EXISTS (
                  SELECT 1 FROM firms.method_weight w
                  WHERE w.version = v_version AND w.satellite = h.satellite
                    AND w.cell2_id = firms.cell2_id(h.cell_id)
                    AND w.calendar_month = extract(month FROM h.acq_date)::int
                    AND h.acq_date >= w.date_from AND h.acq_date <= coalesce(w.date_to, 'infinity'::date))
            GROUP BY 1, 2, 3
        )
        SELECT count(*), array_agg(format('%s %s square %s (%s fires)', st.code, to_char(mi.mon, 'YYYY-MM'),
                                          mi.cell2, mi.fires) ORDER BY mi.mon, mi.cell2)
          INTO found_count, found_gaps
        FROM missing mi
        JOIN firms.satellite st ON st.id = mi.satellite;
        gap_count := gap_count + found_count;
        gaps := gaps || coalesce(found_gaps, '{}');
    END LOOP;
    IF gap_count > 0 THEN
        RAISE EXCEPTION 'firms.build_series(%): % square-months have fires but no weight row: %',
            v_version, gap_count, array_to_string(gaps[1:20], '; ') || CASE WHEN gap_count > 20 THEN '; ...' ELSE '' END
            USING HINT = 'Every 2-degree square and calendar month with fires in the days of a satellite''s weight '
                         'rows needs a row of its own in firms.method_weight.';
    END IF;

    DELETE FROM firms.cell_month_series s WHERE s.version = v_version AND s.month >= lo AND s.month < hi;
    INSERT INTO firms.cell_month_series (version, cell_id, month, satellite, n_raw, n_harm)
    SELECT v_version, p.cell_id, date_trunc('month', p.acq_date::timestamp)::date, p.satellite, count(*),
           sum(p.weight)
    FROM firms.v_series_point p
    WHERE p.version = v_version AND p.acq_date >= lo AND p.acq_date < hi
    GROUP BY p.cell_id, date_trunc('month', p.acq_date::timestamp)::date, p.satellite;

    -- The squares of 1 and 2 degrees of the map's small zooms, from the sums just made.
    DELETE FROM firms.square_month_series s WHERE s.version = v_version AND s.month >= lo AND s.month < hi;
    INSERT INTO firms.square_month_series (version, side, month, sy, sx, n_raw, n_harm)
    SELECT v_version, sq.side, c.month, (c.cell_id / 1440) / sq.side, (c.cell_id % 1440) / sq.side, sum(c.n_raw),
           sum(c.n_harm)
    FROM firms.cell_month_series c
    CROSS JOIN (VALUES (4), (8)) AS sq(side)
    WHERE c.version = v_version AND c.month >= lo AND c.month < hi
    GROUP BY sq.side, c.month, (c.cell_id / 1440) / sq.side, (c.cell_id % 1440) / sq.side;

    DELETE FROM firms.method_month mm WHERE mm.version = v_version AND mm.month >= lo AND mm.month < hi;
    SELECT c.d_from, c.d_to INTO cov_from, cov_to FROM firms.coverage(v_version) c;
    IF cov_from IS NOT NULL THEN
        INSERT INTO firms.method_month (version, month, source)
        WITH viirs AS MATERIALIZED (  -- once, not once per month
            SELECT DISTINCT w.date_from, coalesce(w.date_to, 'infinity'::date) AS date_to, w.calendar_month
            FROM firms.method_weight w
            JOIN firms.satellite st ON st.id = w.satellite
            WHERE w.version = v_version AND w.weight > 0 AND st.instrument = 'VIIRS'
        )
        SELECT v_version, m.mon,
               CASE WHEN EXISTS (SELECT 1 FROM viirs vi
                                 WHERE vi.date_from < (m.mon + interval '1 month')::date AND vi.date_to >= m.mon
                                   AND vi.calendar_month = extract(month FROM m.mon)::int)
                    THEN 'viirs' ELSE 'modis' END
        FROM (SELECT gs::date AS mon
              FROM generate_series(greatest(date_trunc('month', cov_from::timestamp), lo::timestamp),
                                   least(date_trunc('month', cov_to::timestamp), hi::timestamp - interval '1 month'),
                                   interval '1 month') AS gs) m;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------------------------------------------
-- What the application calls (design, 6.6). The PL/pgSQL ones switch JIT off: PostGIS functions declare a high
-- cost, so each of their short queries would spend about 0.3 s compiling (measured on 2 million fires). They also
-- plan every query for its own values: after five calls in one connection PL/pgSQL would otherwise keep a generic
-- plan, which made map_features four to five times slower (measured on Brazil).

-- Monthly counts of a zone for the calendar. Months are whole: every month that meets [d_from, d_to] inside the
-- coverage of the version, with 0 when it has no fire. count is the rounded sum of weights and count_raw the number
-- of fires. count_error is the harmonized MODIS part times the largest rel_error of the month's MODIS satellites,
-- plus each VIIRS satellite's harmonized count times its own rel_error. A satellite's rel_error is that of the
-- method_error row of its source and satellite with the largest n_min not above its fires in the zone that month,
-- 0 without such a row; count_error is NULL when the version has no rows of error at all. partial marks the month
-- where the coverage ends before its last day, incomplete a month with a day of firms.method_gap.
CREATE FUNCTION firms.monthly_counts(aoi text, d_from date, d_to date, version text)
    RETURNS TABLE(year int, month int, count bigint, count_raw bigint, source text, partial boolean,
                  count_error bigint, incomplete boolean)
    LANGUAGE plpgsql STABLE
    SET search_path FROM CURRENT
    SET jit = off
    SET plan_cache_mode = force_custom_plan
AS $$
DECLARE
    v_version text := monthly_counts.version;
    zone geometry := firms.aoi_geom(monthly_counts.aoi);
    inner_cells int[];
    edge_cells int[];
    cov_from date;
    cov_to date;
    first_month date;
    last_month date;
    end_day date;
    has_error boolean;
BEGIN
    PERFORM firms.check_version(v_version);
    SELECT c.d_from, c.d_to INTO cov_from, cov_to FROM firms.coverage(v_version) c;
    -- greatest() and least() skip NULLs: without this a version with no days would answer months of zeros.
    IF cov_from IS NULL THEN
        RETURN;
    END IF;
    first_month := date_trunc('month', greatest(monthly_counts.d_from, cov_from)::timestamp)::date;
    last_month := date_trunc('month', least(monthly_counts.d_to, cov_to)::timestamp)::date;
    IF first_month IS NULL OR last_month IS NULL OR first_month > last_month THEN
        RETURN;
    END IF;
    end_day := (last_month + interval '1 month')::date;
    has_error := EXISTS (SELECT 1 FROM firms.method_error e WHERE e.version = v_version);
    -- Arrays, not a subquery: the plan of each call sees how many cells there are and looks them up by index.
    SELECT array_agg(c.cell_id) FILTER (WHERE c.is_inner), array_agg(c.cell_id) FILTER (WHERE NOT c.is_inner)
      INTO inner_cells, edge_cells
    FROM firms.aoi_cells(zone) c;

    RETURN QUERY
    WITH fires AS (
        SELECT s.month AS mon, s.satellite AS sat, s.n_raw::bigint AS n_raw, s.n_harm
        FROM firms.cell_month_series s
        WHERE s.version = v_version AND s.cell_id = ANY (inner_cells)
          AND s.month >= first_month AND s.month <= last_month
        UNION ALL
        SELECT date_trunc('month', p.acq_date::timestamp)::date, p.satellite, 1::bigint, p.weight
        FROM firms.v_series_point p
        WHERE p.version = v_version AND p.cell_id = ANY (edge_cells)
          AND p.acq_date >= first_month AND p.acq_date < end_day
          AND ST_Intersects(zone, ST_Point(p.lon_e5::float8 / 100000, p.lat_e5::float8 / 100000, 4326))
    ), per_satellite AS (
        SELECT f.mon, f.sat, sum(f.n_raw) AS n_raw, sum(f.n_harm) AS n_harm
        FROM fires f
        GROUP BY f.mon, f.sat
    ), per_month AS (
        SELECT ps.mon, sum(ps.n_raw) AS n_raw, sum(ps.n_harm) AS n_harm,
               sum(ps.n_harm) FILTER (WHERE st.instrument = 'MODIS') AS n_harm_modis,
               max(coalesce(err.rel_error, 0)) FILTER (WHERE st.instrument = 'MODIS' AND ps.n_harm > 0)
                   AS rel_error_modis,
               sum(ps.n_harm * coalesce(err.rel_error, 0)) FILTER (WHERE st.instrument <> 'MODIS' AND ps.n_harm > 0)
                   AS error_viirs
        FROM per_satellite ps
        JOIN firms.satellite st ON st.id = ps.sat
        LEFT JOIN LATERAL (
            SELECT e.rel_error FROM firms.method_error e
            WHERE e.version = v_version AND e.source = lower(st.instrument) AND e.satellite = ps.sat
              AND e.n_min <= ps.n_raw
            ORDER BY e.n_min DESC
            LIMIT 1) err ON true
        GROUP BY ps.mon
    )
    SELECT extract(year FROM m.mon)::int, extract(month FROM m.mon)::int,
           coalesce(round(pm.n_harm::numeric), 0)::bigint,
           coalesce(pm.n_raw, 0)::bigint,
           mm.source,
           m.mon = date_trunc('month', cov_to::timestamp)::date
               AND cov_to < (m.mon + interval '1 month' - interval '1 day')::date,
           CASE WHEN has_error
                THEN round((coalesce(pm.n_harm_modis * pm.rel_error_modis, 0)
                            + coalesce(pm.error_viirs, 0))::numeric)::bigint END,
           EXISTS (SELECT 1 FROM firms.method_gap gp
                   WHERE gp.version = v_version AND gp.day >= m.mon AND gp.day < (m.mon + interval '1 month')::date)
    FROM (SELECT gs::date AS mon
          FROM generate_series(first_month::timestamp, last_month::timestamp, interval '1 month') AS gs) m
    LEFT JOIN per_month pm ON pm.mon = m.mon
    LEFT JOIN firms.method_month mm ON mm.version = v_version AND mm.month = m.mon
    ORDER BY m.mon;
END
$$;

-- The fires of the series in a zone and dates, exact to the day, for the CSV: month after month, by date and time
-- inside a month, at most max_rows. source is the source of the series in the fire's month.
CREATE FUNCTION firms.hotspots_in(aoi text, d_from date, d_to date, version text, max_rows int)
    RETURNS TABLE(latitude float8, longitude float8, acq_date text, acq_time text, satellite text,
                  instrument text, confidence text, frp real, daynight text, source text, brightness real,
                  brightness_2 real, scan real, track real, firms_version text, weight float8)
    LANGUAGE plpgsql STABLE
    SET search_path FROM CURRENT
    SET jit = off
    SET plan_cache_mode = force_custom_plan
AS $$
DECLARE
    v_version text := hotspots_in.version;
    zone geometry := firms.aoi_geom(hotspots_in.aoi);
    inner_cells int[];
    edge_cells int[];
    cov_from date;
    cov_to date;
    first_day date;
    last_day date;
    mon date;
    mon_source text;
    rows_left bigint := hotspots_in.max_rows;
    rows_got bigint;
BEGIN
    IF rows_left IS NULL OR rows_left < 0 THEN
        RAISE EXCEPTION 'firms.hotspots_in: max_rows must be 0 or more, got %', coalesce(rows_left::text, 'NULL');
    END IF;
    PERFORM firms.check_version(v_version);
    IF rows_left = 0 THEN
        RETURN;
    END IF;
    SELECT c.d_from, c.d_to INTO cov_from, cov_to FROM firms.coverage(v_version) c;
    IF cov_from IS NULL THEN
        RETURN;
    END IF;
    first_day := greatest(hotspots_in.d_from, cov_from);
    last_day := least(hotspots_in.d_to, cov_to);
    IF first_day IS NULL OR last_day IS NULL OR first_day > last_day THEN
        RETURN;
    END IF;
    SELECT array_agg(c.cell_id) FILTER (WHERE c.is_inner), array_agg(c.cell_id) FILTER (WHERE NOT c.is_inner)
      INTO inner_cells, edge_cells
    FROM firms.aoi_cells(zone) c;
    IF inner_cells IS NULL AND edge_cells IS NULL THEN
        RETURN;
    END IF;

    mon := date_trunc('month', first_day::timestamp)::date;
    WHILE mon <= last_day AND rows_left > 0 LOOP
        SELECT mm.source INTO mon_source FROM firms.method_month mm WHERE mm.version = v_version AND mm.month = mon;
        RETURN QUERY
        SELECT p.lat_e5::float8 / 100000, p.lon_e5::float8 / 100000, to_char(p.acq_date, 'YYYY-MM-DD'),
               lpad(p.acq_time::text, 4, '0'), st.firms_value, st.instrument,
               CASE WHEN st.instrument = 'MODIS' THEN p.conf_pct::text ELSE p.conf_class::text END,
               p.frp, CASE WHEN p.is_day THEN 'D' ELSE 'N' END, mon_source, p.brightness, p.brightness_2,
               p.scan, p.track, array_to_string(b.versions, ','), p.weight
        FROM firms.v_series_point p
        JOIN firms.satellite st ON st.id = p.satellite
        LEFT JOIN firms.load_batch b ON b.id = p.batch_id
        WHERE p.version = v_version
          AND p.acq_date >= greatest(mon, first_day)
          AND p.acq_date <= least((mon + interval '1 month' - interval '1 day')::date, last_day)
          AND (p.cell_id = ANY (inner_cells)
               OR (p.cell_id = ANY (edge_cells)
                   AND ST_Intersects(zone, ST_Point(p.lon_e5::float8 / 100000, p.lat_e5::float8 / 100000, 4326))))
        ORDER BY p.acq_date, p.acq_time, p.satellite, p.lat_e5, p.lon_e5
        LIMIT rows_left;
        GET DIAGNOSTICS rows_got = ROW_COUNT;
        rows_left := rows_left - rows_got;
        mon := (mon + interval '1 month')::date;
    END LOOP;
END
$$;

-- What the map shows in a bbox and dates. From zoom 9 on, the fires of the series, exact to the day, at most
-- max_points, the newest first: kind 'point', lon, lat, satellite (the FIRMS value), acq_date, frp, weight and the
-- own_share of the MODIS factor (NULL without a row of firms.method_factor). The fires are read month by month from
-- the end, so a cut at max_points keeps the fresh ones and stops reading; a bbox that touches more than 20 000 cells
-- of 0.25 degrees is an error. Below zoom 9, the sums of whole months in cells of 0.25 degrees (zoom 7-8), 0.5 (6),
-- 1 (5) or 2 (4 and below) that the bbox touches: kind 'cell', the centre, the cell_* bounds, n_raw and n_harm, at
-- most max_points with the largest n_harm first. Cells of 1 and 2 degrees come from firms.square_month_series, the
-- others from firms.cell_month_series.
CREATE FUNCTION firms.map_features(west float8, south float8, east float8, north float8, zoom int,
                                   d_from date, d_to date, version text, max_points int)
    RETURNS TABLE(kind text, lon float8, lat float8, cell_west float8, cell_south float8, cell_east float8,
                  cell_north float8, satellite text, acq_date date, frp real, weight float8, n_raw bigint,
                  n_harm float8, own_share real)
    LANGUAGE plpgsql STABLE
    SET search_path FROM CURRENT
    SET jit = off
    SET plan_cache_mode = force_custom_plan
AS $$
DECLARE
    v_version text := map_features.version;
    first_day date := coalesce(map_features.d_from, '-infinity'::date);
    last_day date := coalesce(map_features.d_to, 'infinity'::date);
    cov_from date;
    cov_to date;
    mon date;
    mon_from date;
    mon_to date;
    points_left bigint := map_features.max_points;
    points_got bigint;
    ix0 int;
    ix1 int;
    iy0 int;
    iy1 int;
    step int;  -- the side of an answer cell, in cells of 0.25 degrees
BEGIN
    IF (map_features.west >= -180 AND map_features.west < map_features.east AND map_features.east <= 180
        AND map_features.south >= -90 AND map_features.south < map_features.north AND map_features.north <= 90)
       IS NOT TRUE THEN
        RAISE EXCEPTION 'firms.map_features: bbox must have -180 <= west < east <= 180 and -90 <= south < north '
                        '<= 90, got west %, south %, east %, north %',
            map_features.west, map_features.south, map_features.east, map_features.north;
    END IF;
    IF map_features.zoom IS NULL THEN
        RAISE EXCEPTION 'firms.map_features: zoom is NULL';
    END IF;
    IF map_features.max_points IS NULL OR map_features.max_points < 0 THEN
        RAISE EXCEPTION 'firms.map_features: max_points must be 0 or more, got %',
            coalesce(map_features.max_points::text, 'NULL');
    END IF;
    PERFORM firms.check_version(v_version);
    ix0 := least(floor((map_features.west + 180) / 0.25), 1439);
    ix1 := least(floor((map_features.east + 180) / 0.25), 1439);
    iy0 := least(floor((map_features.south + 90) / 0.25), 719);
    iy1 := least(floor((map_features.north + 90) / 0.25), 719);

    IF map_features.zoom >= 9 THEN
        -- Each month reads the fires of every cell the bbox touches: a world bbox took seconds. A 4K screen at zoom
        -- 9 touches about 1 000 cells.
        IF (ix1 - ix0 + 1) * (iy1 - iy0 + 1) > 20000 THEN
            RAISE EXCEPTION 'firms.map_features: from zoom 9 on, the bbox may touch at most 20000 cells of 0.25 '
                            'degrees, got % at zoom %', (ix1 - ix0 + 1) * (iy1 - iy0 + 1), map_features.zoom;
        END IF;
        -- The months to walk are those of the coverage: open dates would never end the walk.
        SELECT c.d_from, c.d_to INTO cov_from, cov_to FROM firms.coverage(v_version) c;
        first_day := greatest(first_day, cov_from);
        last_day := least(last_day, cov_to);
        IF cov_from IS NULL OR first_day > last_day THEN
            RETURN;
        END IF;
        mon := date_trunc('month', last_day::timestamp)::date;
        WHILE mon >= date_trunc('month', first_day::timestamp)::date AND points_left > 0 LOOP
            mon_from := greatest(mon, first_day);
            mon_to := least((mon + interval '1 month' - interval '1 day')::date, last_day);
            RETURN QUERY
            SELECT 'point'::text, pt.lon_e5::float8 / 100000, pt.lat_e5::float8 / 100000,
                   NULL::float8, NULL::float8, NULL::float8, NULL::float8,
                   st.firms_value, pt.acq_date, pt.frp, pt.weight, NULL::bigint, NULL::float8, f.own_share
            FROM (SELECT p.satellite, p.cell_id, p.lat_e5, p.lon_e5, p.acq_date, p.acq_time, p.frp, p.weight
                  FROM firms.v_series_point p
                  WHERE p.version = v_version AND p.acq_date >= mon_from AND p.acq_date <= mon_to
                    AND p.cell_id IN (SELECT r.iy * 1440 + c.ix
                                      FROM generate_series(iy0, iy1) AS r(iy), generate_series(ix0, ix1) AS c(ix))
                    AND p.lon_e5 >= map_features.west * 100000 AND p.lon_e5 <= map_features.east * 100000
                    AND p.lat_e5 >= map_features.south * 100000 AND p.lat_e5 <= map_features.north * 100000
                  ORDER BY p.acq_date DESC, p.acq_time DESC, p.satellite, p.lat_e5, p.lon_e5
                  LIMIT points_left) pt
            JOIN firms.satellite st ON st.id = pt.satellite
            LEFT JOIN firms.method_factor f
                   ON f.version = v_version AND f.satellite = pt.satellite AND f.cell2_id = firms.cell2_id(pt.cell_id)
                  AND f.calendar_month = extract(month FROM pt.acq_date)::int
            ORDER BY pt.acq_date DESC, pt.acq_time DESC, pt.satellite, pt.lat_e5, pt.lon_e5;
            GET DIAGNOSTICS points_got = ROW_COUNT;
            points_left := points_left - points_got;
            mon := (mon - interval '1 month')::date;
        END LOOP;
        RETURN;
    END IF;

    step := CASE WHEN map_features.zoom >= 7 THEN 1 WHEN map_features.zoom = 6 THEN 2
                 WHEN map_features.zoom = 5 THEN 4 ELSE 8 END;
    -- Whole answer cells: all the cells of every answer cell the bbox touches, wherever the bbox ends.
    ix0 := ix0 / step * step;
    iy0 := iy0 / step * step;
    ix1 := ix1 / step * step + step - 1;
    iy1 := iy1 / step * step + step - 1;
    mon_from := date_trunc('month', first_day::timestamp)::date;
    mon_to := date_trunc('month', last_day::timestamp)::date;
    -- Each query is planned for its step, so only one branch of the UNION is read.
    RETURN QUERY
    SELECT 'cell'::text, ((q.cx + 0.5) * step * 0.25 - 180)::float8, ((q.cy + 0.5) * step * 0.25 - 90)::float8,
           (q.cx * step * 0.25 - 180)::float8, (q.cy * step * 0.25 - 90)::float8,
           ((q.cx + 1) * step * 0.25 - 180)::float8, ((q.cy + 1) * step * 0.25 - 90)::float8,
           NULL::text, NULL::date, NULL::real, NULL::float8, q.n_raw, q.n_harm, NULL::real
    FROM (SELECT (cs.cell_id % 1440) / step AS cx, (cs.cell_id / 1440) / step AS cy,
                 sum(cs.n_raw)::bigint AS n_raw, sum(cs.n_harm) AS n_harm
          FROM firms.cell_month_series cs
          WHERE step < 4 AND cs.version = v_version
            AND cs.month >= mon_from AND cs.month <= mon_to
            AND cs.cell_id BETWEEN iy0 * 1440 AND iy1 * 1440 + 1439
            AND cs.cell_id / 1440 BETWEEN iy0 AND iy1
            AND cs.cell_id % 1440 BETWEEN ix0 AND ix1
          GROUP BY 1, 2
          UNION ALL
          SELECT sq.sx, sq.sy, sum(sq.n_raw)::bigint, sum(sq.n_harm)
          FROM firms.square_month_series sq
          WHERE step >= 4 AND sq.version = v_version AND sq.side = step
            AND sq.month >= mon_from AND sq.month <= mon_to
            AND sq.sy BETWEEN iy0 / step AND iy1 / step
            AND sq.sx BETWEEN ix0 / step AND ix1 / step
          GROUP BY 1, 2) q
    WHERE q.n_raw > 0
    ORDER BY q.n_harm DESC, q.cy, q.cx
    LIMIT map_features.max_points;
END
$$;

-- The row of a method version for /api/meta: version, label, params (the confidence filter behind the numbers)
-- and created_at. NULL when there is no such version.
CREATE FUNCTION firms.method_info(version text) RETURNS jsonb
    LANGUAGE sql STABLE PARALLEL SAFE
BEGIN ATOMIC
    SELECT jsonb_build_object('version', m.version, 'label', m.label, 'params', m.params,
                              'created_at', m.created_at)
    FROM firms.method m
    WHERE m.version = method_info.version;
END;

-- What the restored package covers: name, scope (world or countries), countries (null for the world), built_at.
CREATE FUNCTION firms.dataset_info() RETURNS jsonb
    LANGUAGE sql STABLE PARALLEL SAFE
BEGIN ATOMIC
    SELECT jsonb_build_object('name', d.name, 'scope', d.scope, 'countries', to_jsonb(d.countries),
                              'built_at', d.built_at)
    FROM firms.dataset d
    ORDER BY d.built_at DESC NULLS LAST, d.name
    LIMIT 1;
END;
