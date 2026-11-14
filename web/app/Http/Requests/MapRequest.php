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
    /** Zoom from which the map shows single fires, and the cell limit of firms.map_features there. */
    public const POINTS_ZOOM = 9;

    public const MAX_POINT_CELLS = 20000;

    /** 0.25° cells the bbox touches, counted as firms.map_features does. */
    public static function cellCount(float $west, float $south, float $east, float $north): int
    {
        $ix = fn (float $lon) => min((int) floor(($lon + 180) / 0.25), 1439);
        $iy = fn (float $lat) => min((int) floor(($lat + 90) / 0.25), 719);

        return ($ix($east) - $ix($west) + 1) * ($iy($north) - $iy($south) + 1);
    }

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

            // From zoom 9 firms.map_features reads single fires and refuses a bbox over this many 0.25° cells
            // (about 35° × 35°); a map window never comes close (a 4K screen at zoom 9 is ~1 000 cells).
            if ($this->zoom() >= self::POINTS_ZOOM && self::cellCount($west, $south, $east, $north) > self::MAX_POINT_CELLS) {
                $validator->errors()->add('bbox', sprintf(
                    'At zoom %d and above the bbox may cover at most %s cells of 0.25° (about 35° × 35°); zoom in or send a lower zoom.',
                    self::POINTS_ZOOM, number_format(self::MAX_POINT_CELLS)));
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
