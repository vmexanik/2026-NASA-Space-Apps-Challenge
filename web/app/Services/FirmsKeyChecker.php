<?php

namespace App\Services;

use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Http;

/**
 * Calls FIRMS mapkey_status to validate a MAP_KEY and show the remaining quota.
 */
class FirmsKeyChecker
{
    /** @return array{ok: bool, message: string, data: array<string, mixed>|null} */
    public function check(string $key): array
    {
        try {
            $response = Http::timeout(10)
                ->acceptJson()
                ->get(config('we_charge.firms.status_url'), ['MAP_KEY' => $key]);
        } catch (ConnectionException $e) {
            return ['ok' => false, 'message' => 'FIRMS is not reachable: '.$e->getMessage(), 'data' => null];
        }

        $data = $response->json();

        if (! $response->successful() || ! is_array($data) || ! isset($data['transaction_limit'])) {
            $text = is_array($data) ? json_encode($data) : trim(strip_tags((string) $response->body()));

            return ['ok' => false, 'message' => 'FIRMS answered: '.str($text)->limit(200), 'data' => is_array($data) ? $data : null];
        }

        return [
            'ok' => true,
            'message' => sprintf(
                'Used %s of %s transactions per %s.',
                $data['current_transactions'] ?? '?',
                $data['transaction_limit'],
                $data['transaction_interval'] ?? 'interval',
            ),
            'data' => $data,
        ];
    }
}
