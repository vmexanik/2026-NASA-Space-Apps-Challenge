<?php

return [

    'firms' => [
        // Fallback when no key is saved in the admin.
        'map_key' => env('FIRMS_MAP_KEY'),
        'status_url' => 'https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/',
    ],

    // Initial admin created by the seeder. Change the password after first login.
    'admin' => [
        'name' => env('ADMIN_NAME', 'admin'),
        'email' => env('ADMIN_EMAIL', 'admin@we-charge.test'),
        'password' => env('ADMIN_PASSWORD', 'admin'),
    ],

    // Most map objects one /api/map response carries (docs/database/README.md, section 5).
    'map_max_points' => 20000,

    // The one harmonization method (docs/harmonization/decisions/harmonization.md, approach 15, D29).
    // version is its key in the firms schema; name is what people see.
    'harmonization' => [
        'version' => 'v1-2026-11-14',
        'name' => [
            'en' => 'Area-and-month adjustment method',
            'uk' => 'Метод приведення за площею та місяцем',
        ],
    ],

    // Settings editable in the admin (Setting::get). type: string|int|float|bool|array.
    'settings' => [
        'firms_map_key' => ['type' => 'string', 'secret' => true, 'default' => null],
        'nrt_refresh_hours' => ['type' => 'int', 'default' => 3],
        'api_rate_limit_per_minute' => ['type' => 'int', 'default' => 60],
        'csv_export_max_rows' => ['type' => 'int', 'default' => 100000],
        'max_aoi_area_km2' => ['type' => 'int', 'default' => 5000000],
    ],

];
