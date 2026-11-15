<?php

namespace App\Filament\Resources\AreaPresets;

use App\Filament\Resources\AreaPresets\Pages\EditAreaPreset;
use App\Filament\Resources\AreaPresets\Pages\ListAreaPresets;
use App\Models\AreaPreset;
use App\Support\Aoi;
use BackedEnum;
use Closure;
use Filament\Actions\DeleteAction;
use Filament\Actions\EditAction;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Columns\ToggleColumn;
use Filament\Tables\Table;
use InvalidArgumentException;

/**
 * Quick areas of the public map. New ones are saved from the map itself (draw a shape while
 * signed in to the admin, then "Save as quick area"); here they are renamed, ordered and hidden.
 */
class AreaPresetResource extends Resource
{
    protected static ?string $model = AreaPreset::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedMapPin;

    protected static ?string $navigationLabel = 'Quick areas';

    protected static ?string $modelLabel = 'quick area';

    protected static ?string $recordTitleAttribute = 'name_en';

    public static function form(Schema $schema): Schema
    {
        return $schema->columns(2)->components([
            TextInput::make('name_en')->label('Name (English)')->required()->maxLength(80),
            TextInput::make('name_uk')->label('Name (Ukrainian)')->maxLength(80)->placeholder('Same as English'),
            Toggle::make('enabled')->label('Shown on the map')->default(true),
            TextInput::make('sort')->numeric()->integer()->default(0),
            Textarea::make('geometry')
                ->label('Shape (GeoJSON Polygon, [lon, lat])')
                ->helperText('Easier to redraw on the public map and save again.')
                ->rows(4)
                ->columnSpanFull()
                ->formatStateUsing(fn ($state) => is_array($state) ? json_encode($state) : $state)
                ->dehydrateStateUsing(fn ($state) => json_decode($state, true))
                ->rule(fn () => function (string $attribute, mixed $value, Closure $fail) {
                    try {
                        Aoi::fromGeoJson(json_decode((string) $value, true) ?? []);
                    } catch (InvalidArgumentException $e) {
                        $fail($e->getMessage());
                    }
                })
                ->required(),
        ]);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->defaultSort('sort')
            ->reorderable('sort')
            ->columns([
                TextColumn::make('name_en')->label('Name')->searchable(),
                TextColumn::make('name_uk')->label('Ukrainian')->placeholder('—'),
                TextColumn::make('area')
                    ->label('Area, km²')
                    ->state(fn (AreaPreset $record) => number_format(Aoi::fromGeoJson($record->geometry)->areaKm2())),
                ToggleColumn::make('enabled')->label('Shown'),
            ])
            ->recordActions([EditAction::make(), DeleteAction::make()]);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListAreaPresets::route('/'),
            'edit' => EditAreaPreset::route('/{record}/edit'),
        ];
    }
}
