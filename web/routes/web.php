<?php

use App\Http\Controllers\AreaPresetController;
use Illuminate\Support\Facades\Route;

// Public SPA (the admin panel lives under /admin, registered by Filament).
Route::view('/', 'app');

// Admins save the shape drawn on the map as a quick area (session of the admin panel).
Route::post('/presets', [AreaPresetController::class, 'store'])->middleware('auth');
