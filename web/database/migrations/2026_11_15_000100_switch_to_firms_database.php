<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;

/**
 * Moves an installed app onto the firms database (docs/database/README.md, section 6):
 *  - NOAA-20 carries the series after Suomi NPP stopped (2026-11-02), so its sources are enabled;
 *  - settings that no longer exist: grid_step (the database counts exactly for any area), the quality
 *    filter and the method version (there is one method, built into the database).
 */
return new class extends Migration
{
    public function up(): void
    {
        DB::table('data_sources')->whereIn('code', ['VIIRS_NOAA20_SP', 'VIIRS_NOAA20_NRT'])->update(['enabled' => true]);

        DB::table('settings')
            ->whereIn('key', ['grid_step', 'modis_min_confidence', 'viirs_confidence_levels', 'harmonization_method_version'])
            ->delete();

        Cache::forget('settings.all');
    }

    public function down(): void
    {
        // Data change only; nothing to undo.
    }
};
