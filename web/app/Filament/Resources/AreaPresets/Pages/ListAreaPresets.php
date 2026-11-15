<?php

namespace App\Filament\Resources\AreaPresets\Pages;

use App\Filament\Resources\AreaPresets\AreaPresetResource;
use Filament\Actions\Action;
use Filament\Resources\Pages\ListRecords;

class ListAreaPresets extends ListRecords
{
    protected static string $resource = AreaPresetResource::class;

    protected ?string $subheading = 'To add one, draw the area on the public map and press "Save as quick area" (shown while you are signed in here). Drag rows to change the order.';

    protected function getHeaderActions(): array
    {
        return [
            Action::make('map')->label('Open the map')->url('/', shouldOpenInNewTab: true),
        ];
    }
}
