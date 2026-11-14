<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class IngestRun extends Model
{
    public const STATUSES = ['pending', 'running', 'success', 'failed'];

    protected $fillable = [
        'data_source_id', 'coverage_region_id', 'period_from', 'period_to',
        'status', 'records_count', 'error', 'started_at', 'finished_at',
    ];

    protected function casts(): array
    {
        return [
            'period_from' => 'date',
            'period_to' => 'date',
            'started_at' => 'datetime',
            'finished_at' => 'datetime',
        ];
    }

    public function dataSource(): BelongsTo
    {
        return $this->belongsTo(DataSource::class);
    }

    public function coverageRegion(): BelongsTo
    {
        return $this->belongsTo(CoverageRegion::class);
    }
}
