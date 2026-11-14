<?php

namespace App\Http\Requests;

use App\Contracts\HotspotRepository;
use Carbon\CarbonImmutable;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Validator;

/**
 * Body of POST /api/map:
 *
 *   { "bbox": [west, south, east, north], "zoom": 7, "date_from": "2020-01-01", "date_to": "2020-12-31" }
 *
 * Longitudes past ±180 (the date line is on screen) are clipped to [-180, 180].
 */
class MapRequest extends FormRequest
{
    public function rules(): array
    {
        return [
            'bbox' => ['required', 'array', 'size:4'],
            'bbox.*' => ['required', 'numeric'],
            'zoom' => ['required', 'integer', 'min:0', 'max:22'],
            'date_from' => ['nullable', 'date_format:Y-m-d'],
            'date_to' => ['nullable', 'date_format:Y-m-d', 'after_or_equal:date_from'],
        ];
    }

    public function after(): array
    {
        return [function (Validator $validator) {
            if ($validator->errors()->isNotEmpty()) {
                return;
            }
            [$west, $south, $east, $north] = $this->bbox();
            if ($west >= $east || $south >= $north) {
                $validator->errors()->add('bbox', 'bbox must be [west, south, east, north] with west < east and south < north.');
            }
        }];
    }

    /** @return array{0: float, 1: float, 2: float, 3: float} */
    public function bbox(): array
    {
        [$west, $south, $east, $north] = array_map('floatval', array_values($this->input('bbox')));
        $clip = fn (float $v, float $limit) => max(-$limit, min($limit, $v));

        return [$clip($west, 180), $clip($south, 90), $clip($east, 180), $clip($north, 90)];
    }

    public function zoom(): int
    {
        return (int) $this->input('zoom');
    }

    public function dateFrom(): CarbonImmutable
    {
        return $this->filled('date_from')
            ? CarbonImmutable::parse($this->input('date_from'))
            : app(HotspotRepository::class)->coverage()['from'];
    }

    public function dateTo(): CarbonImmutable
    {
        return $this->filled('date_to')
            ? CarbonImmutable::parse($this->input('date_to'))
            : app(HotspotRepository::class)->coverage()['to'];
    }
}
