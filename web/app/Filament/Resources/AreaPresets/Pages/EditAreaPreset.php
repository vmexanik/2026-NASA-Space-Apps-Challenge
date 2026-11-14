<?php

namespace App\Filament\Resources\AreaPresets\Pages;

use App\Filament\Resources\AreaPresets\AreaPresetResource;
use Filament\Actions\DeleteAction;
use Filament\Resources\Pages\EditRecord;

class EditAreaPreset extends EditRecord
{
    protected static string $resource = AreaPresetResource::class;

    protected function getHeaderActions(): array
    {
        return [DeleteAction::make()];
    }
}
