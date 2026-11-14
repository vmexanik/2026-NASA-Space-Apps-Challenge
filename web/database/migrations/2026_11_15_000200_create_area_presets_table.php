<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Quick areas of the public map: shapes an admin saved from the map, picked in one click.
 * Starts with the boxes that used to be hard-coded in the SPA.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('area_presets', function (Blueprint $table) {
            $table->id();
            $table->string('name_en');
            $table->string('name_uk')->nullable();
            $table->json('geometry'); // GeoJSON Polygon, [lon, lat]
            $table->unsignedInteger('sort')->default(0);
            $table->boolean('enabled')->default(true);
            $table->timestamps();
        });

        $presets = [
            ['Kyiv region', 'Київщина', [29.2, 49.2, 32.2, 51.6]],
            ['Ukraine', 'Україна', [22.1, 44.3, 40.2, 52.4]],
            ['California', 'Каліфорнія', [-124.5, 32.5, -114.1, 42.0]],
            ['Rondônia, BR', 'Рондонія, Бразилія', [-66.8, -13.7, -59.8, -7.9]],
            ['New South Wales', 'Новий Південний Уельс', [141.0, -37.5, 153.6, -28.2]],
        ];
        $now = now();
        foreach ($presets as $i => [$en, $uk, [$w, $s, $e, $n]]) {
            DB::table('area_presets')->insert([
                'name_en' => $en,
                'name_uk' => $uk,
                'geometry' => json_encode(['type' => 'Polygon', 'coordinates' => [[[$w, $s], [$e, $s], [$e, $n], [$w, $n], [$w, $s]]]]),
                'sort' => $i,
                'enabled' => true,
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('area_presets');
    }
};
