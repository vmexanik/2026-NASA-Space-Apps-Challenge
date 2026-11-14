<?php

namespace App\Http\Controllers\Api;

use App\Contracts\HotspotRepository;
use App\Http\Controllers\Controller;
use App\Http\Requests\AoiQueryRequest;
use App\Http\Requests\MapRequest;
use App\Models\AreaPreset;
use App\Models\DataSource;
use App\Models\Setting;
use App\Services\FireAnalytics;
use Illuminate\Http\JsonResponse;

class AnalyticsController extends Controller
{
    public function __construct(
        private readonly FireAnalytics $analytics,
        private readonly HotspotRepository $repository,
    ) {}

    /** GET /api/meta: what the UI needs before the first query. */
    public function meta(): JsonResponse
    {
        $coverage = $this->repository->coverage();

        return response()->json([
            'data' => [
                'from' => $coverage['from']->toDateString(),
                'to' => $coverage['to']->toDateString(),
            ],
            // The method as built in the database (its params say which points it counts).
            'method' => $this->method(),
            'dataset' => $this->repository->dataset(),
            'presets' => AreaPreset::query()->where('enabled', true)->orderBy('sort')->orderBy('id')->get()
                ->map(fn (AreaPreset $p) => $p->toPublic()),
            'sources' => DataSource::query()->where('enabled', true)->orderBy('sort')
                ->get(['code', 'label', 'sensor', 'satellite', 'kind', 'available_from']),
            'limits' => [
                'max_aoi_area_km2' => Setting::get('max_aoi_area_km2'),
                'csv_export_max_rows' => Setting::get('csv_export_max_rows'),
            ],
        ]);
    }

    /** The method from the database plus the name people see ({en, uk}). */
    private function method(): array
    {
        return $this->repository->method() + ['name' => config('we_charge.harmonization.name')];
    }

    /** POST /api/calendar: month × year matrix with baseline and anomalies. */
    public function calendar(AoiQueryRequest $request): JsonResponse
    {
        return response()->json(
            $this->analytics->calendar($request->aoi(), $request->dateFrom(), $request->dateTo()),
        );
    }

    /** POST /api/summary: key figures, rankings, current month vs median, trend. */
    public function summary(AoiQueryRequest $request): JsonResponse
    {
        return response()->json(
            $this->analytics->summary($request->aoi(), $request->dateFrom(), $request->dateTo()),
        );
    }

    /**
     * POST /api/map: GeoJSON FeatureCollection of the fires in the visible box.
     * Points from zoom 9, grid cells below. "truncated" says the points hit the cap.
     */
    public function map(MapRequest $request): JsonResponse
    {
        [$west, $south, $east, $north] = $request->bbox();
        $max = (int) config('we_charge.map_max_points');

        $rows = $this->repository->mapFeatures($west, $south, $east, $north, $request->zoom(),
            $request->dateFrom(), $request->dateTo(), $max + 1);
        $truncated = count($rows) > $max;
        if ($truncated) {
            $rows = array_slice($rows, 0, $max);
        }

        return response()->json([
            'type' => 'FeatureCollection',
            'truncated' => $truncated,
            'features' => array_map(fn (array $r) => $r['kind'] === 'point'
                ? [
                    'type' => 'Feature',
                    'geometry' => ['type' => 'Point', 'coordinates' => [$r['lon'], $r['lat']]],
                    'properties' => [
                        'kind' => 'point',
                        'satellite' => $r['satellite'],
                        'acq_date' => $r['acq_date'],
                        'frp' => $r['frp'],
                        'weight' => $r['weight'],
                        'own_share' => $r['own_share'],
                    ],
                ]
                : [
                    'type' => 'Feature',
                    'geometry' => ['type' => 'Polygon', 'coordinates' => [[
                        [$r['cell_west'], $r['cell_south']], [$r['cell_east'], $r['cell_south']],
                        [$r['cell_east'], $r['cell_north']], [$r['cell_west'], $r['cell_north']],
                        [$r['cell_west'], $r['cell_south']],
                    ]]],
                    'properties' => ['kind' => 'cell', 'n_harm' => $r['n_harm'], 'n_raw' => $r['n_raw']],
                ], $rows),
        ]);
    }
}
