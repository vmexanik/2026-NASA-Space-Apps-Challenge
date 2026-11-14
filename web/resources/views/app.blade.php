<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="description" content="Burning activity calendar from harmonized MODIS and VIIRS hotspots.">
        <title>{{ config('app.name', 'We Charge') }} · Burning Activity Calendar</title>
        @fonts
        @vite(['resources/css/app.css', 'resources/js/app.js'])
    </head>
    <body class="bg-page text-ink antialiased">
        <div id="app"></div>
        <noscript>This application needs JavaScript.</noscript>
    </body>
</html>
