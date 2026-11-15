<?php

namespace Tests\Support;

use App\Contracts\HotspotRepository;
use App\Support\Aoi;
use Carbon\CarbonImmutable;
use Random\Engine\Mt19937;
use Random\Randomizer;

/**
 * Test double: deterministic synthetic hotspots, so API tests run without the firms schema.
 * To be replaced by fixtures shaped like the real data once the test package exists.
 *
 * Same AOI → same numbers. Mimics what real data looks like:
 *  - latitude-dependent fire season, year-to-year variability, occasional extreme years;
 *  - before 2012 only MODIS exists: raw MODIS detections are fewer, the harmonized
 *    value is raw × MODIS_TO_VIIRS (the "transfer coefficient" of the real method);
 *  - the current month is partial.
 */
final class FakeHotspotRepository implements HotspotRepository
{
    public const MODIS_TO_VIIRS = 2.6;

    private const DATA_START = '2000-11-01';

    private const VIIRS_START = '2012-01-01';

    /** @param bool $harmonized false gives months without error figures (as raw, unharmonized data would) */
    public function __construct(private readonly ?CarbonImmutable $today = null, private readonly bool $harmonized = true) {}

    public function method(): array
    {
        return [
            'version' => 'v1-2026-11-14',
            'label' => 'Test method',
            'params' => ['confidence_filter' => null],
            'created_at' => '2026-11-14T00:00:00+00:00',
        ];
    }

    public function dataset(): ?array
    {
        return ['name' => 'test', 'scope' => 'countries', 'countries' => ['Ukraine'], 'built_at' => '2026-11-14T00:00:00+00:00'];
    }

    public function hotspotCount(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to, int $limit): int
    {
        $n = 0;
        foreach ($this->hotspots($aoi, $from, $to, $limit) as $_) {
            $n++;
        }

        return $n;
    }

    public function mapFeatures(float $west, float $south, float $east, float $north, int $zoom,
        CarbonImmutable $from, CarbonImmutable $to, int $maxPoints): array
    {
        $out = [];
        $rnd = new Randomizer(new Mt19937(crc32("$west,$south,$east,$north,$zoom")));
        for ($i = 0; $i < min(50, $maxPoints); $i++) {
            $lon = $rnd->getFloat($west, $east);
            $lat = $rnd->getFloat($south, $north);
            $out[] = $zoom >= 9
                ? ['kind' => 'point', 'lon' => $lon, 'lat' => $lat, 'cell_west' => null, 'cell_south' => null,
                    'cell_east' => null, 'cell_north' => null, 'satellite' => $i % 2 ? 'Aqua' : 'N',
                    'acq_date' => $from->toDateString(), 'frp' => 10.0, 'weight' => $i % 2 ? 2.6 : 1.0,
                    'n_raw' => null, 'n_harm' => null, 'own_share' => $i % 2 ? 0.4 : null]
                : ['kind' => 'cell', 'lon' => null, 'lat' => null, 'cell_west' => $lon, 'cell_south' => $lat,
                    'cell_east' => $lon + 0.25, 'cell_north' => $lat + 0.25, 'satellite' => null, 'acq_date' => null,
                    'frp' => null, 'weight' => null, 'n_raw' => 10, 'n_harm' => 14.5, 'own_share' => null];
        }

        return $out;
    }

    public function coverage(): array
    {
        return [
            'from' => CarbonImmutable::parse(self::DATA_START),
            'to' => $this->today()->subDay(), // NRT lag: yesterday is the last full day
        ];
    }

    public function monthlyCounts(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to): array
    {
        $coverage = $this->coverage();
        $from = $from->max($coverage['from'])->startOfMonth();
        $to = $to->min($coverage['to']);

        $seed = $aoi->fingerprint();
        $profile = $this->profile($aoi, $seed);
        $rows = [];

        for ($m = $from; $m->lessThanOrEqualTo($to); $m = $m->addMonth()) {
            $rows[] = $this->month($m->year, $m->month, $profile, $seed, $coverage['to']);
        }

        return $rows;
    }

    public function hotspots(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to, int $maxRows): iterable
    {
        $n = 0;
        $bbox = $aoi->bbox();
        $from = $from->startOfDay();
        $to = $to->endOfDay();

        foreach ($this->monthlyCounts($aoi, $from, $to) as $row) {
            $monthStart = CarbonImmutable::create($row['year'], $row['month'], 1);
            $days = $monthStart->daysInMonth;
            $rnd = new Randomizer(new Mt19937(crc32($aoi->fingerprint().$row['year'].'-'.$row['month'])));

            for ($i = 0; $i < $row['count_raw']; $i++) {
                $date = $monthStart->addDays($rnd->getInt(0, $days - 1));
                if ($date->lessThan($from) || $date->greaterThan($to)) {
                    continue;
                }

                // Rejection sampling inside the polygon.
                $point = null;
                for ($try = 0; $try < 50 && $point === null; $try++) {
                    $lon = $rnd->getFloat($bbox['west'], $bbox['east']);
                    $lat = $rnd->getFloat($bbox['south'], $bbox['north']);
                    if ($aoi->contains($lon, $lat)) {
                        $point = [$lon, $lat];
                    }
                }
                if ($point === null) {
                    continue;
                }

                if ($n++ >= $maxRows) {
                    return;
                }
                yield $this->detection($rnd, $row['source'], $date, $point);
            }
        }
    }

    // --- internals -----------------------------------------------------------------

    private function today(): CarbonImmutable
    {
        return ($this->today ?? CarbonImmutable::now())->startOfDay();
    }

    /** @return array{density: float, season: list<float>, trend: float} */
    private function profile(Aoi $aoi, string $seed): array
    {
        $lat = $aoi->centroid()['lat'];

        $season = match (true) {
            $lat >= 35 => [0.02, 0.03, 0.12, 0.20, 0.07, 0.05, 0.10, 0.17, 0.12, 0.07, 0.03, 0.02],
            $lat >= 10 => [0.12, 0.18, 0.20, 0.15, 0.08, 0.04, 0.03, 0.03, 0.03, 0.04, 0.05, 0.05],
            $lat >= -10 => [0.14, 0.12, 0.06, 0.03, 0.04, 0.08, 0.12, 0.13, 0.10, 0.06, 0.05, 0.07],
            default => [0.02, 0.02, 0.02, 0.03, 0.05, 0.08, 0.13, 0.20, 0.22, 0.13, 0.06, 0.04],
        };

        // VIIRS-equivalent detections per km² per year; varies by AOI.
        $density = 0.02 * (0.5 + 1.5 * $this->u($seed, 'density'));

        return [
            'density' => $density * $aoi->areaKm2(),
            'season' => $season,
            'trend' => -0.02 + 0.04 * $this->u($seed, 'trend'), // ±2 %/year
        ];
    }

    /** @return array<string, mixed> one monthlyCounts row */
    private function month(int $year, int $month, array $profile, string $seed, CarbonImmutable $lastDay): array
    {
        $yearFactor = exp(0.35 * $this->normal($seed, "y$year"));
        if ($this->u($seed, "extreme$year") > 0.88) {
            $yearFactor *= 2.0;
        }
        $monthNoise = exp(0.35 * $this->normal($seed, "m$year-$month"));
        $trend = (1 + $profile['trend']) ** ($year - 2000);

        $partial = $year === $lastDay->year && $month === $lastDay->month && ! $lastDay->isLastOfMonth();
        $fraction = $partial ? $lastDay->day / $lastDay->daysInMonth : 1.0;

        $expected = $profile['density'] * $profile['season'][$month - 1] * $yearFactor * $monthNoise * $trend * $fraction;

        if (CarbonImmutable::create($year, $month, 1)->lessThan(CarbonImmutable::parse(self::VIIRS_START))) {
            $raw = (int) round($expected / self::MODIS_TO_VIIRS * exp(0.15 * $this->normal($seed, "s$year-$month")));

            return [
                'year' => $year, 'month' => $month,
                'count' => (int) round($raw * self::MODIS_TO_VIIRS),
                'count_raw' => $raw,
                'source' => 'modis',
                'partial' => $partial,
                'count_error' => $this->harmonized ? (int) round($raw * self::MODIS_TO_VIIRS * 0.2) : null,
                'incomplete' => $year <= 2002 && $month === 6, // a Terra gap
            ];
        }

        $count = (int) round($expected);

        return [
            'year' => $year, 'month' => $month,
            'count' => $count, 'count_raw' => $count,
            'source' => 'viirs',
            'partial' => $partial,
            'count_error' => $this->harmonized ? 0 : null,
            'incomplete' => false,
        ];
    }

    private function detection(Randomizer $rnd, string $source, CarbonImmutable $date, array $point): array
    {
        $day = $rnd->getInt(0, 1) === 1;
        $modis = $source === 'modis';

        // Nominal overpass (minutes after midnight): Terra 10:30/22:30, Aqua & S-NPP 13:30/01:30.
        $overpass = $modis
            ? ($day ? [630, 810] : [1350, 90])[$rnd->getInt(0, 1)]
            : ($day ? 810 : 90);
        // Jitter by up to ±40 min.
        $minutes = $overpass + $rnd->getInt(-40, 40);
        $minutes = ($minutes + 1440) % 1440;

        return [
            'latitude' => round($point[1], 5),
            'longitude' => round($point[0], 5),
            'acq_date' => $date->toDateString(),
            'acq_time' => sprintf('%02d%02d', intdiv($minutes, 60), $minutes % 60),
            'satellite' => $modis ? ($rnd->getInt(0, 1) ? 'Terra' : 'Aqua') : 'N',
            'instrument' => $modis ? 'MODIS' : 'VIIRS',
            'confidence' => $modis ? (string) $rnd->getInt(30, 100) : ['l', 'n', 'n', 'n', 'h'][$rnd->getInt(0, 4)],
            'frp' => round(exp($rnd->getFloat(log(1), log($modis ? 400 : 150))), 1),
            'daynight' => $day ? 'D' : 'N',
            'source' => $source,
            'brightness' => 320.5,
            'brightness_2' => 290.1,
            'scan' => $modis ? 1.2 : 0.4,
            'track' => $modis ? 1.1 : 0.4,
            'firms_version' => $modis ? '6.03' : '2.0NRT',
            'weight' => $modis ? self::MODIS_TO_VIIRS : 1.0,
        ];
    }

    /** Uniform [0, 1) from a hash: order-independent and stable. */
    private function u(string $seed, string $key): float
    {
        return hexdec(substr(md5($seed.'|'.$key), 0, 12)) / 0x1000000000000;
    }

    /** Standard normal via Box–Muller. */
    private function normal(string $seed, string $key): float
    {
        $u1 = max($this->u($seed, $key.'a'), 1e-12);
        $u2 = $this->u($seed, $key.'b');

        return sqrt(-2 * log($u1)) * cos(2 * M_PI * $u2);
    }
}
