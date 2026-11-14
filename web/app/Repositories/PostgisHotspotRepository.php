<?php

namespace App\Repositories;

use App\Contracts\HotspotRepository;
use App\Exceptions\DataUnavailable;
use App\Support\Aoi;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;

/**
 * Reads the firms schema through its functions (docs/database/README.md, section 4).
 * The schema is created by parser/firmsdb, never by Laravel migrations.
 */
final class PostgisHotspotRepository implements HotspotRepository
{
    private const CACHE_TTL = 86400;

    /** @var array<string, mixed> per-request memo */
    private array $memo = [];

    public function monthlyCounts(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to): array
    {
        $version = $this->version();
        $key = implode(':', ['firms.monthly', $version, $this->builtAt(), $aoi->fingerprint(), $from->toDateString(), $to->toDateString()]);

        return Cache::remember($key, self::CACHE_TTL, function () use ($aoi, $from, $to, $version) {
            $rows = DB::select(
                'select * from firms.monthly_counts(?, ?::date, ?::date, ?)',
                [$this->aoiJson($aoi), $from->toDateString(), $to->toDateString(), $version],
            );

            return array_map(fn ($r) => [
                'year' => (int) $r->year,
                'month' => (int) $r->month,
                'count' => (int) $r->count,
                'count_raw' => (int) $r->count_raw,
                'source' => $r->source,
                'partial' => (bool) $r->partial,
                'count_error' => $r->count_error === null ? null : (int) $r->count_error,
                'incomplete' => (bool) $r->incomplete,
            ], $rows);
        });
    }

    public function hotspots(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to, int $maxRows): iterable
    {
        $version = $this->version();

        DB::beginTransaction();
        try {
            DB::statement(
                'declare hs no scroll cursor for select * from firms.hotspots_in(?, ?::date, ?::date, ?, ?)',
                [$this->aoiJson($aoi), $from->toDateString(), $to->toDateString(), $version, $maxRows],
            );
            while ($rows = DB::select('fetch 5000 from hs')) {
                foreach ($rows as $row) {
                    yield (array) $row;
                }
            }
        } finally {
            DB::rollBack();
        }
    }

    public function hotspotCount(Aoi $aoi, CarbonImmutable $from, CarbonImmutable $to, int $limit): int
    {
        return (int) DB::scalar(
            'select count(*) from firms.hotspots_in(?, ?::date, ?::date, ?, ?)',
            [$this->aoiJson($aoi), $from->toDateString(), $to->toDateString(), $this->version(), $limit],
        );
    }

    public function mapFeatures(float $west, float $south, float $east, float $north, int $zoom,
        CarbonImmutable $from, CarbonImmutable $to, int $maxPoints): array
    {
        $rows = DB::select(
            'select * from firms.map_features(?, ?, ?, ?, ?, ?::date, ?::date, ?, ?)',
            [$west, $south, $east, $north, $zoom, $from->toDateString(), $to->toDateString(), $this->version(), $maxPoints],
        );

        return array_map(fn ($r) => (array) $r, $rows);
    }

    public function coverage(): array
    {
        $version = $this->version();

        return $this->memo["coverage:$version"] ??= (function () use ($version) {
            $row = DB::selectOne('select d_from, d_to from firms.coverage(?)', [$version]);
            if ($row === null || $row->d_from === null) {
                throw new DataUnavailable("Harmonization method version '{$version}' has no data in the firms schema.");
            }

            return ['from' => CarbonImmutable::parse($row->d_from), 'to' => CarbonImmutable::parse($row->d_to)];
        })();
    }

    public function method(): array
    {
        $version = $this->rawVersion();

        return $this->memo["method:$version"] ??= (function () use ($version) {
            $json = DB::scalar('select firms.method_info(?)', [$version]);
            if ($json === null) {
                throw new DataUnavailable("Harmonization method version '{$version}' is not in the firms schema.");
            }

            return json_decode($json, true);
        })();
    }

    public function dataset(): ?array
    {
        if (! array_key_exists('dataset', $this->memo)) {
            $json = DB::scalar('select firms.dataset_info()');
            $this->memo['dataset'] = $json === null ? null : json_decode($json, true);
        }

        return $this->memo['dataset'];
    }

    // --- internals -----------------------------------------------------------------

    /**
     * The version, checked once per request: the firms functions raise a bare SQL error for an unknown version,
     * and this turns it into DataUnavailable (503) before any of them runs.
     */
    private function version(): string
    {
        $this->method();

        return $this->rawVersion();
    }

    private function rawVersion(): string
    {
        return (string) config('we_charge.harmonization.version');
    }

    /** restore.sh rewrites built_at, so a new package invalidates cached series by itself. */
    private function builtAt(): string
    {
        return (string) ($this->dataset()['built_at'] ?? 'none');
    }

    private function aoiJson(Aoi $aoi): string
    {
        return json_encode($aoi->toGeoJson());
    }
}
