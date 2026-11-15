<?php

namespace Tests\Unit;

use App\Support\Aoi;
use InvalidArgumentException;
use PHPUnit\Framework\TestCase;

class AoiTest extends TestCase
{
    public function test_closes_ring_and_computes_bbox(): void
    {
        $aoi = Aoi::fromGeoJson(['type' => 'Polygon', 'coordinates' => [[[30, 48], [34, 48], [34, 51], [30, 51]]]]);

        $this->assertCount(5, $aoi->ring);
        $this->assertSame(['west' => 30.0, 'south' => 48.0, 'east' => 34.0, 'north' => 51.0], $aoi->bbox());
    }

    public function test_area_of_one_degree_cell_at_equator(): void
    {
        // 1°×1° at the equator ≈ 12 364 km².
        $area = Aoi::fromBbox(0, 0, 1, 1)->areaKm2();

        $this->assertEqualsWithDelta(12364, $area, 50);
    }

    public function test_point_in_polygon(): void
    {
        $triangle = Aoi::fromGeoJson(['type' => 'Polygon', 'coordinates' => [[[0, 0], [10, 0], [0, 10], [0, 0]]]]);

        $this->assertTrue($triangle->contains(2, 2));
        $this->assertFalse($triangle->contains(8, 8));
    }

    public function test_rejects_out_of_range_coordinates(): void
    {
        $this->expectException(InvalidArgumentException::class);

        Aoi::fromGeoJson(['type' => 'Polygon', 'coordinates' => [[[0, 0], [200, 0], [0, 10]]]]);
    }

    public function test_rejects_degenerate_polygon(): void
    {
        $this->expectException(InvalidArgumentException::class);

        Aoi::fromGeoJson(['type' => 'Polygon', 'coordinates' => [[[0, 0], [1, 1]]]]);
    }
}
