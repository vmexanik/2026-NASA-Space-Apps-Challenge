<?php

namespace App\Filament\Resources\CoverageRegions;

use App\Filament\Resources\CoverageRegions\Pages\CreateCoverageRegion;
use App\Filament\Resources\CoverageRegions\Pages\EditCoverageRegion;
use App\Filament\Resources\CoverageRegions\Pages\ListCoverageRegions;
use App\Filament\Resources\CoverageRegions\Schemas\CoverageRegionForm;
use App\Filament\Resources\CoverageRegions\Tables\CoverageRegionsTable;
use App\Models\CoverageRegion;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;

class CoverageRegionResource extends Resource
{
    protected static ?string $model = CoverageRegion::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedGlobeEuropeAfrica;

    protected static string|\UnitEnum|null $navigationGroup = 'Data collection';

    protected static ?int $navigationSort = 2;

    protected static ?string $recordTitleAttribute = 'name';

    public static function form(Schema $schema): Schema
    {
        return CoverageRegionForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return CoverageRegionsTable::configure($table);
    }

    public static function getRelations(): array
    {
        return [
            //
        ];
    }

    public static function getPages(): array
    {
        return [
            'index' => ListCoverageRegions::route('/'),
            'create' => CreateCoverageRegion::route('/create'),
            'edit' => EditCoverageRegion::route('/{record}/edit'),
        ];
    }
}
