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

    // Where the public API gets data: "fake" (synthetic demo data) until the real schema exists.
    'data_driver' => env('WE_CHARGE_DATA_DRIVER', 'fake'),

    // Settings editable in the admin (Setting::get). type: string|int|float|bool|array.
    'settings' => [
        'firms_map_key' => ['type' => 'string', 'secret' => true, 'default' => null],
        'modis_min_confidence' => ['type' => 'int', 'default' => 30],
        'viirs_confidence_levels' => ['type' => 'array', 'default' => ['n', 'h']],
        'grid_step' => ['type' => 'float', 'default' => 0.25],
        'nrt_refresh_hours' => ['type' => 'int', 'default' => 3],
        'harmonization_method_version' => ['type' => 'string', 'default' => 'v0-demo'],
        'api_rate_limit_per_minute' => ['type' => 'int', 'default' => 60],
        'csv_export_max_rows' => ['type' => 'int', 'default' => 100000],
        'max_aoi_area_km2' => ['type' => 'int', 'default' => 5000000],
    ],

];
