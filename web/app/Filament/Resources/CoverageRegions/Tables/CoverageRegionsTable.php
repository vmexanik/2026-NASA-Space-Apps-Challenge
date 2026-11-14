<?php

namespace App\Filament\Resources\CoverageRegions\Tables;

use App\Models\CoverageRegion;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Columns\ToggleColumn;
use Filament\Tables\Table;

class CoverageRegionsTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->columns([
                TextColumn::make('name')
                    ->searchable()
                    ->sortable(),
                TextColumn::make('bbox')
                    ->label('Area (W,S,E,N)')
                    ->fontFamily('mono')
                    ->state(fn (CoverageRegion $record) => $record->firmsArea())
                    ->copyable(),
                TextColumn::make('history_from')
                    ->date()
                    ->placeholder('—'),
                ToggleColumn::make('enabled'),
            ])
            ->recordActions([
                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make(),
                ]),
            ]);
    }
}
