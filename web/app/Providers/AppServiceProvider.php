<?php

namespace App\Providers;

use App\Contracts\HotspotRepository;
use App\Models\Setting;
use App\Repositories\PostgisHotspotRepository;
use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\ServiceProvider;
use Throwable;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        $this->app->singleton(HotspotRepository::class, PostgisHotspotRepository::class);
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        RateLimiter::for('public-api', function (Request $request) {
            try {
                $perMinute = (int) Setting::get('api_rate_limit_per_minute');
            } catch (Throwable) {
                $perMinute = 60; // settings table not migrated yet
            }

            return Limit::perMinute(max(1, $perMinute))->by($request->ip());
        });
    }
}
