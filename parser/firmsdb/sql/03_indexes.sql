-- Indexes of the firms schema. restore.sh runs this file after the data is loaded, so the big tables are copied
-- without indexes to keep up on a first restore; a later restore keeps them.

-- Fires of a cell (design, 6.3). Made on every part of firms.hotspot, now and later.
CREATE INDEX IF NOT EXISTS hotspot_cell_id_idx ON firms.hotspot (cell_id);

-- Cells under a zone.
CREATE INDEX IF NOT EXISTS grid_cell_geom_idx ON firms.grid_cell USING gist (geom);

-- The day ranges of the series (firms.series_segments, behind firms.coverage on every request).
CREATE INDEX IF NOT EXISTS method_weight_segment_idx
    ON firms.method_weight (version, satellite, date_from, (coalesce(date_to, 'infinity'::date)))
    WHERE weight > 0;

-- Sums of a range of months in a bbox (firms.map_features below zoom 9).
CREATE INDEX IF NOT EXISTS cell_month_series_month_idx ON firms.cell_month_series (version, month, cell_id);
