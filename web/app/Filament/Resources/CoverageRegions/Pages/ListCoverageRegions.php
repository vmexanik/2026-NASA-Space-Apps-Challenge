<?php

namespace App\Filament\Resources\CoverageRegions\Pages;

use App\Filament\Resources\CoverageRegions\CoverageRegionResource;
use Filament\Actions\CreateAction;
use Filament\Resources\Pages\ListRecords;

class ListCoverageRegions extends ListRecords
{
    protected static string $resource = CoverageRegionResource::class;

    protected function getHeaderActions(): array
    {
        return [
            CreateAction::make(),
        ];
    }
}
