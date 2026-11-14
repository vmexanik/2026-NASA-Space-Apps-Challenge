---
last_verified: 2026-11-14
status: draft
---

# FIRMS hotspot data: columns, units, and sources

This page describes the raw active-fire hotspot files that the project reads from NASA FIRMS
(Fire Information for Resource Management System). It covers the two sensors, MODIS and VIIRS,
in both forms FIRMS delivers: the yearly archive and the near-real-time (NRT) API. For each sensor
it shows sample rows, the unit of every column, and the document that states that unit. It does
not cover how the project harmonizes the two sensors.

## Where the raw files are

The raw files live in [`data/`](../data/). Git ignores that folder because the archive alone
takes about 5 GB. Two scripts fill it:

| Folder | What it holds | Script that fills it |
|---|---|---|
| [`data/raw/archive/`](../data/raw/archive/) | One zip per sensor and year, all countries, standard processing | `python3 fetch_archive.py` |
| [`data/raw/api/`](../data/raw/api/) | The current year for the whole world from the FIRMS area API: one folder per source (`MODIS_SP`, `VIIRS_SNPP_NRT`, …), one file per chunk of 1–5 days (`<start>_<days>d.csv`) | `python3 fetch_current_year.py` |
| [`data/raw/nrt/`](../data/raw/nrt/) | Small area samples from the FIRMS API, last 1–5 days, shown on this page | `python3 firms_client.py area ...` |

Inside each archive zip, every country has its own CSV, for example
`modis/2021/modis_2021_Ukraine.csv` inside `modis_2021_all_countries.zip`. To read one without
unpacking the zip, run:

```
unzip -p data/raw/archive/modis_2021_all_countries.zip modis/2021/modis_2021_Ukraine.csv | head
```

The sample rows on this page come from these files:

- MODIS archive: [`modis_2021_all_countries.zip`](../data/raw/archive/modis_2021_all_countries.zip), file `modis/2021/modis_2021_Ukraine.csv`, date 2021-08-01.
- VIIRS archive: [`viirs-snpp_2017_all_countries.zip`](../data/raw/archive/viirs-snpp_2017_all_countries.zip), file `viirs-snpp/2017/viirs-snpp_2017_Ukraine.csv`, date 2017-08-01.
- MODIS NRT: [`MODIS_NRT_ukraine_2026-11-13_14.csv`](../data/raw/nrt/MODIS_NRT_ukraine_2026-11-13_14.csv), area `22,44,40.5,52.5`.
- VIIRS NRT: [`VIIRS_NOAA20_NRT_ukraine_2026-11-14.csv`](../data/raw/nrt/VIIRS_NOAA20_NRT_ukraine_2026-11-14.csv) and [`VIIRS_NOAA21_NRT_ukraine_2026-11-14.csv`](../data/raw/nrt/VIIRS_NOAA21_NRT_ukraine_2026-11-14.csv), same area.

## Sensors and satellites

Each sensor flies on more than one satellite. The `satellite` column tells them apart.

| Sensor | Satellite | `satellite` value in the files | Archive zip prefix | Nominal pixel |
|---|---|---|---|---|
| MODIS | Terra | `Terra` | `modis` | 1 km |
| MODIS | Aqua | `Aqua` | `modis` | 1 km |
| VIIRS | Suomi NPP (S-NPP) | `N` | `viirs-snpp` | 375 m |
| VIIRS | NOAA-20 (JPSS-1) | `N20` | `viirs-jpss1` | 375 m |
| VIIRS | NOAA-21 (JPSS-2) | `N21` | not downloaded | 375 m |

The FIRMS FAQ states that S-NPP data production "ceased at 15:40 Universal Time (UTC) on
November 2, 2026" [F]. The project downloads no NOAA-21 archive, so NOAA-21 rows come only from
the NRT API.

## Archive files and NRT files differ in two columns

Both forms share 14 columns. The archive and the API files of a standard-processing (SP) source add a 15th column, `type`. The `version` column also
takes different values in each form.

| Column | Archive | NRT |
|---|---|---|
| `type` | present, values 0–3 | absent |
| `version` | collection and product version, for example `6.03` or `2` | collection with `NRT`, for example `6.1NRT` or `2.0NRT` |

The FIRMS FAQ says: "NRT data distributed via the FIRMS download tool does not attribute the
static sources or inferred hotspot "type"" [F]. The project sets non-fire rows aside before any
calculation, so it can do that only for archive rows.

## MODIS columns

Sample archive rows (Terra and Aqua, Ukraine, 2021-08-01):

```
latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type
47.5888,31.5712,304.2,2.6,1.6,2021-08-01,0049,Aqua,MODIS,59,6.03,288,28.4,N,0
48.7114,38.0979,330.6,1,1,2021-08-01,0832,Terra,MODIS,63,6.03,310.4,15.6,D,0
47.8727,33.446,328.7,1.2,1.1,2021-08-01,0833,Terra,MODIS,69,6.03,305.1,21.4,D,2
47.0967,37.5972,325.7,1,1,2021-08-01,0833,Terra,MODIS,0,6.03,305.9,11.1,D,2
```

Sample NRT row (Aqua, 2026-11-13). It has no `type` column:

```
latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight
45.31887,28.57331,336.39,1.51,1.21,2026-11-13,1344,Aqua,MODIS,68,6.1NRT,291.92,69,D
```

| Column | Meaning | Unit or values | Evidence |
|---|---|---|---|
| `latitude` | Latitude of the center of the 1 km fire pixel | degrees | [G-M] Table 10: "lat · degrees · Latitude at center of fire pixel." |
| `longitude` | Longitude of the center of the fire pixel | degrees | [G-M] Table 10: "lon · degrees" |
| `brightness` | Brightness temperature of the fire pixel, channel 21/22 | K (kelvin) | [A]: "Brightness temperature 21 (Kelvin)" |
| `scan` | Pixel size along the scan, east–west | km, 1.0 at nadir, up to 4.8 at the swath edge | [G-M] §8.4.6 gives "the pixel dimensions (in km)". [A]: "Scan and track reflect actual pixel size." [D]: 1.0–4.8 in 2021 Ukraine rows |
| `track` | Pixel size along the track, north–south | km, 1.0 to 2.0 | Same sources as `scan`. [D]: 1.0–2.0 |
| `acq_date` | Date of the overpass | `YYYY-MM-DD`, UTC | [A]: "Acquisition Date" |
| `acq_time` | Time of the overpass | `HHMM`, UTC | [A]: "Time of acquisition/overpass of the satellite (in UTC)." |
| `satellite` | Satellite | `Terra` or `Aqua` | [D]. The attribute page writes "A = Aqua and T = Terra" [A], but the CSV files spell the names out |
| `instrument` | Sensor | `MODIS` | [D]. Neither the attribute page nor the guide lists this column |
| `confidence` | Detection confidence | % (0–100). Classes: low 0–29, nominal 30–79, high 80–100 | [A]: "Confidence (0-100%)". [G-M] Table 11: "0% ≤ C < 30% low, 30% ≤ C < 80% nominal, 80% ≤ C ≤ 100% high" |
| `version` | Collection and processing source | text, see below | [A]: "Version (Collection and source)" |
| `bright_t31` | Brightness temperature of the fire pixel, channel 31 | K (kelvin) | [A]: "Brightness temperature 31 (Kelvin)" |
| `frp` | Fire radiative power of the pixel | MW (megawatts) | [A]: "Fire Radiative Power (MW - megawatts)" |
| `daynight` | Day or night detection | `D` or `N` | [A]: "D= Daytime fire, N= Nighttime fire" |
| `type` | Inferred hotspot type, archive only | 0 vegetation fire, 1 active volcano, 2 other static land source, 3 offshore | [G-M] Table 10 and [A]. [A] footnote: "only available for MCD14ML (standard quality) data" |

The MODIS `version` column takes these values in the project's archive (Ukraine files, every
year checked):

| Years | `version` | Reading |
|---|---|---|
| 2000–2017 | `6.2` | Collection 6, product version 02 (our reading) |
| 2018–2022 | `6.03` | Collection 6, product version 03 |
| 2023–2025 | `61.03` | Collection 6.1, product version 03 |
| NRT | `6.1NRT` | Collection 6.1, near-real-time processing [A] |

The reading of the archive values rests on the file names in [G-M] §5.5.1, `MCD14ML.YYYYMM.CCC.VV`,
where CCC is the collection and VV is the product version, for example `MCD14ML.201701.006.03`.
No source states the FIRMS CSV values `6.2` and `61.03` directly.

## VIIRS columns

Sample archive rows (S-NPP, Ukraine, 2017-08-01):

```
latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight,type
48.74919,26.60671,299.73,0.59,0.7,2017-08-01,0136,N,VIIRS,n,2,289.58,0.95,N,2
50.54178,26.25836,314.46,0.5,0.66,2017-08-01,0136,N,VIIRS,n,2,288.57,2.09,N,2
48.76572,39.58633,334.12,0.5,0.41,2017-08-01,0942,N,VIIRS,n,2,304.02,5.47,D,0
48.33157,37.71348,339.15,0.4,0.44,2017-08-01,0942,N,VIIRS,l,2,309.61,6.57,D,0
```

Sample NRT rows (NOAA-20 and NOAA-21, 2026-11-14). They have no `type` column:

```
latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
48.29334,39.91782,297.61,0.37,0.58,2026-11-14,28,N20,VIIRS,n,2.0NRT,282.11,0.37,N
51.89175,29.34097,339.59,0.35,0.57,2026-11-14,113,N21,VIIRS,n,2.0NRT,274.25,3.45,N
```

| Column | Meaning | Unit or values | Evidence |
|---|---|---|---|
| `latitude` | Latitude of the center of the 375 m fire pixel | degrees | [G-V] §3.2.2: "Lat · Fire pixel latitude (degrees)" |
| `longitude` | Longitude of the center of the fire pixel | degrees | [G-V] §3.2.2: "Lon · Fire pixel longitude (degrees)" |
| `bright_ti4` | Brightness temperature of the fire pixel, channel I-4 | K (kelvin) | [A]: "VIIRS I-4 channel brightness temperature of the fire pixel measured in Kelvin". [G-V]: "T4 … (K)" |
| `scan` | Pixel size along the scan | km, about 0.375 at nadir, up to 0.8 at the swath edge | [A]: "approximately 375 m pixels at nadir. Scan and track reflect actual pixel size". [G-V] gives the pixel area in km². [D]: 0.32–0.80 in 2017 Ukraine rows |
| `track` | Pixel size along the track | km | Same sources as `scan`. [D]: 0.36–0.78 |
| `acq_date` | Date of the overpass | `YYYY-MM-DD`, UTC | [A]: "Date of VIIRS acquisition" |
| `acq_time` | Time of the overpass | `HHMM`, UTC | [A]: "(in UTC)". [G-V]: "UTC detection hour (HH) and minute (MM)" |
| `satellite` | Satellite | `N`, `N20`, `N21` | [A]: "N= Suomi National Polar-orbiting Partnership (Suomi NPP), N20=NOAA-20 …, N21=NOAA-21" |
| `instrument` | Sensor | `VIIRS` | [D]. Neither the attribute page nor the guide lists this column |
| `confidence` | Confidence class | `l` low, `n` nominal, `h` high | [A]: "Confidence values are set to low, nominal and high." [G-V] writes the classes as `L`, `N`, `H`. The FIRMS CSV files use lowercase [D] |
| `version` | Collection and processing source | `2` in the archive, `2.0NRT` in NRT | [D]. [G-V] §3.2.1: collection "currently "02"". The examples on [A] still show Collection 1 (`1.0NRT`) |
| `bright_ti5` | Brightness temperature of the fire pixel, channel I-5 | K (kelvin) | [A]: "I-5 Channel brightness temperature of the fire pixel measured in Kelvin". [G-V]: "T5 … (K)" |
| `frp` | Fire radiative power of the pixel | MW (megawatts) | [A]: "pixel-integrated fire radiative power in MW (megawatts)". [G-V]: "FRP · Fire radiative power (MW)" |
| `daynight` | Day or night detection | `D` or `N` | [A]: "D= Daytime fire, N= Nighttime fire" |
| `type` | Inferred hotspot type, archive only | 0 vegetation fire, 1 active volcano, 2 other static land source, 3 offshore | [G-V] §3.2.2: "Type … 0 = presumed vegetation fire, 1 = active volcano, 2 = other static land source, 3 = offshore detection (includes all detections over water)". The VIIRS table on [A] has no `type` row |

## Differences between the files and the documentation

The project's code must handle these cases. Each one was checked in the files listed above.

- **`acq_time` loses its leading zeros in every file of the area API, SP and NRT alike.** The
  archive writes `0049`. The API writes `28` for 00:28 UTC. Pad the value to four digits before
  parsing it.
- **A coordinate closer to 0 than 0.0001 is written in exponent form**, for example `4e-05`. The
  Suomi NPP archive has 341 such rows, the NOAA-20 archive 146, and the API files 53. Read both the
  plain and the exponent form.
- The archive files are cut by country, so they hold no point in the open sea. The API files cover
  the whole area and hold open-sea points, all of `type` 3. In the central North Sea the NOAA-20
  archive of 2025 has 0 points, and the NOAA-20 SP files of 2026 have 120.
- The MODIS `satellite` column holds `Terra` and `Aqua`, not the `T` and `A` that [A] lists.
- VIIRS `confidence` is lowercase (`l`, `n`, `h`) in FIRMS files and uppercase in [G-V].
- MODIS `confidence` can be 0. Such a row is a low-confidence detection, not a missing value.
- No source gives the unit of `scan` and `track` in the FIRMS table. The unit km comes from
  [G-M] §8.4.6 and from the measured ranges, which match 1 km and 375 m pixels at nadir.
- The day/night flag is set differently in the two forms. For archive data, [F] says: "If the
  SZA exceeds 85 degrees, it is assigned a "night" value". SZA is the solar zenith angle. For NRT
  data the flag is "based simply on the satellite's orbit: ascending (day) vs. descending (night)" [F].

## Sources

- [A] FIRMS attribute descriptions, MODIS and VIIRS:
  https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs
- [F] FIRMS FAQ: https://www.earthdata.nasa.gov/data/tools/firms/faq
- [G-M] Giglio, Schroeder, Hall, Justice. *MODIS Collection 6 and Collection 6.1 Active Fire
  Product User's Guide*, version 1.0. Table 10 (MCD14ML columns), Table 11 (confidence classes),
  §5.5.1 (file names), §8.4.6 (pixel size):
  https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf
- [G-V] Schroeder. *Collection 2 VIIRS 375-m Active Fire Product User's Guide*, version 1.2.
  §3.2.1 (file names), §3.2.2 (VNP14IMGML columns):
  https://www.earthdata.nasa.gov/s3fs-public/2025-06/VIIRS_C2_AF-375m_User_Guide_1.2.pdf
- [D] The project's own files in [`data/raw/`](../data/raw/), read on 2026-11-14 with `unzip -p`
  and `awk`.
- Code: `fetch_archive.py` and `firms/archive.py` (`Sensor`, `ARCHIVE_URL`) for the archive,
  `firms_client.py`, `firms/constants.py` (`Source`) and `firms/client.py` (`FirmsClient.latest`,
  `FirmsClient.iter_range`) for the NRT API.
