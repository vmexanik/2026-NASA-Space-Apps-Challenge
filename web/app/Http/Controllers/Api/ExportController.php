<?php

namespace App\Http\Controllers\Api;

use App\Contracts\HotspotRepository;
use App\Http\Controllers\Controller;
use App\Http\Requests\AoiQueryRequest;
use App\Models\Setting;
use Symfony\Component\HttpFoundation\StreamedResponse;

class ExportController extends Controller
{
    public const COLUMNS = [
        'latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'instrument',
        'confidence', 'frp', 'daynight', 'source',
    ];

    /**
     * POST /api/export/csv: raw detections in the AOI and date range, streamed.
     * Rows beyond csv_export_max_rows are cut; X-Export-Truncated tells the client.
     */
    public function csv(AoiQueryRequest $request, HotspotRepository $repository): StreamedResponse
    {
        $aoi = $request->aoi();
        $from = $request->dateFrom();
        $to = $request->dateTo();
        $max = (int) Setting::get('csv_export_max_rows');

        // Expected size from the aggregates, so the client can warn before downloading.
        $expected = array_sum(array_column($repository->monthlyCounts($aoi, $from, $to), 'count_raw'));

        $filename = sprintf('hotspots_%s_%s.csv', $from->format('Ymd'), $to->format('Ymd'));

        return response()->streamDownload(function () use ($repository, $aoi, $from, $to, $max) {
            $out = fopen('php://output', 'w');
            fputcsv($out, self::COLUMNS, escape: '');
            $n = 0;
            foreach ($repository->hotspots($aoi, $from, $to) as $row) {
                if ($n++ >= $max) {
                    break;
                }
                fputcsv($out, array_map(fn ($c) => $row[$c] ?? null, self::COLUMNS), escape: '');
                if ($n % 5000 === 0) {
                    flush();
                }
            }
            fclose($out);
        }, $filename, [
            'Content-Type' => 'text/csv; charset=UTF-8',
            'X-Export-Expected-Rows' => (string) $expected,
            'X-Export-Max-Rows' => (string) $max,
            'X-Export-Truncated' => $expected > $max ? '1' : '0',
            'Access-Control-Expose-Headers' => 'X-Export-Expected-Rows, X-Export-Max-Rows, X-Export-Truncated, Content-Disposition',
        ]);
    }
}
