<?php

namespace App\Filament\Resources\CoverageRegions\Schemas;

use Filament\Forms\Components\DatePicker;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

class CoverageRegionForm
{
    public static function configure(Schema $schema): Schema
    {
        $lon = fn (string $name, string $label) => TextInput::make($name)->label($label)
            ->numeric()->minValue(-180)->maxValue(180)->step(0.00001)->suffix('°')->required();
        $lat = fn (string $name, string $label) => TextInput::make($name)->label($label)
            ->numeric()->minValue(-90)->maxValue(90)->step(0.00001)->suffix('°')->required();

        return $schema
            ->columns(2)
            ->components([
                TextInput::make('name')->required()->maxLength(255),
                DatePicker::make('history_from')
                    ->label('Download history from')
                    ->minDate('2000-11-01')
                    ->helperText('MODIS archive starts 2000-11-01.'),
                Section::make('Bounding box (WGS84)')
                    ->description('Same order as the FIRMS area parameter: west, south, east, north.')
                    ->columns(4)
                    ->columnSpanFull()
                    ->schema([
                        $lon('west', 'West (min lon)'),
                        $lat('south', 'South (min lat)'),
                        $lon('east', 'East (max lon)')
                            ->gt('west')
                            ->validationMessages(['gt' => 'East must be greater than west.']),
                        $lat('north', 'North (max lat)')
                            ->gt('south')
                            ->validationMessages(['gt' => 'North must be greater than south.']),
                    ]),
                Toggle::make('enabled')
                    ->default(true)
                    ->helperText('The parser downloads only enabled regions.'),
            ]);
    }
}
