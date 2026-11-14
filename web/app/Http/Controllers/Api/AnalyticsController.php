<?php

namespace App\Http\Controllers\Api;

use App\Contracts\HotspotRepository;
use App\Http\Controllers\Controller;
use App\Http\Requests\AoiQueryRequest;
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
            'demo' => $this->repository->isDemo(),
            'method' => [
                'version' => Setting::get('harmonization_method_version'),
                'grid_step' => Setting::get('grid_step'),
                'viirs_start' => '2012-01-01',
                'modis_min_confidence' => Setting::get('modis_min_confidence'),
                'viirs_confidence_levels' => Setting::get('viirs_confidence_levels'),
            ],
            'sources' => DataSource::query()->where('enabled', true)->orderBy('sort')
                ->get(['code', 'label', 'sensor', 'satellite', 'kind', 'available_from']),
            'limits' => [
                'max_aoi_area_km2' => Setting::get('max_aoi_area_km2'),
                'csv_export_max_rows' => Setting::get('csv_export_max_rows'),
            ],
        ]);
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
}
