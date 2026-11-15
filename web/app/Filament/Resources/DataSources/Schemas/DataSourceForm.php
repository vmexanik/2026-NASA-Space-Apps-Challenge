<?php

namespace App\Filament\Resources\DataSources\Schemas;

use Filament\Forms\Components\DatePicker;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Schema;

class DataSourceForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema
            ->columns(2)
            ->components([
                TextInput::make('code')
                    ->label('FIRMS product code')
                    ->helperText('As used by the FIRMS API, e.g. VIIRS_SNPP_NRT')
                    ->required()
                    ->maxLength(64)
                    ->unique(ignoreRecord: true),
                TextInput::make('label')
                    ->required()
                    ->maxLength(255),
                Select::make('sensor')
                    ->options(['modis' => 'MODIS', 'viirs' => 'VIIRS'])
                    ->required(),
                TextInput::make('satellite')
                    ->maxLength(32),
                Select::make('kind')
                    ->options(['archive' => 'Archive (standard processing)', 'nrt' => 'Near real-time'])
                    ->required(),
                DatePicker::make('available_from'),
                TextInput::make('sort')
                    ->numeric()
                    ->integer()
                    ->default(0)
                    ->required(),
            ]);
    }
}
