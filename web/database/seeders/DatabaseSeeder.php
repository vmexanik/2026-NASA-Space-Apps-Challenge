<?php

namespace Database\Seeders;

use App\Models\CoverageRegion;
use App\Models\DataSource;
use App\Models\User;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    /**
     * Idempotent: safe to run more than once.
     */
    public function run(): void
    {
        $admin = config('we_charge.admin');

        User::query()->firstOrCreate(
            ['email' => $admin['email']],
            ['name' => $admin['name'], 'password' => $admin['password']],
        );

        $sources = [
            ['MODIS_SP', 'MODIS standard (archive)', 'modis', 'Terra/Aqua', 'archive', '2000-11-01', true],
            ['MODIS_NRT', 'MODIS near real-time', 'modis', 'Terra/Aqua', 'nrt', null, true],
            ['VIIRS_SNPP_SP', 'VIIRS S-NPP standard (archive)', 'viirs', 'Suomi NPP', 'archive', '2012-01-20', true],
            ['VIIRS_SNPP_NRT', 'VIIRS S-NPP near real-time', 'viirs', 'Suomi NPP', 'nrt', null, true],
            ['VIIRS_NOAA20_SP', 'VIIRS NOAA-20 standard (archive)', 'viirs', 'NOAA-20', 'archive', '2018-04-01', true],
            ['VIIRS_NOAA20_NRT', 'VIIRS NOAA-20 near real-time', 'viirs', 'NOAA-20', 'nrt', null, true],
            ['VIIRS_NOAA21_NRT', 'VIIRS NOAA-21 near real-time', 'viirs', 'NOAA-21', 'nrt', null, false],
        ];

        foreach ($sources as $i => [$code, $label, $sensor, $satellite, $kind, $from, $enabled]) {
            DataSource::query()->firstOrCreate(['code' => $code], [
                'label' => $label,
                'sensor' => $sensor,
                'satellite' => $satellite,
                'kind' => $kind,
                'available_from' => $from,
                'enabled' => $enabled,
                'sort' => $i,
            ]);
        }

        CoverageRegion::query()->firstOrCreate(['name' => 'Ukraine'], [
            'west' => 22.0, 'south' => 44.0, 'east' => 40.5, 'north' => 52.5,
            'history_from' => '2000-11-01',
            'enabled' => true,
        ]);
    }
}
