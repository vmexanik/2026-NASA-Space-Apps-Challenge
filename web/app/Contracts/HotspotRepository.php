<?php

namespace App\Contracts;

use App\Support\Aoi;
use Carbon\CarbonImmutable;

/**
 * The only seam between the web app and the hotspot storage (the firms schema in PostGIS,
 * see docs/database/README.md). Numbers follow the one harmonization method
 * (config we_charge.harmonization.version); methods throw App\Exceptions\DataUnavailable
 * when the database has no data for it.
 */
interface HotspotRepository
{
    /**
     * Monthly hotspot counts inside the AOI, ordered by year, month, for every month
     * between $from and $to inclusive (months without fires must be present with 0).
     * Months are taken whole; the range is clipped to coverage().
     *
     * @return list<array{
     *     year: int,
     *     month: int,
     *     count: int,             // harmonized, VIIRS-equivalent count
     *     count_raw: int,         // detections that the series counts
     *     source: string,         // 'modis' (scaled to VIIRS-equivalent) | 'viirs'
     *     partial: bool,          // month not finished yet
     *     count_error: int|null,  // typical error of count; null when the method gives none
     *     incomplete: bool,       // some days of the month have no satellite at all
     * }>
     */
    public function monthlyCounts(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to): array;

    /**
     * Detections the calendar counts, inside the AOI and the exact days, for CSV export.
     * Streams (cursor), never more than $maxRows rows.
     *
     * @return iterable<array{
     *     latitude: float, longitude: float, acq_date: string, acq_time: string,
     *     satellite: string, instrument: string, confidence: string, frp: float,
     *     daynight: string, source: string, brightness: float|null, brightness_2: float|null,
     *     scan: float|null, track: float|null, firms_version: string|null, weight: float,
     * }>
     */
    public function hotspots(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to, int $maxRows): iterable;

    /** Number of rows hotspots() would give, counted up to $limit (so a cap can be detected cheaply). */
    public function hotspotCount(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to, int $limit): int;

    /**
     * Map objects in a bounding box: points at zoom >= 9, otherwise grid cells (whole months).
     *
     * @return list<array{kind: string, lon: ?float, lat: ?float, cell_west: ?float, cell_south: ?float,
     *     cell_east: ?float, cell_north: ?float, satellite: ?string, acq_date: ?string, frp: ?float,
     *     weight: ?float, n_raw: ?int, n_harm: ?float, own_share: ?float}>
     */
    public function mapFeatures(float $west, float $south, float $east, float $north, int $zoom,
        CarbonImmutable $from, CarbonImmutable $to, int $maxPoints): array;

    /** First and last day with data. @return array{from: CarbonImmutable, to: CarbonImmutable} */
    public function coverage(): array;

    /** The harmonization method as stored in the database: version, label, params, created_at. */
    public function method(): array;

    /** What the database covers: name, scope (world|countries), countries, built_at. Null if empty. */
    public function dataset(): ?array;
}
