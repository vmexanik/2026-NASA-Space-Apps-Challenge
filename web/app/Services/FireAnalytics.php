<?php

namespace App\Services;

use App\Contracts\HotspotRepository;
use App\Support\Aoi;
use Carbon\CarbonImmutable;

/**
 * Turns a monthly series from the repository into the calendar and analytics the
 * UI shows. Pure computation, independent of where the numbers come from.
 *
 * Baseline ("historical") statistics always use the full record of complete months,
 * independent of the selected date range, so the comparison stays meaningful.
 */
final class FireAnalytics
{
    public function __construct(private readonly HotspotRepository $repository) {}

    /** @return array<string, mixed> */
    public function calendar(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to): array
    {
        [$series, $baseline] = $this->load($aoi);
        $cells = $this->inRange($series, $from, $to);

        $cells = array_map(function (array $row) use ($baseline) {
            $b = $baseline[$row['month']];

            return $row + [
                'anomaly' => $row['partial'] || $b['mean'] === null ? null : round($row['count'] - $b['mean'], 1),
                'anomaly_pct' => $row['partial'] || ! $b['mean'] ? null : round(($row['count'] / $b['mean'] - 1) * 100, 1),
                'z' => $row['partial'] || ! $b['std'] ? null : round(($row['count'] - $b['mean']) / $b['std'], 2),
            ];
        }, $cells);

        $counts = array_column($cells, 'count');

        return [
            'aoi' => $this->aoiInfo($aoi),
            'range' => $this->rangeInfo($cells, $from, $to),
            'years' => array_values(array_unique(array_column($cells, 'year'))),
            'cells' => $cells,
            'baseline' => [
                'years' => $this->baselineYears($series),
                'by_month' => array_values($baseline),
            ],
            'scale' => ['min' => 0, 'max' => $counts === [] ? 0 : max($counts)],
            'sources' => $this->sourceSummary($cells),
        ];
    }

    /** @return array<string, mixed> */
    public function summary(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to): array
    {
        [$series, $baseline] = $this->load($aoi);
        $cells = $this->inRange($series, $from, $to);

        // Annual totals within the range.
        $years = [];
        foreach ($cells as $row) {
            $years[$row['year']] ??= ['year' => $row['year'], 'count' => 0, 'count_error' => 0, 'count_raw' => 0, 'source' => $row['source'], 'months' => 0, 'complete' => true, 'incomplete' => false];
            $years[$row['year']]['count'] += $row['count'];
            $years[$row['year']]['count_raw'] += $row['count_raw'];
            if ($years[$row['year']]['source'] !== $row['source']) {
                $years[$row['year']]['source'] = 'mixed'; // the year where VIIRS takes over
            }
            // Upper bound of the year's error: the sum of the months' errors (null when the method has none).
            $years[$row['year']]['count_error'] = self::addError($years[$row['year']]['count_error'], $row['count_error'] ?? null);
            $years[$row['year']]['incomplete'] = $years[$row['year']]['incomplete'] || ($row['incomplete'] ?? false);
            $years[$row['year']]['months']++;
            if ($row['partial']) {
                $years[$row['year']]['complete'] = false;
            }
        }
        foreach ($years as &$y) {
            $y['complete'] = $y['complete'] && $y['months'] === 12;
            unset($y['months']);
        }
        unset($y);
        $years = array_values($years);

        $completeYears = array_values(array_filter($years, fn ($y) => $y['complete']));
        $yearMean = $completeYears === [] ? null : array_sum(array_column($completeYears, 'count')) / count($completeYears);

        $total = array_sum(array_column($cells, 'count'));
        $sortedMonths = $cells;
        usort($sortedMonths, fn ($a, $b) => $b['count'] <=> $a['count'] ?: [$b['year'], $b['month']] <=> [$a['year'], $a['month']]);
        $sortedYears = $years;
        usort($sortedYears, fn ($a, $b) => $b['count'] <=> $a['count']);

        $medians = array_map(fn ($b) => $b['median'] ?? 0, $baseline);
        $maxMedian = max($medians ?: [0]);

        return [
            'aoi' => $this->aoiInfo($aoi),
            'range' => $this->rangeInfo($cells, $from, $to),
            'totals' => [
                'hotspots' => $total,
                'hotspots_error' => array_reduce($cells, fn ($sum, $row) => self::addError($sum, $row['count_error'] ?? null), $cells === [] ? null : 0),
                'hotspots_raw' => array_sum(array_column($cells, 'count_raw')),
                'months' => count($cells),
                'mean_per_year' => $yearMean === null ? null : round($yearMean, 1),
                'peak_month' => $sortedMonths[0] ?? null,
                'peak_year' => $sortedYears[0] ?? null,
            ],
            'current_month' => $this->currentMonth($series, $baseline),
            'top_months' => array_slice($sortedMonths, 0, 10),
            'top_years' => array_slice($sortedYears, 0, 10),
            'yearly' => array_map(fn ($y) => $y + [
                'anomaly_pct' => $y['complete'] && $yearMean ? round(($y['count'] / $yearMean - 1) * 100, 1) : null,
            ], $years),
            'trend' => $this->trend($completeYears),
            'fire_season' => $maxMedian > 0
                ? array_keys(array_filter($medians, fn ($m) => $m >= 0.5 * $maxMedian))
                : [],
            'sources' => $this->sourceSummary($cells),
        ];
    }

    // --- internals -----------------------------------------------------------------

    /** Sum of errors that stays null once any part is null (a version without harmonization has no error). */
    private static function addError(?int $sum, ?int $error): ?int
    {
        return $sum === null || $error === null ? null : $sum + $error;
    }

    /** @return array{0: list<array>, 1: array<int, array>} full series + baseline keyed by month 1..12 */
    private function load(Aoi $aoi): array
    {
        $coverage = $this->repository->coverage();
        $series = $this->repository->monthlyCounts($aoi, $coverage['from'], $coverage['to']);

        $byMonth = array_fill(1, 12, []);
        foreach ($series as $row) {
            if (! $row['partial']) {
                $byMonth[$row['month']][] = $row['count'];
            }
        }

        $baseline = [];
        foreach ($byMonth as $month => $values) {
            sort($values);
            $n = count($values);
            $mean = $n ? array_sum($values) / $n : null;
            $baseline[$month] = [
                'month' => $month,
                'n' => $n,
                'median' => $n ? $this->quantile($values, 0.5) : null,
                'mean' => $mean === null ? null : round($mean, 1),
                'p10' => $n ? $this->quantile($values, 0.1) : null,
                'p90' => $n ? $this->quantile($values, 0.9) : null,
                'std' => $n > 1 ? round(sqrt(array_sum(array_map(fn ($v) => ($v - $mean) ** 2, $values)) / ($n - 1)), 1) : null,
                'values' => $values,
            ];
        }

        // Keep raw values internal (used for percentiles), not in the API.
        $public = array_map(function ($b) {
            unset($b['values']);

            return $b;
        }, $baseline);
        $this->baselineValues = array_map(fn ($b) => $b['values'], $baseline);

        return [$series, $public];
    }

    /** @var array<int, list<int>> */
    private array $baselineValues = [];

    private function inRange(array $series, CarbonImmutable $from, CarbonImmutable $to): array
    {
        $start = $from->year * 12 + $from->month;
        $end = $to->year * 12 + $to->month;

        return array_values(array_filter($series, function ($row) use ($start, $end) {
            $key = $row['year'] * 12 + $row['month'];

            return $key >= $start && $key <= $end;
        }));
    }

    private function currentMonth(array $series, array $baseline): ?array
    {
        $last = end($series);
        if ($last === false) {
            return null;
        }

        $lastDay = $this->repository->coverage()['to'];
        $daysInMonth = CarbonImmutable::create($last['year'], $last['month'], 1)->daysInMonth;
        $daysElapsed = $last['partial'] ? $lastDay->day : $daysInMonth;
        $fraction = $daysElapsed / $daysInMonth;

        $b = $baseline[$last['month']];
        $medianToDate = $b['median'] === null ? null : round($b['median'] * $fraction, 1);
        $projected = $fraction > 0 ? $last['count'] / $fraction : null;

        $ratio = $medianToDate ? round($last['count'] / $medianToDate, 2) : null;

        $values = $this->baselineValues[$last['month']] ?? [];
        $percentile = $values && $projected !== null
            ? (int) round(100 * count(array_filter($values, fn ($v) => $v <= $projected)) / count($values))
            : null;

        return [
            'year' => $last['year'],
            'month' => $last['month'],
            'count' => $last['count'],
            'partial' => $last['partial'],
            'days_elapsed' => $daysElapsed,
            'days_in_month' => $daysInMonth,
            'median' => $b['median'],
            'median_to_date' => $medianToDate,
            'projected' => $projected === null ? null : (int) round($projected),
            'ratio' => $ratio,
            'percentile' => $percentile,
            'status' => match (true) {
                $ratio === null => 'unknown',
                $ratio >= 1.5 => 'above',
                $ratio <= 0.67 => 'below',
                default => 'normal',
            },
            'baseline_years' => $b['n'],
        ];
    }

    /** OLS slope over complete years. */
    private function trend(array $completeYears): ?array
    {
        $n = count($completeYears);
        if ($n < 3) {
            return null;
        }

        $xs = array_column($completeYears, 'year');
        $ys = array_column($completeYears, 'count');
        $mx = array_sum($xs) / $n;
        $my = array_sum($ys) / $n;
        $sxx = array_sum(array_map(fn ($x) => ($x - $mx) ** 2, $xs));
        $sxy = 0;
        foreach ($xs as $i => $x) {
            $sxy += ($x - $mx) * ($ys[$i] - $my);
        }
        $slope = $sxx > 0 ? $sxy / $sxx : 0;
        $pctPerDecade = $my > 0 ? $slope * 10 / $my * 100 : null;

        return [
            'slope_per_year' => round($slope, 1),
            'pct_per_decade' => $pctPerDecade === null ? null : round($pctPerDecade, 1),
            'years' => [min($xs), max($xs)],
            'direction' => match (true) {
                $pctPerDecade === null || abs($pctPerDecade) < 5 => 'flat',
                $pctPerDecade > 0 => 'up',
                default => 'down',
            },
        ];
    }

    private function quantile(array $sorted, float $q): float
    {
        $pos = ($count = count($sorted)) > 1 ? $q * ($count - 1) : 0;
        $lo = (int) floor($pos);
        $hi = (int) ceil($pos);

        return round($sorted[$lo] + ($sorted[$hi] - $sorted[$lo]) * ($pos - $lo), 1);
    }

    private function baselineYears(array $series): ?array
    {
        $complete = array_filter($series, fn ($r) => ! $r['partial']);

        return $complete === [] ? null : [min(array_column($complete, 'year')), max(array_column($complete, 'year'))];
    }

    private function sourceSummary(array $cells): array
    {
        $out = ['modis' => 0, 'viirs' => 0];
        foreach ($cells as $row) {
            $out[$row['source']] = ($out[$row['source']] ?? 0) + 1;
        }

        return ['months_by_source' => $out, 'modis_to_viirs_note' => 'MODIS months are scaled to VIIRS-equivalent counts.'];
    }

    private function aoiInfo(Aoi $aoi): array
    {
        return ['area_km2' => round($aoi->areaKm2(), 1), 'bbox' => $aoi->bbox()];
    }

    private function rangeInfo(array $cells, CarbonImmutable $from, CarbonImmutable $to): array
    {
        $coverage = $this->repository->coverage();

        return [
            'from' => $from->max($coverage['from'])->toDateString(),
            'to' => $to->min($coverage['to'])->toDateString(),
        ];
    }
}
