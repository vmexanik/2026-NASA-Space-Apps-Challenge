<?php

namespace Tests\Feature;

use App\Filament\Pages\Settings;
use App\Models\Setting;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Livewire\Livewire;
use Tests\TestCase;

class AdminPanelTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        $this->seed();
    }

    public function test_seeder_creates_default_admin_and_sources(): void
    {
        $this->assertDatabaseHas('users', ['email' => 'admin@we-charge.test']);
        $this->assertDatabaseHas('data_sources', ['code' => 'MODIS_SP']);
        $this->assertDatabaseHas('data_sources', ['code' => 'VIIRS_SNPP_SP']);

        // Idempotent.
        $this->seed();
        $this->assertSame(1, User::query()->count());
    }

    public function test_guest_is_redirected_to_login(): void
    {
        $this->get('/admin')->assertRedirect('/admin/login');
    }

    public function test_admin_pages_render(): void
    {
        $this->actingAs(User::query()->first());

        foreach (['/admin', '/admin/settings', '/admin/data-sources', '/admin/area-presets', '/admin/area-presets/1/edit', '/admin/ingest-runs', '/admin/users'] as $url) {
            $this->get($url)->assertOk();
        }
    }

    public function test_settings_save_encrypts_map_key_and_keeps_it_when_blank(): void
    {
        $this->actingAs(User::query()->first());

        Livewire::test(Settings::class)
            ->set('data.firms_map_key', 'abc123secret')
            ->set('data.csv_export_max_rows', 50000)
            ->call('save')
            ->assertHasNoErrors();

        $raw = DB::table('settings')->where('key', 'firms_map_key')->value('value');
        $this->assertNotSame('abc123secret', $raw);
        $this->assertSame('abc123secret', Setting::firmsMapKey());
        $this->assertSame(50000, Setting::get('csv_export_max_rows'));

        // Saving again with an empty key field keeps the stored key.
        Livewire::test(Settings::class)
            ->assertSet('data.firms_map_key', null)
            ->call('save')
            ->assertHasNoErrors();

        $this->assertSame('abc123secret', Setting::firmsMapKey());
    }

    public function test_map_key_falls_back_to_env(): void
    {
        config(['we_charge.firms.map_key' => 'from-env']);

        $this->assertSame('from-env', Setting::firmsMapKey());
    }

    public function test_check_key_reports_quota(): void
    {
        Http::fake(['firms.modaps.eosdis.nasa.gov/*' => Http::response([
            'transaction_limit' => 5000, 'current_transactions' => 12, 'transaction_interval' => '10 minutes',
        ])]);

        $this->actingAs(User::query()->first());

        Livewire::test(Settings::class)
            ->set('data.firms_map_key', 'abc')
            ->call('checkKey')
            ->assertNotified('MAP_KEY is valid');
    }
}
