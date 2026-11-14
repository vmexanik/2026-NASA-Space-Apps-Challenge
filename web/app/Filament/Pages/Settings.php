<?php

namespace App\Filament\Pages;

use App\Models\Setting;
use App\Services\FirmsKeyChecker;
use BackedEnum;
use Filament\Actions\Action;
use Filament\Forms\Components\CheckboxList;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Schemas\Components\Actions;
use Filament\Schemas\Components\EmbeddedSchema;
use Filament\Schemas\Components\Form;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;

class Settings extends Page
{
    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedCog6Tooth;

    protected static ?int $navigationSort = -1;

    protected static ?string $title = 'Settings';

    /** @var array<string, mixed> */
    public ?array $data = [];

    /** Keys handled by this form, in config/we_charge.php order. */
    private function keys(): array
    {
        return array_keys(config('we_charge.settings'));
    }

    public function mount(): void
    {
        $state = [];
        foreach ($this->keys() as $key) {
            // Never send the secret to the browser; an empty field means "keep current".
            $state[$key] = $key === 'firms_map_key' ? null : Setting::get($key);
        }
        $this->form->fill($state);
    }

    public function form(Schema $schema): Schema
    {
        $hasDbKey = filled(Setting::allValues()['firms_map_key'] ?? null);
        $hasEnvKey = filled(config('we_charge.firms.map_key'));

        return $schema
            ->statePath('data')
            ->components([
                Section::make('NASA FIRMS access')
                    ->description('MAP_KEY for the FIRMS API. Get one for free at firms.modaps.eosdis.nasa.gov/api/map_key.')
                    ->schema([
                        TextInput::make('firms_map_key')
                            ->label('MAP_KEY')
                            ->password()
                            ->revealable()
                            ->autocomplete('off')
                            ->placeholder(match (true) {
                                $hasDbKey => '•••••••• saved (leave empty to keep)',
                                $hasEnvKey => 'not set here, using FIRMS_MAP_KEY from .env',
                                default => 'not set',
                            })
                            ->helperText('Stored encrypted. If empty, FIRMS_MAP_KEY from .env is used.'),
                        Actions::make([
                            Action::make('checkKey')
                                ->label('Check key')
                                ->icon(Heroicon::OutlinedSignal)
                                ->color('gray')
                                ->action(fn () => $this->checkKey()),
                            Action::make('clearKey')
                                ->label('Remove saved key')
                                ->color('danger')
                                ->link()
                                ->requiresConfirmation()
                                ->visible($hasDbKey)
                                ->action(function () {
                                    Setting::put('firms_map_key', null);
                                    Notification::make()->title('Saved key removed')->success()->send();
                                }),
                        ]),
                    ]),

                Section::make('Quality filter & harmonization')
                    ->description('Read by the parser and the harmonization step.')
                    ->columns(2)
                    ->schema([
                        TextInput::make('modis_min_confidence')
                            ->label('MODIS min confidence (0–100)')
                            ->numeric()->integer()->minValue(0)->maxValue(100)->required(),
                        CheckboxList::make('viirs_confidence_levels')
                            ->label('VIIRS confidence levels kept')
                            ->options(['l' => 'low', 'n' => 'nominal', 'h' => 'high'])
                            ->columns(3)
                            ->required(),
                        Select::make('grid_step')
                            ->label('Grid step')
                            ->options(['0.1' => '0.1°', '0.25' => '0.25°', '0.5' => '0.5°', '1' => '1°'])
                            ->formatStateUsing(fn ($state) => $state === null ? null : rtrim(rtrim(number_format((float) $state, 2, '.', ''), '0'), '.'))
                            ->required(),
                        TextInput::make('harmonization_method_version')
                            ->label('Active harmonization method version')
                            ->required()
                            ->maxLength(32),
                    ]),

                Section::make('Updates')
                    ->schema([
                        TextInput::make('nrt_refresh_hours')
                            ->label('NRT refresh interval, hours')
                            ->numeric()->integer()->minValue(1)->maxValue(168)->required(),
                    ]),

                Section::make('Public API')
                    ->columns(3)
                    ->schema([
                        TextInput::make('api_rate_limit_per_minute')
                            ->label('Rate limit, requests/min per IP')
                            ->numeric()->integer()->minValue(1)->required(),
                        TextInput::make('csv_export_max_rows')
                            ->label('CSV export max rows')
                            ->numeric()->integer()->minValue(1000)->required(),
                        TextInput::make('max_aoi_area_km2')
                            ->label('Max AOI area, km²')
                            ->numeric()->integer()->minValue(1)->required(),
                    ]),
            ]);
    }

    public function content(Schema $schema): Schema
    {
        return $schema->components([
            Form::make([EmbeddedSchema::make('form')])
                ->id('form')
                ->livewireSubmitHandler('save')
                ->footer([
                    Actions::make([
                        Action::make('save')->label('Save')->submit('save')->keyBindings(['mod+s']),
                    ]),
                ]),
        ]);
    }

    public function save(): void
    {
        $state = $this->form->getState();

        foreach ($this->keys() as $key) {
            if (! array_key_exists($key, $state)) {
                continue;
            }
            if ($key === 'firms_map_key' && blank($state[$key])) {
                continue; // keep the current secret
            }
            Setting::put($key, is_string($state[$key]) ? trim($state[$key]) : $state[$key]);
        }

        $this->data['firms_map_key'] = null;

        Notification::make()->title('Settings saved')->success()->send();
    }

    public function checkKey(): void
    {
        // Check what was typed (not saved yet) or the effective key.
        $key = filled($this->data['firms_map_key'] ?? null)
            ? trim($this->data['firms_map_key'])
            : Setting::firmsMapKey();

        if (blank($key)) {
            Notification::make()->title('No MAP_KEY to check')->warning()->send();

            return;
        }

        $result = app(FirmsKeyChecker::class)->check($key);

        $notification = Notification::make()->title($result['ok'] ? 'MAP_KEY is valid' : 'MAP_KEY check failed')
            ->body($result['message']);

        $result['ok'] ? $notification->success()->send() : $notification->danger()->send();
    }
}
