<?php

namespace App\Http\Controllers;

use App\Models\AreaPreset;
use App\Support\Aoi;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use InvalidArgumentException;

/** POST /presets: an admin saves the shape drawn on the public map as a quick area (session auth + CSRF). */
class AreaPresetController extends Controller
{
    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'name' => ['required', 'string', 'max:80'],
            'geometry' => ['required', 'array'],
        ]);

        try {
            $aoi = Aoi::fromGeoJson($data['geometry']);
        } catch (InvalidArgumentException $e) {
            return response()->json(['message' => $e->getMessage(), 'errors' => ['geometry' => [$e->getMessage()]]], 422);
        }

        $preset = AreaPreset::query()->create([
            'name_en' => $data['name'],
            'geometry' => $aoi->toGeoJson(),
            'sort' => (int) AreaPreset::query()->max('sort') + 1,
        ]);

        return response()->json($preset->toPublic(), 201);
    }
}
