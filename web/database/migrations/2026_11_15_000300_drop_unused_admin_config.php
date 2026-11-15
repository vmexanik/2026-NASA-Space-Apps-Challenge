<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * The data scripts in parser/ read none of the admin configuration (TZ.md, open question 8), so the parts that only
 * pretended to steer them go: the coverage regions, the region of a journal row and the "enabled" switch of a product.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('ingest_runs', function (Blueprint $table) {
            $table->dropConstrainedForeignId('coverage_region_id');
        });
        Schema::dropIfExists('coverage_regions');
        Schema::table('data_sources', function (Blueprint $table) {
            $table->dropColumn('enabled');
        });
    }

    public function down(): void
    {
        Schema::table('data_sources', function (Blueprint $table) {
            $table->boolean('enabled')->default(false);
        });
        Schema::create('coverage_regions', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->decimal('west', 9, 5);
            $table->decimal('south', 8, 5);
            $table->decimal('east', 9, 5);
            $table->decimal('north', 8, 5);
            $table->date('history_from')->nullable();
            $table->boolean('enabled')->default(true);
            $table->timestamps();
        });
        Schema::table('ingest_runs', function (Blueprint $table) {
            $table->foreignId('coverage_region_id')->nullable()->after('data_source_id')->constrained()->nullOnDelete();
        });
    }
};
