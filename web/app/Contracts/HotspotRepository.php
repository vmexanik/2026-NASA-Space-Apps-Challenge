<?php

namespace App\Contracts;

use App\Support\Aoi;
use Carbon\CarbonImmutable;

/**
 * The only seam between the web app and the hotspot storage.
 *
 * Today it is implemented by FakeHotspotRepository (synthetic data). Once the parser's
 * schema is fixed, add a PostGIS implementation and switch WE_CHARGE_DATA_DRIVER.
 * Everything above this interface (analytics, API, SPA) stays unchanged.
 */
interface HotspotRepository
{
    /**
     * Monthly hotspot counts inside the AOI, ordered by year, month, for every month
     * between $from and $to inclusive (months without fires must be present with 0).
     *
     * @return list<array{
     *     year: int,
     *     month: int,
     *     count: int,          // harmonized, VIIRS-equivalent count
     *     count_raw: int,      // detections of the sensor actually used
     *     source: string,      // 'modis' (scaled to VIIRS-equivalent) | 'viirs'
     *     partial: bool,       // month not finished yet
     * }>
     */
    public function monthlyCounts(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to): array;

    /**
     * Raw detections inside the AOI and date range, for CSV export.
     * Must stream (generator / lazy cursor), never load everything into memory.
     *
     * @return iterable<array{
     *     latitude: float, longitude: float, acq_date: string, acq_time: string,
     *     satellite: string, instrument: string, confidence: string, frp: float,
     *     daynight: string, source: string,
     * }>
     */
    public function hotspots(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to): iterable;

    /** First and last day with data. @return array{from: CarbonImmutable, to: CarbonImmutable} */
    public function coverage(): array;

    /** True when the data is synthetic (shown as a banner in the UI). */
    public function isDemo(): bool;
}
