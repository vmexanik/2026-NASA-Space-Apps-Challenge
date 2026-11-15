<?php

namespace App\Support;

use InvalidArgumentException;

/**
 * Area of interest: a single polygon ring in WGS84, [[lon, lat], ...], closed.
 * Holes and multipolygons are not supported (the UI only draws simple shapes).
 */
final class Aoi
{
    private const EARTH_RADIUS_KM = 6371.0088;

    /** @param list<array{0: float, 1: float}> $ring closed ring */
    private function __construct(public readonly array $ring) {}

    /** @param array<mixed> $geometry GeoJSON Polygon geometry */
    public static function fromGeoJson(array $geometry): self
    {
        if (($geometry['type'] ?? null) !== 'Polygon' || ! is_array($geometry['coordinates'][0] ?? null)) {
            throw new InvalidArgumentException('AOI must be a GeoJSON Polygon.');
        }

        $ring = [];
        foreach ($geometry['coordinates'][0] as $point) {
            if (! is_array($point) || count($point) < 2 || ! is_numeric($point[0]) || ! is_numeric($point[1])) {
                throw new InvalidArgumentException('Each AOI vertex must be [lon, lat].');
            }
            [$lon, $lat] = [(float) $point[0], (float) $point[1]];
            if ($lon < -180 || $lon > 180 || $lat < -90 || $lat > 90) {
                throw new InvalidArgumentException('AOI coordinates are out of range.');
            }
            $ring[] = [$lon, $lat];
        }

        if ($ring !== [] && $ring[0] !== $ring[count($ring) - 1]) {
            $ring[] = $ring[0];
        }

        if (count($ring) < 4) {
            throw new InvalidArgumentException('AOI polygon needs at least 3 distinct vertices.');
        }
        if (count($ring) > 1001) {
            throw new InvalidArgumentException('AOI polygon has too many vertices (max 1000).');
        }

        return new self($ring);
    }

    public static function fromBbox(float $west, float $south, float $east, float $north): self
    {
        return self::fromGeoJson(['type' => 'Polygon', 'coordinates' => [[
            [$west, $south], [$east, $south], [$east, $north], [$west, $north], [$west, $south],
        ]]]);
    }

    /** @return array{west: float, south: float, east: float, north: float} */
    public function bbox(): array
    {
        $lons = array_column($this->ring, 0);
        $lats = array_column($this->ring, 1);

        return ['west' => min($lons), 'south' => min($lats), 'east' => max($lons), 'north' => max($lats)];
    }

    /** @return array{lon: float, lat: float} */
    public function centroid(): array
    {
        $b = $this->bbox();

        return ['lon' => ($b['west'] + $b['east']) / 2, 'lat' => ($b['south'] + $b['north']) / 2];
    }

    /** Spherical polygon area in km² (good enough for UI limits and fake data). */
    public function areaKm2(): float
    {
        $sum = 0.0;
        $n = count($this->ring) - 1;
        for ($i = 0; $i < $n; $i++) {
            [$lon1, $lat1] = $this->ring[$i];
            [$lon2, $lat2] = $this->ring[$i + 1];
            $sum += deg2rad($lon2 - $lon1) * (2 + sin(deg2rad($lat1)) + sin(deg2rad($lat2)));
        }

        return abs($sum * self::EARTH_RADIUS_KM ** 2 / 2);
    }

    /** Ray casting point-in-polygon. */
    public function contains(float $lon, float $lat): bool
    {
        $inside = false;
        $n = count($this->ring) - 1;
        for ($i = 0, $j = $n - 1; $i < $n; $j = $i++) {
            [$xi, $yi] = $this->ring[$i];
            [$xj, $yj] = $this->ring[$j];
            if (($yi > $lat) !== ($yj > $lat) && $lon < ($xj - $xi) * ($lat - $yi) / ($yj - $yi) + $xi) {
                $inside = ! $inside;
            }
        }

        return $inside;
    }

    /** Stable fingerprint, used to seed fake data and as a cache key. */
    public function fingerprint(): string
    {
        return md5(json_encode(array_map(fn ($p) => [round($p[0], 4), round($p[1], 4)], $this->ring)));
    }

    /** @return array{type: string, coordinates: array} */
    public function toGeoJson(): array
    {
        return ['type' => 'Polygon', 'coordinates' => [$this->ring]];
    }
}
