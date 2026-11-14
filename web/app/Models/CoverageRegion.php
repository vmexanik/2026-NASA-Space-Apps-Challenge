<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class CoverageRegion extends Model
{
    protected $fillable = ['name', 'west', 'south', 'east', 'north', 'history_from', 'enabled'];

    protected function casts(): array
    {
        return [
            'west' => 'float',
            'south' => 'float',
            'east' => 'float',
            'north' => 'float',
            'history_from' => 'date',
            'enabled' => 'boolean',
        ];
    }

    /** FIRMS area string: west,south,east,north */
    public function firmsArea(): string
    {
        return implode(',', [$this->west, $this->south, $this->east, $this->north]);
    }
}
