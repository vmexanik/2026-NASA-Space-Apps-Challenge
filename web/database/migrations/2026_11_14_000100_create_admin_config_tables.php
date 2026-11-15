<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Configuration tables owned by the web app and edited in the Filament admin.
 * The parser will read them (how exactly is decided later), so keep names stable.
 */
return new class extends Migration
{
    public function up(): void
    {
        // Key/value application settings. Secret values are stored encrypted with APP_KEY.
        Schema::create('settings', function (Blueprint $table) {
            $table->string('key')->primary();
            $table->text('value')->nullable();
            $table->boolean('is_encrypted')->default(false);
            $table->timestamps();
        });

        // FIRMS products (MODIS_SP, VIIRS_SNPP_NRT, ...).
        Schema::create('data_sources', function (Blueprint $table) {
            $table->id();
            $table->string('code')->unique();
            $table->string('label');
            $table->string('sensor', 16);            // modis | viirs
            $table->string('satellite', 32)->nullable();
            $table->string('kind', 16);              // archive | nrt
            $table->date('available_from')->nullable();
            $table->boolean('enabled')->default(false);
            $table->unsignedSmallInteger('sort')->default(0);
            $table->timestamps();
        });

        // Coverage areas the parser downloads (bounding boxes, WGS84).
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

        // Ingest journal: written by the parser, shown read-only in the admin.
        Schema::create('ingest_runs', function (Blueprint $table) {
            $table->id();
            $table->foreignId('data_source_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('coverage_region_id')->nullable()->constrained()->nullOnDelete();
            $table->date('period_from')->nullable();
            $table->date('period_to')->nullable();
            $table->string('status', 16)->default('pending')->index(); // pending|running|success|failed
            $table->unsignedBigInteger('records_count')->default(0);
            $table->text('error')->nullable();
            $table->timestamp('started_at')->nullable();
            $table->timestamp('finished_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('ingest_runs');
        Schema::dropIfExists('coverage_regions');
        Schema::dropIfExists('data_sources');
        Schema::dropIfExists('settings');
    }
};
