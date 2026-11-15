<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class DataSource extends Model
{
    protected $fillable = ['code', 'label', 'sensor', 'satellite', 'kind', 'available_from', 'sort'];

    protected function casts(): array
    {
        return [
            'available_from' => 'date:Y-m-d',
        ];
    }

    public function ingestRuns(): HasMany
    {
        return $this->hasMany(IngestRun::class);
    }
}
