<?php

namespace App\Filament\Resources\IngestRuns\Schemas;

use App\Filament\Resources\IngestRuns\Tables\IngestRunsTable;
use Filament\Infolists\Components\TextEntry;
use Filament\Schemas\Schema;

class IngestRunInfolist
{
    public static function configure(Schema $schema): Schema
    {
        return $schema
            ->columns(3)
            ->components([
                TextEntry::make('dataSource.code')->label('Source')->placeholder('—'),
                TextEntry::make('coverageRegion.name')->label('Region')->placeholder('—'),
                TextEntry::make('status')->badge()->color(fn (string $state) => IngestRunsTable::statusColor($state)),
                TextEntry::make('period_from')->date()->placeholder('—'),
                TextEntry::make('period_to')->date()->placeholder('—'),
                TextEntry::make('records_count')->label('Records')->numeric(),
                TextEntry::make('started_at')->dateTime()->placeholder('—'),
                TextEntry::make('finished_at')->dateTime()->placeholder('—'),
                TextEntry::make('created_at')->dateTime(),
                TextEntry::make('error')
                    ->placeholder('No error')
                    ->fontFamily('mono')
                    ->columnSpanFull(),
            ]);
    }
}
