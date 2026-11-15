<?php

namespace App\Filament\Resources\Users\Tables;

use App\Models\User;
use Filament\Actions\DeleteAction;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;

class UsersTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->columns([
                TextColumn::make('name')
                    ->searchable(),
                TextColumn::make('email')
                    ->searchable(),
                TextColumn::make('created_at')
                    ->dateTime()
                    ->sortable(),
            ])
            ->recordActions([
                EditAction::make(),
                // Keep at least one admin and never delete yourself.
                DeleteAction::make()
                    ->hidden(fn (User $record) => $record->is(auth()->user()) || User::query()->count() <= 1),
            ]);
    }
}
