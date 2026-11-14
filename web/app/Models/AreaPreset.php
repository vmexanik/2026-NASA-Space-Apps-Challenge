<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

/** A quick area of the public map: a shape saved by an admin, picked in one click. */
class AreaPreset extends Model
{
    protected $fillable = ['name_en', 'name_uk', 'geometry', 'sort', 'enabled'];

    protected function casts(): array
    {
        return ['geometry' => 'array', 'enabled' => 'boolean', 'sort' => 'integer'];
    }

    /** @return array{id: int, name: array{en: string, uk: string}, geometry: array} */
    public function toPublic(): array
    {
        return [
            'id' => $this->id,
            'name' => ['en' => $this->name_en, 'uk' => $this->name_uk ?: $this->name_en],
            'geometry' => $this->geometry,
        ];
    }
}
