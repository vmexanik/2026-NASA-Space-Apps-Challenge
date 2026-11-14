<?php

namespace App\Filament\Resources\IngestRuns\Tables;

use App\Models\IngestRun;
use Filament\Actions\ViewAction;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;

class IngestRunsTable
{
    public static function statusColor(string $state): string
    {
        return match ($state) {
            'success' => 'success',
            'failed' => 'danger',
            'running' => 'info',
            default => 'gray',
        };
    }

    public static function configure(Table $table): Table
    {
        return $table
            ->defaultSort('created_at', 'desc')
            ->emptyStateHeading('No ingest runs yet')
            ->emptyStateDescription('The parser writes a row here for every download it performs.')
            ->columns([
                TextColumn::make('created_at')
                    ->label('Created')
                    ->dateTime()
                    ->sortable(),
                TextColumn::make('dataSource.code')
                    ->label('Source')
                    ->fontFamily('mono')
                    ->placeholder('—'),
                TextColumn::make('coverageRegion.name')
                    ->label('Region')
                    ->placeholder('—'),
                TextColumn::make('period_from')
                    ->label('Period')
                    ->formatStateUsing(fn (IngestRun $record) => trim(
                        ($record->period_from?->toDateString() ?? '…').' → '.($record->period_to?->toDateString() ?? '…'),
                    )),
                TextColumn::make('status')
                    ->badge()
                    ->color(fn (string $state) => self::statusColor($state)),
                TextColumn::make('records_count')
                    ->label('Records')
                    ->numeric()
                    ->alignEnd(),
                TextColumn::make('duration')
                    ->state(fn (IngestRun $record) => $record->started_at && $record->finished_at
                        ? $record->started_at->diffForHumans($record->finished_at, true)
                        : null)
                    ->placeholder('—'),
                TextColumn::make('error')
                    ->limit(60)
                    ->placeholder('—')
                    ->toggleable(),
            ])
            ->filters([
                SelectFilter::make('status')
                    ->options(array_combine(IngestRun::STATUSES, array_map('ucfirst', IngestRun::STATUSES))),
                SelectFilter::make('data_source_id')
                    ->label('Source')
                    ->relationship('dataSource', 'code'),
            ])
            ->recordActions([
                ViewAction::make(),
            ]);
    }
}
