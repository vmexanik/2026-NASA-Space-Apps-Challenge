<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Crypt;

/**
 * Key/value settings edited in the admin. Use Setting::get()/Setting::put().
 * Defaults and which keys are secret live in config/we_charge.php.
 */
class Setting extends Model
{
    protected $primaryKey = 'key';

    public $incrementing = false;

    protected $keyType = 'string';

    protected $fillable = ['key', 'value', 'is_encrypted'];

    protected $hidden = ['value'];

    protected function casts(): array
    {
        return ['is_encrypted' => 'boolean'];
    }

    private const CACHE_KEY = 'settings.all';

    /** @return array<string, string|null> decrypted values keyed by setting key */
    public static function allValues(): array
    {
        return Cache::rememberForever(self::CACHE_KEY, function () {
            return static::query()->get()->mapWithKeys(fn (self $s) => [
                $s->key => $s->is_encrypted && $s->value !== null ? Crypt::decryptString($s->value) : $s->value,
            ])->all();
        });
    }

    public static function get(string $key, mixed $default = null): mixed
    {
        $value = static::allValues()[$key] ?? null;

        if ($value === null || $value === '') {
            return $default ?? config("we_charge.settings.$key.default");
        }

        return match (config("we_charge.settings.$key.type")) {
            'int' => (int) $value,
            'float' => (float) $value,
            'bool' => filter_var($value, FILTER_VALIDATE_BOOL),
            'array' => json_decode($value, true) ?? [],
            default => $value,
        };
    }

    public static function put(string $key, mixed $value): void
    {
        $secret = (bool) config("we_charge.settings.$key.secret", false);

        if (is_array($value)) {
            $value = json_encode(array_values($value));
        } elseif (is_bool($value)) {
            $value = $value ? '1' : '0';
        } elseif ($value !== null) {
            $value = (string) $value;
        }

        static::query()->updateOrCreate(['key' => $key], [
            'value' => $secret && $value !== null && $value !== '' ? Crypt::encryptString($value) : $value,
            'is_encrypted' => $secret,
        ]);

        Cache::forget(self::CACHE_KEY);
    }

    /** FIRMS MAP_KEY: admin value first, then FIRMS_MAP_KEY from .env. */
    public static function firmsMapKey(): ?string
    {
        $key = static::allValues()['firms_map_key'] ?? null;

        return $key !== null && $key !== '' ? $key : config('we_charge.firms.map_key');
    }
}
