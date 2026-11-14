<?php

namespace Tests\Feature;

use App\Contracts\HotspotRepository;
use App\Models\Setting;
use App\Repositories\FakeHotspotRepository;
use Carbon\CarbonImmutable;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class PublicApiTest extends TestCase
{
    use RefreshDatabase;

    private const KYIV_REGION = [
        'type' => 'Polygon',
        'coordinates' => [[[30, 48], [34, 48], [34, 51], [30, 51], [30, 48]]],
    ];

    protected function setUp(): void
    {
        parent::setUp();
        // Freeze "today" so the partial month is deterministic.
        $this->app->instance(HotspotRepository::class, new FakeHotspotRepository(CarbonImmutable::parse('2026-11-14')));
    }

    public function test_meta_describes_data_and_limits(): void
    {
        $this->getJson('/api/meta')
            ->assertOk()
            ->assertJsonPath('data.from', '2000-11-01')
            ->assertJsonPath('data.to', '2026-11-13')
            ->assertJsonPath('demo', true)
            ->assertJsonStructure(['method' => ['version', 'grid_step'], 'sources', 'limits' => ['max_aoi_area_km2', 'csv_export_max_rows']]);
    }

    public function test_calendar_is_continuous_across_modis_viirs_switch(): void
    {
        $response = $this->postJson('/api/calendar', [
            'aoi' => self::KYIV_REGION,
            'date_from' => '2010-01-01',
            'date_to' => '2013-12-31',
        ])->assertOk();

        $cells = $response->json('cells');
        $this->assertCount(48, $cells, 'every month present, no gaps');
        $this->assertSame([2010, 2011, 2012, 2013], $response->json('years'));

        $byKey = collect($cells)->keyBy(fn ($c) => $c['year'].'-'.$c['month']);
        $this->assertSame('modis', $byKey['2011-12']['source']);
        $this->assertSame('viirs', $byKey['2012-1']['source']);

        // MODIS months are scaled to VIIRS-equivalent, so harmonized > raw.
        $modis = collect($cells)->where('source', 'modis')->where('count_raw', '>', 10)->first();
        $this->assertGreaterThan($modis['count_raw'], $modis['count']);

        $this->assertCount(12, $response->json('baseline.by_month'));
    }

    public function test_summary_compares_current_month_with_median(): void
    {
        $current = $this->postJson('/api/summary', ['aoi' => self::KYIV_REGION])
            ->assertOk()
            ->json('current_month');

        $this->assertSame(2026, $current['year']);
        $this->assertSame(11, $current['month']);
        $this->assertTrue($current['partial']);
        $this->assertSame(13, $current['days_elapsed']);
        $this->assertEqualsWithDelta($current['median'] * 13 / 30, $current['median_to_date'], 0.1);
        $this->assertContains($current['status'], ['above', 'normal', 'below']);
    }

    public function test_summary_rankings_are_sorted(): void
    {
        $json = $this->postJson('/api/summary', ['aoi' => self::KYIV_REGION, 'date_from' => '2005-01-01', 'date_to' => '2020-12-31'])
            ->assertOk()
            ->json();

        $counts = array_column($json['top_months'], 'count');
        $sorted = $counts;
        rsort($sorted);
        $this->assertSame($sorted, $counts);
        $this->assertCount(10, $json['top_months']);
        $this->assertSame(16, count($json['yearly']));
        $this->assertNotNull($json['trend']);
    }

    public function test_same_aoi_gives_same_numbers(): void
    {
        $a = $this->postJson('/api/calendar', ['aoi' => self::KYIV_REGION])->json('cells');
        $b = $this->postJson('/api/calendar', ['aoi' => self::KYIV_REGION])->json('cells');

        $this->assertSame($a, $b);
    }

    public function test_validation_errors(): void
    {
        $this->postJson('/api/calendar', [])->assertUnprocessable()->assertJsonValidationErrors('aoi');

        $this->postJson('/api/calendar', ['aoi' => ['type' => 'Polygon', 'coordinates' => [[[0, 0], [1, 1]]]]])
            ->assertUnprocessable()->assertJsonValidationErrors('aoi');

        $this->postJson('/api/calendar', ['aoi' => self::KYIV_REGION, 'date_from' => '2020-01-01', 'date_to' => '2019-01-01'])
            ->assertUnprocessable()->assertJsonValidationErrors('date_to');
    }

    public function test_rejects_aoi_larger_than_admin_limit(): void
    {
        Setting::put('max_aoi_area_km2', 1000);

        $this->postJson('/api/calendar', ['aoi' => self::KYIV_REGION])
            ->assertUnprocessable()
            ->assertJsonValidationErrors('aoi');
    }

    public function test_csv_export_respects_aoi_and_dates(): void
    {
        $response = $this->post('/api/export/csv', [
            'aoi' => self::KYIV_REGION,
            'date_from' => '2020-04-01',
            'date_to' => '2020-04-30',
        ], ['Accept' => 'text/csv']);

        $response->assertOk();
        $this->assertStringContainsString('attachment; filename=hotspots_20200401_20200430.csv', $response->headers->get('Content-Disposition'));

        $lines = array_values(array_filter(explode("\n", $response->streamedContent())));
        $header = str_getcsv(array_shift($lines), escape: '');
        $this->assertSame(['latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'instrument', 'confidence', 'frp', 'daynight', 'source'], $header);

        $this->assertSame((int) $response->headers->get('X-Export-Expected-Rows'), count($lines));
        $this->assertGreaterThan(0, count($lines));

        foreach ($lines as $line) {
            $row = array_combine($header, str_getcsv($line, escape: ''));
            $this->assertTrue($row['latitude'] >= 48 && $row['latitude'] <= 51);
            $this->assertTrue($row['longitude'] >= 30 && $row['longitude'] <= 34);
            $this->assertStringStartsWith('2020-04-', $row['acq_date']);
            $this->assertSame('VIIRS', $row['instrument']);
        }
    }

    public function test_csv_export_is_capped(): void
    {
        Setting::put('csv_export_max_rows', 1000);

        $response = $this->post('/api/export/csv', ['aoi' => self::KYIV_REGION, 'date_from' => '2020-01-01', 'date_to' => '2021-12-31']);

        $response->assertOk()->assertHeader('X-Export-Truncated', '1');
        $this->assertSame(1001, substr_count($response->streamedContent(), "\n"));
    }
}
