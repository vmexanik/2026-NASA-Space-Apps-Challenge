<?php

namespace App\Filament\Resources\CoverageRegions\Pages;

use App\Filament\Resources\CoverageRegions\CoverageRegionResource;
use Filament\Actions\DeleteAction;
use Filament\Resources\Pages\EditRecord;

class EditCoverageRegion extends EditRecord
{
    protected static string $resource = CoverageRegionResource::class;

    protected function getHeaderActions(): array
    {
        return [
            DeleteAction::make(),
        ];
    }
}
