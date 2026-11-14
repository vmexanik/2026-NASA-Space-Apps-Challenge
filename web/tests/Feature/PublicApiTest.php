<?php

namespace Tests\Feature;

use App\Contracts\HotspotRepository;
use App\Models\AreaPreset;
use App\Models\Setting;
use App\Models\User;
use Carbon\CarbonImmutable;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Support\FakeHotspotRepository;
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
            ->assertJsonPath('method.version', 'v1-2026-11-14')
            ->assertJsonPath('method.params.confidence_filter', null)
            ->assertJsonPath('method.name.uk', 'Метод приведення за площею та місяцем')
            ->assertJsonPath('dataset.scope', 'countries')
            ->assertJsonPath('dataset.countries', ['Ukraine'])
            ->assertJsonMissingPath('demo')
            ->assertJsonStructure(['method' => ['version', 'label', 'params', 'name' => ['en', 'uk']], 'sources', 'limits' => ['max_aoi_area_km2', 'csv_export_max_rows']]);
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
        $this->assertSame([
            'latitude', 'longitude', 'acq_date', 'acq_time', 'satellite', 'instrument', 'confidence', 'frp', 'daynight', 'source',
            'brightness', 'brightness_2', 'scan', 'track', 'firms_version', 'weight',
        ], $header);

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

    public function test_csv_expected_rows_are_exact_for_part_of_a_month(): void
    {
        $response = $this->post('/api/export/csv', ['aoi' => self::KYIV_REGION, 'date_from' => '2020-04-10', 'date_to' => '2020-04-20']);

        $lines = array_values(array_filter(explode("\n", $response->streamedContent())));
        $response->assertHeader('X-Export-Truncated', '0');
        $this->assertSame(count($lines) - 1, (int) $response->headers->get('X-Export-Expected-Rows'));
    }

    public function test_calendar_cells_carry_error_and_incomplete(): void
    {
        $cells = collect($this->postJson('/api/calendar', ['aoi' => self::KYIV_REGION, 'date_from' => '2002-01-01', 'date_to' => '2012-12-31'])
            ->assertOk()->json('cells'))->keyBy(fn ($c) => $c['year'].'-'.$c['month']);

        $this->assertTrue($cells['2002-6']['incomplete']);
        $this->assertFalse($cells['2002-7']['incomplete']);
        $this->assertGreaterThan(0, $cells['2002-7']['count_error'] + $cells['2002-8']['count_error']);
        $this->assertSame(0, $cells['2012-7']['count_error']);
    }

    public function test_summary_sums_month_errors_into_years_and_totals(): void
    {
        $json = $this->postJson('/api/summary', ['aoi' => self::KYIV_REGION, 'date_from' => '2010-01-01', 'date_to' => '2011-12-31'])
            ->assertOk()->json();
        $calendar = $this->postJson('/api/calendar', ['aoi' => self::KYIV_REGION, 'date_from' => '2010-01-01', 'date_to' => '2011-12-31'])
            ->json('cells');

        $this->assertSame(array_sum(array_column($calendar, 'count_error')), $json['totals']['hotspots_error']);
        $y2010 = collect($json['yearly'])->firstWhere('year', 2010);
        $this->assertSame(
            array_sum(array_column(array_filter($calendar, fn ($c) => $c['year'] === 2010), 'count_error')),
            $y2010['count_error'],
        );
    }

    public function test_summary_error_stays_null_without_harmonization(): void
    {
        $this->app->instance(HotspotRepository::class, new FakeHotspotRepository(CarbonImmutable::parse('2026-11-14'), harmonized: false));

        $json = $this->postJson('/api/summary', ['aoi' => self::KYIV_REGION, 'date_from' => '2010-01-01', 'date_to' => '2011-12-31'])
            ->assertOk()->json();

        $this->assertNull($json['totals']['hotspots_error']);
        $this->assertNull($json['yearly'][0]['count_error']);
    }

    public function test_map_returns_cells_when_zoomed_out_and_points_when_zoomed_in(): void
    {
        $cells = $this->postJson('/api/map', ['bbox' => [22, 44, 40.5, 52.5], 'zoom' => 6, 'date_from' => '2020-01-01', 'date_to' => '2020-12-31'])
            ->assertOk()
            ->assertJsonPath('type', 'FeatureCollection')
            ->assertJsonPath('truncated', false)
            ->json('features');
        $this->assertSame('Polygon', $cells[0]['geometry']['type']);
        $this->assertArrayHasKey('n_harm', $cells[0]['properties']);

        $points = $this->postJson('/api/map', ['bbox' => [30, 50, 30.5, 50.3], 'zoom' => 10])->assertOk()->json('features');
        $this->assertSame('Point', $points[0]['geometry']['type']);
        $this->assertArrayHasKey('own_share', $points[0]['properties']);
    }

    public function test_map_clips_longitude_and_validates_bbox(): void
    {
        $this->postJson('/api/map', ['bbox' => [170, -10, 200, 10], 'zoom' => 4])->assertOk();
        $this->postJson('/api/map', ['bbox' => [10, 10, 5, 20], 'zoom' => 4])->assertUnprocessable()->assertJsonValidationErrors('bbox');
        $this->postJson('/api/map', ['bbox' => [1, 2, 3], 'zoom' => 4])->assertUnprocessable()->assertJsonValidationErrors('bbox');
    }

    public function test_map_reports_truncation(): void
    {
        config(['we_charge.map_max_points' => 10]);

        $json = $this->postJson('/api/map', ['bbox' => [30, 50, 30.5, 50.3], 'zoom' => 10])->assertOk()->json();
        $this->assertTrue($json['truncated']);
        $this->assertCount(10, $json['features']);
    }

    public function test_meta_lists_enabled_quick_areas(): void
    {
        AreaPreset::query()->where('name_en', 'California')->update(['enabled' => false]);

        $names = collect($this->getJson('/api/meta')->assertOk()->json('presets'))->pluck('name.en');

        $this->assertContains('Kyiv region', $names);
        $this->assertNotContains('California', $names);
    }

    public function test_only_admins_save_quick_areas(): void
    {
        $body = ['name' => 'Polissia', 'geometry' => self::KYIV_REGION];

        $this->postJson('/presets', $body)->assertUnauthorized();

        $this->actingAs(User::factory()->create())
            ->postJson('/presets', $body)
            ->assertCreated()
            ->assertJsonPath('name.uk', 'Polissia');
        $this->assertDatabaseHas('area_presets', ['name_en' => 'Polissia']);

        $this->postJson('/presets', ['name' => 'Polissia 2', 'name_uk' => 'Полісся', 'geometry' => self::KYIV_REGION])
            ->assertCreated()
            ->assertJsonPath('name.uk', 'Полісся');

        $this->postJson('/presets', ['name' => 'Bad', 'geometry' => ['type' => 'Polygon', 'coordinates' => [[[0, 0], [1, 1]]]]])
            ->assertUnprocessable();
    }
}
