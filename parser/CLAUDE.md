# parser

The data side of the harmonized MODIS + VIIRS burning calendar: the scripts that download the FIRMS hotspots,
compute the harmonization factors and build the dump package the application's database is deployed from. Paths
below are relative to `parser/`.

## What the scripts here are for

The scripts stay apart from the Laravel application, in this folder, for three reasons:

- They work on the raw FIRMS files in `data/` (about 12 GB, ignored by git), which exist only on the machine that
  downloaded them.
- Their jobs are long: the archive download took about 7 hours, the current-year download about 1.5 hours. The
  server needs only the dump package, not this code.
- The application reads the data only through the `firms` schema that the dump creates, so the application and
  these scripts meet in that schema and nowhere else.

| Path | What it does |
|---|---|
| `fetch_archive.py` | Downloads the yearly world archives of FIRMS (MODIS from 2000, VIIRS Suomi NPP from 2012, VIIRS NOAA-20 from 2018) into `data/raw/archive/`. Needs no MAP_KEY. A second run resumes an interrupted download. |
| `fetch_current_year.py` | Downloads the current year for the whole world from the FIRMS area API into `data/raw/api/<SOURCE>/`. Needs `FIRMS_MAP_KEY` in `.env`. |
| `firms_client.py` | Command line for the FIRMS API: key status, data availability, the hotspots of one area. |
| `firms/` | The package behind these scripts: the API client, the archive download, the data models. |
| `build_factors.py` | Computes the harmonization factors (MODIS points to VIIRS Suomi NPP points, per 2-degree square and calendar month), assembles the series with backup satellites for the days a satellite was silent, checks itself year by year and writes the method version files into `data/harmonization/<version>/` for the dump. Reads `data/raw/archive/` and `data/raw/api/`. |
| `harmonize/` | The package behind `build_factors.py`: reading the FIRMS files, the counts, the factors, the series, the check and the version files. |
| `export_dump.py` | Builds the dump package (`manifest.json`, `schema/*.sql`, gzip COPY files, `restore.sh`, `README.md`) from `data/raw/` and the method versions in `data/harmonization/`, for the world or for `--countries`. |
| `make_test_dump.sh` | Builds the test package of Ukraine into `data/dump/test-ukraine/`; further arguments go to `export_dump.py`. |
| `firmsdb/` | The package behind `export_dump.py` (the raw file reader, the precedence of overlapping sources, the rows, the method tables) and the database side: `sql/` with the `firms` schema and `restore.sh`, which deploys a package into PostgreSQL 17 with PostGIS 3. |
| `tests/` | Unit tests; `tests/test_firmsdb_sql.py` deploys a package into its own `postgis/postgis:17-3.5` container and removes it. |
| `testdata/test-ukraine/` | The committed test package of Ukraine, built by `make_test_dump.sh`. |
| `docs/deploy.md` | The instruction in Ukrainian: every step from a fresh machine to the application on real data. |
| `docs/data-standard.md` | The columns of every FIRMS file, their units and the NASA documents that state them. |

A change that adds a script adds its line to this table.

The developer note for the Laravel and Vue side is `../docs/database/README.md`. The harmonization method is
described in `../docs/harmonization/README.md`.
