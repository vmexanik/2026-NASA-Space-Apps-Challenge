<?php

namespace App\Filament\Resources\DataSources\Tables;

use Filament\Actions\EditAction;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;

class DataSourcesTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->defaultSort('sort')
            ->reorderable('sort')
            ->columns([
                TextColumn::make('code')
                    ->fontFamily('mono')
                    ->searchable(),
                TextColumn::make('label')
                    ->searchable(),
                TextColumn::make('sensor')
                    ->badge()
                    ->formatStateUsing(fn (string $state) => strtoupper($state)),
                TextColumn::make('satellite'),
                TextColumn::make('kind')
                    ->badge()
                    ->color(fn (string $state) => $state === 'nrt' ? 'warning' : 'gray'),
                TextColumn::make('available_from')
                    ->date()
                    ->placeholder('—'),
            ])
            ->filters([
                SelectFilter::make('sensor')->options(['modis' => 'MODIS', 'viirs' => 'VIIRS']),
                SelectFilter::make('kind')->options(['archive' => 'Archive', 'nrt' => 'NRT']),
            ])
            ->recordActions([
                EditAction::make(),
            ]);
    }
}
