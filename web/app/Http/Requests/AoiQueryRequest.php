<?php

namespace App\Http\Requests;

use App\Contracts\HotspotRepository;
use App\Models\Setting;
use App\Support\Aoi;
use Carbon\CarbonImmutable;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Validator;
use InvalidArgumentException;

/**
 * Body shared by /api/calendar, /api/summary and /api/export/csv:
 *
 *   {
 *     "aoi": { "type": "Polygon", "coordinates": [[[lon, lat], ...]] },   // GeoJSON geometry
 *     "date_from": "2001-01-01",   // optional, defaults to start of data
 *     "date_to":   "2026-11-13"    // optional, defaults to last day with data
 *   }
 */
class AoiQueryRequest extends FormRequest
{
    private ?Aoi $aoi = null;

    public function rules(): array
    {
        return [
            'aoi' => ['required', 'array'],
            'aoi.type' => ['required', 'in:Polygon'],
            'aoi.coordinates' => ['required', 'array', 'min:1'],
            'date_from' => ['nullable', 'date_format:Y-m-d'],
            'date_to' => ['nullable', 'date_format:Y-m-d', 'after_or_equal:date_from'],
        ];
    }

    public function after(): array
    {
        return [function (Validator $validator) {
            if ($validator->errors()->has('aoi') || $validator->errors()->has('aoi.type') || $validator->errors()->has('aoi.coordinates')) {
                return;
            }
            try {
                $this->aoi = Aoi::fromGeoJson($this->input('aoi'));
            } catch (InvalidArgumentException $e) {
                $validator->errors()->add('aoi', $e->getMessage());

                return;
            }

            $max = (int) Setting::get('max_aoi_area_km2');
            if ($this->aoi->areaKm2() > $max) {
                $validator->errors()->add('aoi', sprintf('AOI is too large (%s km², max %s km²).',
                    number_format($this->aoi->areaKm2()), number_format($max)));
            }
        }];
    }

    public function aoi(): Aoi
    {
        return $this->aoi ??= Aoi::fromGeoJson($this->input('aoi'));
    }

    public function dateFrom(): CarbonImmutable
    {
        $coverage = app(HotspotRepository::class)->coverage();

        return $this->filled('date_from') ? CarbonImmutable::parse($this->input('date_from')) : $coverage['from'];
    }

    public function dateTo(): CarbonImmutable
    {
        $coverage = app(HotspotRepository::class)->coverage();

        return $this->filled('date_to') ? CarbonImmutable::parse($this->input('date_to')) : $coverage['to'];
    }
}
