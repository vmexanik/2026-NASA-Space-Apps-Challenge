<?php

namespace App\Filament\Resources\IngestRuns;

use App\Filament\Resources\IngestRuns\Pages\ListIngestRuns;
use App\Filament\Resources\IngestRuns\Pages\ViewIngestRun;
use App\Filament\Resources\IngestRuns\Schemas\IngestRunInfolist;
use App\Filament\Resources\IngestRuns\Tables\IngestRunsTable;
use App\Models\IngestRun;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;

/**
 * Read-only journal. Rows are written by the parser.
 */
class IngestRunResource extends Resource
{
    protected static ?string $model = IngestRun::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedQueueList;

    protected static string|\UnitEnum|null $navigationGroup = 'Data collection';

    protected static ?int $navigationSort = 3;

    protected static ?string $navigationLabel = 'Ingest runs';

    public static function canCreate(): bool
    {
        return false;
    }

    public static function infolist(Schema $schema): Schema
    {
        return IngestRunInfolist::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return IngestRunsTable::configure($table);
    }

    public static function getNavigationBadge(): ?string
    {
        $failed = IngestRun::query()->where('status', 'failed')->count();

        return $failed > 0 ? (string) $failed : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'danger';
    }

    public static function getNavigationBadgeTooltip(): ?string
    {
        return 'Failed runs';
    }

    public static function getPages(): array
    {
        return [
            'index' => ListIngestRuns::route('/'),
            'view' => ViewIngestRun::route('/{record}'),
        ];
    }
}
