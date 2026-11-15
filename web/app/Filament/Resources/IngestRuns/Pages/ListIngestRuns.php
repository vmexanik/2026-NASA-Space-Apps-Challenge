<?php

namespace App\Filament\Resources\IngestRuns\Pages;

use App\Filament\Resources\IngestRuns\IngestRunResource;
use Filament\Resources\Pages\ListRecords;

class ListIngestRuns extends ListRecords
{
    protected static string $resource = IngestRunResource::class;

    protected function getHeaderActions(): array
    {
        return [
        ];
    }
}
