<?php

use App\Http\Controllers\Api\AnalyticsController;
use App\Http\Controllers\Api\ExportController;
use Illuminate\Support\Facades\Route;

Route::middleware('throttle:public-api')->group(function () {
    Route::get('/meta', [AnalyticsController::class, 'meta']);
    Route::post('/calendar', [AnalyticsController::class, 'calendar']);
    Route::post('/summary', [AnalyticsController::class, 'summary']);
    Route::post('/export/csv', [ExportController::class, 'csv']);
});
