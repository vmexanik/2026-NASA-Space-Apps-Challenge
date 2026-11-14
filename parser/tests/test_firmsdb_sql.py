"""Tests of the firms schema, its SQL functions and restore.sh, in a throwaway PostGIS container.

The tests build a small dump package from literal rows in the shared package format of the web database plan,
deploy it with firmsdb/restore.sh into a container of postgis/postgis:17-3.5 (FIRMSDB_TEST_IMAGE overrides the
image) and compare the functions with counts made by hand from the same rows. restore.sh runs inside the
container, as the owner of the database who is not a superuser, the way it runs on the server. Without docker the
tests are skipped.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from datetime import date
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
FIRMSDB = ROOT / "firmsdb"
IMAGE = os.environ.get("FIRMSDB_TEST_IMAGE", "postgis/postgis:17-3.5")
SEP = "\x1f"

TERRA, AQUA, SNPP, NOAA20, NOAA21 = 1, 2, 3, 4, 5
CODES = {TERRA: "terra", AQUA: "aqua", SNPP: "snpp", NOAA20: "noaa20", NOAA21: "noaa21"}
FAMILY = {TERRA: "modis", AQUA: "modis", SNPP: "snpp", NOAA20: "noaa20", NOAA21: "noaa21"}
SATELLITES = [
    (TERRA, "terra", "Terra", "MODIS", "Terra"),
    (AQUA, "aqua", "Aqua", "MODIS", "Aqua"),
    (SNPP, "snpp", "N", "VIIRS", "Suomi NPP"),
    (NOAA20, "noaa20", "N20", "VIIRS", "NOAA-20"),
    (NOAA21, "noaa21", "N21", "VIIRS", "NOAA-21"),
]


def cell_id_e5(lat_e5: int, lon_e5: int) -> int:
    """The 0.25-degree cell of a point, by the formula of the plan's Global Constraints."""
    ix = min((lon_e5 + 18_000_000) // 25_000, 1439)
    iy = min((lat_e5 + 9_000_000) // 25_000, 719)
    return iy * 1440 + ix


def cell2_id(cell_id: int) -> int:
    iy, ix = divmod(cell_id, 1440)
    return (iy // 8) * 180 + ix // 8


class Fire(NamedTuple):
    day: str
    hhmm: int
    sat: int
    lat_e5: int
    lon_e5: int
    conf_class: str
    conf_pct: int | None
    is_day: bool
    batch: int

    @property
    def date(self) -> date:
        return date.fromisoformat(self.day)

    @property
    def lat(self) -> float:
        return self.lat_e5 / 1e5

    @property
    def lon(self) -> float:
        return self.lon_e5 / 1e5

    @property
    def cell(self) -> int:
        return cell_id_e5(self.lat_e5, self.lon_e5)


# Cell A is [30.5, 30.75] x [50.25, 50.5] (cell 808682), cell B is the cell east of it. The polygon covers all of
# A and the half of B below its diagonal lon + lat = 81.25. Every point keeps clear of the polygon's edges.
POLYGON = [[30.5, 50.25], [31.0, 50.25], [30.75, 50.5], [30.5, 50.5], [30.5, 50.25]]
AOI = json.dumps({"type": "Polygon", "coordinates": [POLYGON]})
UA_CELL2 = 12705  # the 2-degree square of A, B and the cells around them
BR_CELL2 = 7262  # the 2-degree square of the point in Brazil

FIRES = [
    # 2010: Aqua is the series satellite of v0-raw, Terra is not.
    Fire("2010-07-05", 1105, AQUA, 5030000, 3060000, "n", 59, True, 1),  # A
    Fire("2010-07-05", 1105, AQUA, 5045000, 3090000, "n", 75, True, 1),  # B above the diagonal: outside
    Fire("2010-07-20", 1030, TERRA, 5040000, 3070000, "n", 64, True, 1),  # A, but Terra
    Fire("2010-08-12", 150, AQUA, 5030000, 3080000, "l", 20, False, 1),  # B below the diagonal: inside
    Fire("2010-08-12", 150, AQUA, 5030000, 3040000, "h", 85, False, 1),  # west of A: outside
    # 2021: Suomi NPP is the series satellite of v0-raw, Aqua the one of vtest.
    Fire("2021-03-10", 12, SNPP, 5030000, 3060000, "n", None, False, 3),  # A
    Fire("2021-03-10", 12, SNPP, 5026000, 3095000, "h", None, False, 3),  # B, inside
    Fire("2021-03-11", 1130, SNPP, 5045000, 3090000, "l", None, True, 3),  # B, outside
    Fire("2021-03-20", 1040, AQUA, 5035000, 3065000, "n", 70, True, 2),  # A
    Fire("2021-08-02", 1124, SNPP, 5045000, 3055000, "n", None, True, 3),  # A
    Fire("2021-08-02", 1124, SNPP, 5020000, 3070000, "n", None, True, 3),  # south of A: outside
    # The 12 Aqua fires of August 2021 inside the polygon: 8 in A, 4 in B below the diagonal.
    Fire("2021-08-03", 1040, AQUA, 5027000, 3055000, "n", 50, True, 2),
    Fire("2021-08-03", 1040, AQUA, 5027000, 3068000, "n", 51, True, 2),
    Fire("2021-08-04", 1125, AQUA, 5032000, 3055000, "n", 52, True, 2),
    Fire("2021-08-04", 1125, AQUA, 5032000, 3068000, "h", 88, True, 2),
    Fire("2021-08-05", 1210, AQUA, 5037000, 3055000, "n", 53, True, 2),
    Fire("2021-08-05", 1210, AQUA, 5037000, 3068000, "l", 15, True, 2),
    Fire("2021-08-06", 120, AQUA, 5042000, 3055000, "n", 54, False, 2),
    Fire("2021-08-06", 120, AQUA, 5042000, 3068000, "n", 55, False, 2),
    Fire("2021-08-07", 1035, AQUA, 5027000, 3078000, "n", 56, True, 2),
    Fire("2021-08-07", 1035, AQUA, 5030000, 3085000, "n", 57, True, 2),
    Fire("2021-08-08", 1120, AQUA, 5035000, 3080000, "n", 58, True, 2),
    Fire("2021-08-08", 1120, AQUA, 5027000, 3095000, "n", 60, True, 2),
    Fire("2021-08-14", 1050, AQUA, 5040000, 3095000, "n", 61, True, 2),  # B, outside the polygon
    Fire("2021-08-14", 1050, AQUA, 5060000, 3060000, "n", 62, True, 2),  # north of A: outside
    Fire("2021-08-15", 1050, AQUA, -1000000, -5500000, "n", 63, True, 2),  # Brazil
    Fire("2021-11-20", 1200, SNPP, -1000000, -5500000, "n", None, True, 3),  # Brazil
    # 2026: NOAA-20 from an NRT file; v0-raw takes NOAA-20 from 2026-11-03 on.
    Fire("2026-11-02", 400, NOAA20, 5030000, 3060000, "n", None, False, 4),  # A, before its days in the series
    Fire("2026-11-05", 28, NOAA20, 5040000, 3070000, "n", None, False, 4),  # A, acq_time 28 in the NRT CSV
    Fire("2026-11-06", 113, NOAA20, 5040000, 3095000, "n", None, False, 4),  # B, outside
]
STATIC = [  # (fire, type)
    (Fire("2021-08-02", 1124, SNPP, 5030000, 3060000, "n", None, True, 3), 2),
    (Fire("2021-08-03", 1050, AQUA, 5030000, 3061000, "n", 66, True, 2), 3),
]
BATCHES = [  # id, source_code, is_nrt, file, member_count, versions, date_from, date_to
    (1, "MODIS_SP", False, "data/raw/archive/modis_2010_all_countries.zip", 3, ["6.03"], "2010-06-01", "2010-08-31"),
    (2, "MODIS_SP", False, "data/raw/archive/modis_2021_all_countries.zip", 3, ["61.03"], "2021-01-01", "2021-12-31"),
    (3, "VIIRS_SNPP_SP", False, "data/raw/archive/viirs-snpp_2021_all_countries.zip", 3, ["2"], "2021-01-01",
     "2021-12-31"),
    (4, "VIIRS_NOAA20_NRT", True, "data/raw/api/VIIRS_NOAA20_NRT/2026-11-10_5d.csv", None, ["2.0NRT"], "2026-11-01",
     "2026-11-14"),
]
DAYS = [  # satellite, first day, last day, batch: the days each file holds for each satellite
    (TERRA, "2010-06-01", "2010-08-31", 1),
    (AQUA, "2010-06-01", "2010-08-31", 1),
    (AQUA, "2021-01-01", "2021-12-31", 2),
    (SNPP, "2021-01-01", "2021-12-31", 3),
    (NOAA20, "2026-11-01", "2026-11-14", 4),
]

V0_RAW_SEGMENTS = [(TERRA, "2000-11-01", "2002-07-03"), (AQUA, "2002-07-04", "2012-01-19"),
                   (SNPP, "2012-01-20", "2026-11-02"), (NOAA20, "2026-11-03", None)]
# vtest is a sparse version: Aqua is its only satellite, in 2021, with weight 2 in the Ukrainian square.
VTEST_WEIGHTS = [(AQUA, "2021-01-01", "2021-12-31", cell2, month, None, weight)
                 for cell2, weight in ((UA_CELL2, 2.0), (BR_CELL2, 3.0)) for month in range(1, 13)]
# vviirs has only VIIRS satellites, Suomi NPP in 2021 and NOAA-20 from 2026-11-01, so both NOAA-20 fires of the
# polygon are in it. Its errors are those of decision D75: Suomi NPP keeps 0, NOAA-20 has a ladder of its own.
VVIIRS_WEIGHTS = ([(SNPP, "2021-01-01", "2021-12-31", cell2, month, None, 1.0)
                   for cell2 in (UA_CELL2, BR_CELL2) for month in range(1, 13)]
                  + [(NOAA20, "2026-11-01", None, UA_CELL2, month, None, 1.0) for month in range(1, 13)])
SPARSE_WEIGHTS = {"vtest": VTEST_WEIGHTS, "vviirs": VVIIRS_WEIGHTS}
METHODS = [
    ("v0-raw", "v0-raw: weight 1, not harmonized", '{"confidence_filter": null, "harmonized": false}',
     "2026-11-14 12:00:00+00"),
    ("vtest", "test version", '{"confidence_filter": null, "harmonized": true, "lambda": 300}',
     "2026-11-14 12:00:00+00"),
    ("vviirs", "test version of VIIRS errors", '{"confidence_filter": null, "harmonized": true}',
     "2026-11-14 12:00:00+00"),
]
VTEST_FACTORS = [("vtest", AQUA, UA_CELL2, 8, 2.0, 900, 1800, 0.75, 1.9, 3000, 1.8, 1.7)]
# The rows of the brief: n_min 1 gives 0.4, n_min 10 gives 0.2. The row n_min 20 catches a lookup by count (24)
# instead of count_raw (12). VIIRS rows have the satellite set and 0, as the factors step writes them.
VTEST_ERRORS = [("vtest", "modis", AQUA, 1, 0.4), ("vtest", "modis", AQUA, 10, 0.2), ("vtest", "modis", AQUA, 20, 0.1),
                ("vtest", "viirs", SNPP, 1, 0.0), ("vtest", "viirs", NOAA20, 1, 0.0)]
VTEST_GAPS = [("vtest", "2021-03-15")]
VVIIRS_ERRORS = [("vviirs", "viirs", SNPP, 1, 0.0)] + [
    ("vviirs", "viirs", NOAA20, n_min, rel) for n_min, rel in
    ((1, 0.6), (3, 0.3), (10, 0.2), (30, 0.15), (100, 0.12), (300, 0.1), (1000, 0.08))]
DATA_SOURCES = ["MODIS_SP", "VIIRS_SNPP_SP", "VIIRS_NOAA20_NRT", "VIIRS_NOAA20_SP"]

CONTAINER = ""
FIRST_RESTORE: subprocess.CompletedProcess | None = None
PUBLIC_BEFORE: list[list[str | None]] = []


def series_weight(version: str, fire: Fire) -> float | None:
    """The weight of a fire in a version's series, or None when the fire is not in it."""
    if version == "v0-raw":
        for sat, first, last in V0_RAW_SEGMENTS:
            if sat == fire.sat and date.fromisoformat(first) <= fire.date and (
                    last is None or fire.date <= date.fromisoformat(last)):
                return 1.0
        return None
    for sat, first, last, cell2, month, is_day, weight in SPARSE_WEIGHTS[version]:
        if (sat == fire.sat and cell2 == cell2_id(fire.cell) and month == fire.date.month
                and date.fromisoformat(first) <= fire.date
                and (last is None or fire.date <= date.fromisoformat(last))
                and (is_day is None or is_day == fire.is_day) and weight > 0):
            return weight
    return None


def inside(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Even-odd rule over a closed ring."""
    result = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            result = not result
    return result


def brute_force_months(version: str) -> dict[tuple[int, int], tuple[int, int]]:
    """(year, month) -> (count, count_raw) of the series fires inside the polygon, counted one by one."""
    sums: dict[tuple[int, int], tuple[int, float]] = {}
    for fire in FIRES:
        weight = series_weight(version, fire)
        if weight is not None and inside(fire.lon, fire.lat, POLYGON):
            n_raw, n_harm = sums.get((fire.date.year, fire.date.month), (0, 0.0))
            sums[(fire.date.year, fire.date.month)] = (n_raw + 1, n_harm + weight)
    return {key: (round(n_harm), n_raw) for key, (n_raw, n_harm) in sums.items()}


# --- the package ----------------------------------------------------------------------------------------------


def tsv_value(value) -> str:
    if value is None:
        return r"\N"
    if value is True:
        return "t"
    if value is False:
        return "f"
    if isinstance(value, list):
        return "{" + ",".join(value) + "}"
    return str(value)


def hotspot_row(fire: Fire) -> tuple:
    viirs = fire.sat >= SNPP
    return (fire.day, fire.hhmm, fire.sat, fire.cell, fire.lat_e5, fire.lon_e5, 12.5, 330.5, 295.25,
            0.39 if viirs else 1.1, 0.36 if viirs else 1.0, fire.conf_class, fire.conf_pct, fire.is_day,
            fire.batch == 4, fire.batch)


def date_range(first: str, last: str):
    day, end = date.fromisoformat(first).toordinal(), date.fromisoformat(last).toordinal()
    while day <= end:
        yield date.fromordinal(day).isoformat()
        day += 1


def load_batch_rows(changes: dict[int, dict] | None = None) -> list[tuple]:
    """The rows of load_batch; changes replace fields of a batch, such as {3: {"date_to": ..., "rows_fire": ...}}."""
    rows = []
    for bid, source, nrt, file, members, versions, first, last in BATCHES:
        row = {"source_code": source, "is_nrt": nrt, "file": file, "member_count": members,
               "file_size": 1000 + bid, "file_mtime": "2026-11-14 12:52:00+00", "versions": versions,
               "date_from": first, "date_to": last, "rows_fire": sum(f.batch == bid for f in FIRES),
               "rows_static": sum(f.batch == bid for f, _ in STATIC)}
        row.update((changes or {}).get(bid, {}))
        rows.append((bid,) + tuple(row.values()))
    return rows


def write_tsv_gz(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="\n", compresslevel=1) as handle:
        for row in rows:
            handle.write("\t".join(tsv_value(v) for v in row) + "\n")
            n += 1
    return n


def build_package(out: Path) -> None:
    files: list[dict] = []

    def add(table: str, rel: str, rows, **keys) -> None:
        files.append({"table": table, **keys, "file": rel, "rows": write_tsv_gz(out / rel, rows)})

    add("satellite", "data/satellite.tsv.gz", SATELLITES)
    add("load_batch", "data/load_batch.tsv.gz", load_batch_rows())
    add("day_source", "data/day_source.tsv.gz", [(sat, day, batch == 4, batch) for sat, first, last, batch in DAYS
                                                 for day in date_range(first, last)])
    add("archive_cell", "data/archive_cell.tsv.gz",
        [(c,) for c in sorted({f.cell for f in FIRES if f.batch != 4} | {f.cell for f, _ in STATIC})])
    for year, sat in sorted({(f.date.year, f.sat) for f in FIRES}):
        part = sorted((f for f in FIRES if f.date.year == year and f.sat == sat),
                      key=lambda f: (f.cell, f.day, f.hhmm))
        add("hotspot", f"data/hotspot/{year}_{CODES[sat]}.tsv.gz", map(hotspot_row, part),
            partition=f"hotspot_{year}_{CODES[sat]}", year=year, satellite=CODES[sat])
    statics = {(2010, "modis"): []}  # an empty file: a year of the archive without non-fires of this family
    for fire, kind in STATIC:
        statics.setdefault((fire.date.year, FAMILY[fire.sat]), []).append(hotspot_row(fire) + (kind,))
    for (year, family), rows in sorted(statics.items()):
        add("hotspot_static", f"data/hotspot_static/{year}_{family}.tsv.gz", rows,
            partition=f"hotspot_static_{year}", year=year)
    v0_weights = ((version, sat, first, last, cell2, month, None, 1.0) for version in ["v0-raw"]
                  for sat, first, last in V0_RAW_SEGMENTS for cell2 in range(16200) for month in range(1, 13))
    tables = {
        "v0-raw": {"method": [METHODS[0]], "method_weight": v0_weights},
        "vtest": {"method": [METHODS[1]], "method_weight": [("vtest",) + w for w in VTEST_WEIGHTS],
                  "method_factor": VTEST_FACTORS, "method_error": VTEST_ERRORS, "method_gap": VTEST_GAPS},
        "vviirs": {"method": [METHODS[2]], "method_weight": [("vviirs",) + w for w in VVIIRS_WEIGHTS],
                   "method_error": VVIIRS_ERRORS},
    }
    for version, version_tables in tables.items():
        for table, rows in version_tables.items():
            add(table, f"data/method/{version}/{table}.tsv.gz", rows, version=version)
    manifest = {"format": 1, "name": "test-sql", "built_at": "2026-11-15T10:00:00Z", "scope": "countries",
                "countries": ["Australia", "Brazil", "Ukraine"], "years": [2010, 2026],
                "methods": ["v0-raw", "vtest"], "files": files,
                "sources": [{"file": "data/raw/archive/modis_2021_all_countries.zip", "size": 1002,
                             "mtime": "2026-11-14T12:52:00Z"}]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (out / "schema").mkdir()
    for sql in sorted((FIRMSDB / "sql").glob("*.sql")):  # the package carries copies, as the exporter makes them
        shutil.copy(sql, out / "schema" / sql.name)
    if (FIRMSDB / "restore.sh").exists():
        shutil.copy(FIRMSDB / "restore.sh", out / "restore.sh")


# --- the container --------------------------------------------------------------------------------------------


def docker(*args: str, input: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], input=input, capture_output=True, text=True, timeout=timeout,
                          check=False)


def psql(sql: str, *, user: str = "loader") -> subprocess.CompletedProcess:
    return docker("exec", "-i", "-e", f"PGPASSWORD={user}", CONTAINER, "psql", "-X", "-q", "-h", "127.0.0.1",
                  "-U", user, "-d", "we_charge", "-v", "ON_ERROR_STOP=1", "-A", "-t", "-F", SEP, "-P",
                  "null=\\N", "-f", "-", input=sql)


def query(sql: str) -> list[list[str | None]]:
    result = psql(sql)
    if result.returncode:
        raise AssertionError(f"query failed: {result.stderr.strip()}\n{sql}")
    return [[None if v == "\\N" else v for v in line.split(SEP)] for line in result.stdout.splitlines()]


def scalar(sql: str) -> str | None:
    return query(sql)[0][0]


def restore(*args: str, package: str = "/pkg") -> subprocess.CompletedProcess:
    return docker("exec", "-e", "PGHOST=127.0.0.1", "-e", "PGUSER=loader", "-e", "PGPASSWORD=loader",
                  "-e", "PGDATABASE=we_charge", CONTAINER, "bash", f"{package}/restore.sh", *args)


def variant_package(target: str, *, manifest: dict | None = None, files: dict[str, list] | None = None,
                    entries: list[dict] | None = None) -> None:
    """Copies /pkg to target in the container, with keys of manifest.json, data files and file entries changed."""
    data = json.loads(docker("exec", CONTAINER, "cat", "/pkg/manifest.json").stdout)
    data.update(manifest or {})
    data["files"] += entries or []
    work = Path(tempfile.mkdtemp(prefix="firmsdb-sql-variant-"))
    try:
        for rel, rows in (files or {}).items():
            write_tsv_gz(work / rel, rows)
        (work / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
        for step in (("exec", CONTAINER, "bash", "-c", f"rm -rf {target} && cp -r /pkg {target}"),
                     ("cp", f"{work}/.", f"{CONTAINER}:{target}")):
            if (done := docker(*step)).returncode:
                raise RuntimeError(done.stderr)
    finally:
        shutil.rmtree(work, True)


def quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def setUpModule() -> None:
    global CONTAINER, FIRST_RESTORE, PUBLIC_BEFORE
    if shutil.which("docker") is None or docker("info", timeout=30).returncode:
        raise unittest.SkipTest("docker is not available")
    CONTAINER = f"firmsdb-sql-test-{uuid.uuid4().hex[:8]}"
    started = docker("run", "-d", "--name", CONTAINER, "-e", "POSTGRES_PASSWORD=test",
                     "-p", "127.0.0.1::5432", IMAGE)
    unittest.addModuleCleanup(docker, "rm", "-f", "-v", CONTAINER)
    if started.returncode:
        raise RuntimeError(f"docker run failed: {started.stderr}")
    deadline = time.monotonic() + 120
    # The image first runs a server on the Unix socket only to create PostGIS; TCP answers once the real one runs.
    while docker("exec", CONTAINER, "pg_isready", "-q", "-h", "127.0.0.1", "-U", "postgres").returncode:
        if time.monotonic() > deadline:
            raise RuntimeError("PostgreSQL in the container did not start")
        time.sleep(1)
    setup = docker("exec", "-i", CONTAINER, "psql", "-X", "-q", "-U", "postgres", "-v", "ON_ERROR_STOP=1", input="""
        CREATE ROLE loader LOGIN PASSWORD 'loader';
        CREATE DATABASE we_charge OWNER loader;
        \\c we_charge
        CREATE EXTENSION postgis;
    """)
    if setup.returncode:
        raise RuntimeError(f"database setup failed: {setup.stderr}")
    # The application's own tables (web/database/migrations): restore.sh writes its journal into them.
    query("""
        CREATE TABLE public.data_sources (id bigserial PRIMARY KEY, code varchar(255) NOT NULL UNIQUE,
            label varchar(255) NOT NULL, sensor varchar(16) NOT NULL, kind varchar(16) NOT NULL);
        CREATE TABLE public.ingest_runs (id bigserial PRIMARY KEY,
            data_source_id bigint REFERENCES public.data_sources ON DELETE SET NULL, coverage_region_id bigint,
            period_from date, period_to date, status varchar(16) NOT NULL DEFAULT 'pending',
            records_count bigint NOT NULL DEFAULT 0, error text, started_at timestamp, finished_at timestamp,
            created_at timestamp, updated_at timestamp);
    """ + "".join(f"INSERT INTO public.data_sources (code, label, sensor, kind) VALUES ({quote(code)}, "
                  f"{quote(code)}, 'modis', 'archive');\n" for code in DATA_SOURCES))
    PUBLIC_BEFORE = query("SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace ORDER BY 1")
    work = Path(tempfile.mkdtemp(prefix="firmsdb-sql-test-"))
    unittest.addModuleCleanup(shutil.rmtree, work, True)
    build_package(work / "pkg")
    copied = docker("cp", str(work / "pkg"), f"{CONTAINER}:/pkg")
    if copied.returncode:
        raise RuntimeError(f"docker cp failed: {copied.stderr}")
    FIRST_RESTORE = restore("--jobs", "3")


def monthly(version: str, first: str = "1999-01-01", last: str = "2030-12-31", aoi: str = AOI) -> list[list]:
    return query(f"SELECT * FROM firms.monthly_counts({quote(aoi)}, DATE '{first}', DATE '{last}', '{version}')")


class TestFunctions(unittest.TestCase):
    def test_brute_force_fixture(self):
        # Hand-checked against the comments of FIRES, so that the brute force itself is right.
        self.assertEqual(brute_force_months("v0-raw"),
                         {(2010, 7): (1, 1), (2010, 8): (1, 1), (2021, 3): (2, 2), (2021, 8): (1, 1),
                          (2026, 11): (1, 1)})
        self.assertEqual(brute_force_months("vtest"), {(2021, 3): (2, 1), (2021, 8): (24, 12)})
        self.assertEqual(brute_force_months("vviirs"), {(2021, 3): (2, 2), (2021, 8): (1, 1), (2026, 11): (2, 2)})
        self.assertEqual(cell2_id(cell_id_e5(5030000, 3060000)), UA_CELL2)
        self.assertEqual(cell2_id(cell_id_e5(-1000000, -5500000)), BR_CELL2)

    def test_monthly_counts_match_brute_force(self):
        for version in ("v0-raw", "vtest", "vviirs"):
            with self.subTest(version=version):
                expected = brute_force_months(version)
                got = {(int(r[0]), int(r[1])): (int(r[2]), int(r[3])) for r in monthly(version)}
                for key, value in got.items():
                    self.assertEqual(value, expected.get(key, (0, 0)), key)
                self.assertLessEqual(expected.keys(), got.keys())

    def test_monthly_counts_empty_and_clamped(self):
        rows = monthly("v0-raw")
        months = [(int(r[0]), int(r[1])) for r in rows]
        self.assertEqual(months[0], (2010, 6))  # coverage starts on 2010-06-01, the first Aqua day
        self.assertEqual(months[-1], (2026, 11))  # and ends on 2026-11-14, the last NOAA-20 day
        self.assertEqual(len(months), 198)  # every month in between, once
        self.assertEqual(len(set(months)), 198)
        self.assertEqual(rows[months.index((2021, 5))][2:4], ["0", "0"])  # no fire that month
        self.assertEqual(rows[months.index((2015, 1))][2:4], ["0", "0"])  # no data at all that month
        self.assertEqual(rows[months.index((2010, 7))][4], "modis")
        self.assertEqual(rows[months.index((2021, 3))][4], "viirs")
        # Months are whole: both March fires are on the 10th, before the first day asked for.
        rows = monthly("v0-raw", "2021-03-15", "2021-05-02")
        self.assertEqual([(r[0], r[1], r[3]) for r in rows], [("2021", "3", "2"), ("2021", "4", "0"),
                                                              ("2021", "5", "0")])
        self.assertEqual(monthly("v0-raw", "1990-01-01", "1995-12-31"), [])

    def test_count_error(self):
        rows = monthly("vtest", "2021-08-01", "2021-08-31")
        self.assertEqual(rows, [["2021", "8", "24", "12", "modis", "f", "5", "f"]])
        self.assertEqual(monthly("vtest", "2021-05-01", "2021-05-31")[0][6], "0")  # no MODIS fire, no error
        self.assertEqual({r[6] for r in monthly("v0-raw")}, {None})  # v0-raw has no rows of error

    def test_count_error_viirs(self):
        # Each VIIRS satellite adds its harmonized count times its own rel_error (decision D75). NOAA-20 in
        # November 2026: 2 fires of weight 1 in the polygon, the ladder row n_min 1 gives 0.6, round(1.2) = 1.
        self.assertEqual(monthly("vviirs", "2026-11-01", "2026-11-30"),
                         [["2026", "11", "2", "2", "viirs", "t", "1", "f"]])
        # Suomi NPP keeps rel_error 0: 2 fires in March 2021 add nothing.
        self.assertEqual(monthly("vviirs", "2021-03-01", "2021-03-31"),
                         [["2021", "3", "2", "2", "viirs", "f", "0", "f"]])

    def test_incomplete_and_partial(self):
        vtest = {int(r[1]): r for r in monthly("vtest")}
        self.assertEqual(sorted(vtest), list(range(1, 13)))
        self.assertEqual([m for m, r in vtest.items() if r[7] == "t"], [3])  # 2021-03-15 is a gap day
        self.assertEqual({r[5] for r in vtest.values()}, {"f"})  # vtest's coverage ends on 2021-12-31
        v0 = {(int(r[0]), int(r[1])): r for r in monthly("v0-raw")}
        self.assertEqual([key for key, r in v0.items() if r[5] == "t"], [(2026, 11)])
        self.assertEqual({r[7] for r in v0.values()}, {"f"})

    def test_hotspots_in_rows(self):
        rows = query(f"SELECT * FROM firms.hotspots_in({quote(AOI)}, DATE '1999-01-01', DATE '2030-12-31', "
                     f"'v0-raw', 1000)")
        self.assertEqual(len(rows), sum(int(r[3]) for r in monthly("v0-raw")))
        self.assertEqual(len(rows), 6)
        self.assertEqual([r[2] for r in rows], sorted(r[2] for r in rows))  # by date
        by_date = {r[2]: r for r in rows}
        self.assertEqual(by_date["2010-07-05"], ["50.3", "30.6", "2010-07-05", "1105", "Aqua", "MODIS", "59",
                                                 "12.5", "D", "modis", "330.5", "295.25", "1.1", "1", "6.03", "1"])
        self.assertEqual(by_date["2026-11-05"], ["50.4", "30.7", "2026-11-05", "0028", "N20", "VIIRS", "n",
                                                 "12.5", "N", "viirs", "330.5", "295.25", "0.39", "0.36", "2.0NRT",
                                                 "1"])
        self.assertEqual(sorted((r[4], r[6]) for r in rows if r[2] == "2021-03-10"), [("N", "h"), ("N", "n")])
        # Days are exact and max_rows stops the rows in date order.
        self.assertEqual(query(f"SELECT * FROM firms.hotspots_in({quote(AOI)}, DATE '2021-03-11', "
                               f"DATE '2021-03-31', 'v0-raw', 100)"), [])
        first = query(f"SELECT acq_date FROM firms.hotspots_in({quote(AOI)}, DATE '1999-01-01', "
                      f"DATE '2030-12-31', 'v0-raw', 2)")
        self.assertEqual(first, [["2010-07-05"], ["2010-08-12"]])
        vtest = query(f"SELECT count(*), min(weight), max(weight) FROM firms.hotspots_in({quote(AOI)}, "
                      f"DATE '2021-08-01', DATE '2021-08-31', 'vtest', 1000)")
        self.assertEqual(vtest, [["12", "2", "2"]])

    def test_build_series_gap(self):
        for version, sat, month, day in (("vtest", AQUA, 8, "2021-08"), ("v0-raw", SNPP, 3, "2021-03")):
            with self.subTest(version=version):
                result = psql(f"""
                    BEGIN;
                    DELETE FROM firms.method_weight WHERE version = '{version}' AND satellite = {sat}
                        AND cell2_id = {UA_CELL2} AND calendar_month = {month};
                    SELECT firms.build_series('{version}');
                    ROLLBACK;""")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(str(UA_CELL2), result.stderr)
                self.assertIn(day, result.stderr)
        result = psql("BEGIN; SELECT firms.build_series('vtest'); ROLLBACK;")
        self.assertEqual(result.returncode, 0, result.stderr)

    def map_features(self, bbox: str, zoom: int, first: str, last: str, version: str) -> list[list]:
        return query(f"SELECT * FROM firms.map_features({bbox}, {zoom}, DATE '{first}', DATE '{last}', "
                     f"'{version}', 20000)")

    def test_map_features(self):
        bbox = "30.5, 50.25, 31.0, 50.5"
        points = self.map_features(bbox, 10, "2021-08-01", "2021-08-31", "vtest")
        expected = [f for f in FIRES if f.sat == AQUA and f.day.startswith("2021-08") and
                    30.5 <= f.lon <= 31.0 and 50.25 <= f.lat <= 50.5]
        self.assertEqual(len(points), len(expected))
        self.assertEqual(len(points), 13)
        self.assertEqual({(r[0], r[7], r[10], r[13]) for r in points}, {("point", "Aqua", "2", "0.75")})
        self.assertEqual({tuple(r[3:7]) for r in points}, {(None, None, None, None)})
        points = self.map_features(bbox, 9, "2026-11-01", "2026-11-30", "v0-raw")
        self.assertEqual(sorted((r[8], r[7], r[10], r[13]) for r in points),
                         [("2026-11-05", "N20", "1", None), ("2026-11-06", "N20", "1", None)])
        # Zoom 4 and below: 2-degree squares with the harmonized sums of whole months.
        cells = self.map_features("20, 40, 40, 60", 4, "2021-01-15", "2021-12-01", "vtest")
        n_raw = sum(f.sat == AQUA and f.date.year == 2021 and cell2_id(f.cell) == UA_CELL2 for f in FIRES)
        self.assertEqual(n_raw, 15)
        self.assertEqual(cells, [["cell", "31", "51", "30", "50", "32", "52", None, None, None, None, str(n_raw),
                                  str(2 * n_raw), None]])
        for zoom, step in ((8, 0.25), (7, 0.25), (6, 0.5), (5, 1.0), (4, 2.0), (2, 2.0)):
            with self.subTest(zoom=zoom):
                cells = self.map_features("20, 40, 40, 60", zoom, "2021-01-01", "2021-12-31", "v0-raw")
                self.assertTrue(cells)
                self.assertEqual({(r[0], float(r[5]) - float(r[3]), float(r[6]) - float(r[4])) for r in cells},
                                 {("cell", step, step)})
                self.assertEqual(sum(int(r[11]) for r in cells), 5)  # the Ukrainian Suomi NPP fires of 2021

    def test_map_features_rejects_bad_bbox(self):
        self.assertTrue(self.map_features("-180, -90, 180, 90", 2, "2021-01-01", "2021-12-31", "v0-raw"))
        for bbox in ("31.0, 50.25, 30.5, 50.5", "30.5, 50.25, 30.5, 50.5", "30.5, 50.5, 31.0, 50.25",
                     "-181, 50.25, 31.0, 50.5", "30.5, 50.25, 181, 50.5", "30.5, -91, 31.0, 50.5",
                     "30.5, 50.25, 31.0, 91"):
            with self.subTest(bbox=bbox):
                result = psql(f"SELECT * FROM firms.map_features({bbox}, 10, DATE '2021-08-01', "
                              f"DATE '2021-08-31', 'vtest', 100)")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("firms.map_features: bbox", result.stderr)

    def test_confidence_filter(self):
        def series_count(params: str) -> int:
            result = psql(f"""
                BEGIN;
                UPDATE firms.method SET params = '{params}' WHERE version = 'v0-raw';
                SELECT count(*) FROM firms.v_series_point WHERE version = 'v0-raw';
                ROLLBACK;""")
            self.assertEqual(result.returncode, 0, result.stderr)
            return int(result.stdout.split()[0])

        in_series = [f for f in FIRES if series_weight("v0-raw", f) is not None]
        self.assertEqual(series_count('{"confidence_filter": null}'), len(in_series))
        self.assertEqual(series_count('{}'), len(in_series))
        kept = [f for f in in_series if (f.conf_pct >= 30 if f.conf_pct is not None else f.conf_class in "nh")]
        self.assertEqual(len(in_series), 12)
        self.assertEqual(len(kept), 10)  # MODIS 20 % and VIIRS l go
        self.assertEqual(series_count('{"confidence_filter": {"modis_min_confidence": 30, '
                                      '"viirs_confidence_levels": ["n", "h"]}}'), len(kept))

    def test_unknown_version_and_no_days(self):
        # An unknown version is an error, not a calendar of zeros (review, Important 1).
        for call in (f"firms.monthly_counts({quote(AOI)}, DATE '2020-01-01', DATE '2021-12-31', 'no-such-version')",
                     f"firms.hotspots_in({quote(AOI)}, DATE '2020-01-01', DATE '2021-12-31', 'no-such-version', 10)",
                     "firms.map_features(30.5, 50.25, 31.0, 50.5, 10, DATE '2021-01-01', DATE '2021-12-31', "
                     "'no-such-version', 10)"):
            with self.subTest(call=call[:22]):
                result = psql(f"SELECT * FROM {call}")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("there is no method version 'no-such-version'", result.stderr)
        # A version whose weights cover no day of day_source has no months and no fires.
        result = psql(f"""
            BEGIN;
            INSERT INTO firms.method VALUES ('vnodays', 'no days', '{{"confidence_filter": null}}', now());
            INSERT INTO firms.method_weight VALUES ('vnodays', 1, '2000-11-01', '2002-07-03', {UA_CELL2}, 3, NULL, 1);
            SELECT count(*) FROM firms.monthly_counts({quote(AOI)}, DATE '2000-01-01', DATE '2030-12-31', 'vnodays');
            SELECT count(*) FROM firms.hotspots_in({quote(AOI)}, DATE '2000-01-01', DATE '2030-12-31', 'vnodays', 9);
            ROLLBACK;""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["0", "0"])

    def test_build_series_overlap(self):
        # Rows whose days and day-or-night meet would count a fire twice (review, Minor 1).
        for extra in ("('vtest', 2, '2021-08-01', '2021-08-31', 12705, 8, NULL, 2.0)",
                      "('vtest', 2, '2021-01-01', '2021-12-31', 12705, 8, true, 2.0)"):
            with self.subTest(extra=extra):
                result = psql(f"BEGIN; INSERT INTO firms.method_weight VALUES {extra};"
                              "SELECT firms.build_series('vtest'); ROLLBACK;")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("pairs of weight rows overlap", result.stderr)
                self.assertIn("aqua square 12705 month 8", result.stderr)
        # A day row and a night row instead of the row for both do not meet.
        result = psql(f"""
            BEGIN;
            DELETE FROM firms.method_weight WHERE version = 'vtest' AND satellite = 2 AND cell2_id = {UA_CELL2}
                AND calendar_month = 8;
            INSERT INTO firms.method_weight VALUES ('vtest', 2, '2021-01-01', '2021-12-31', {UA_CELL2}, 8, true, 2.0),
                                                   ('vtest', 2, '2021-01-01', '2021-12-31', {UA_CELL2}, 8, false, 2.0);
            SELECT firms.build_series('vtest');
            SELECT count_raw FROM firms.monthly_counts({quote(AOI)}, DATE '2021-08-01', DATE '2021-08-31', 'vtest');
            ROLLBACK;""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[-1], "12")

    def test_bad_inputs(self):
        # Inputs that cannot mean a zone or a limit are errors, the same way in every function (review, Minor 2).
        point = json.dumps({"type": "Point", "coordinates": [30.6, 50.3]})
        cases = {
            "point zone": f"firms.monthly_counts({quote(point)}, DATE '2021-01-01', DATE '2021-12-31', 'v0-raw')",
            "NULL zone": "firms.monthly_counts(NULL, DATE '2021-01-01', DATE '2021-12-31', 'v0-raw')",
            "NULL zone, CSV": "firms.hotspots_in(NULL, DATE '2021-01-01', DATE '2021-12-31', 'v0-raw', 10)",
            "NULL max_rows": f"firms.hotspots_in({quote(AOI)}, DATE '2021-01-01', DATE '2021-12-31', 'v0-raw', NULL)",
            "NULL zoom": "firms.map_features(20, 40, 40, 60, NULL, DATE '2021-01-01', DATE '2021-12-31', 'v0-raw', 9)",
            "NULL max_points": "firms.map_features(20, 40, 40, 60, 4, DATE '2021-01-01', DATE '2021-12-31', "
                               "'v0-raw', NULL)",
        }
        for name, call in cases.items():
            with self.subTest(name):
                result = psql(f"SELECT * FROM {call}")
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stderr, r"aoi|max_rows|zoom|max_points")
        multi = json.dumps({"type": "MultiPolygon", "coordinates": [[POLYGON]]})
        self.assertEqual(monthly("v0-raw", aoi=multi), monthly("v0-raw"))
        self.assertEqual(query(f"SELECT count(*) FROM firms.hotspots_in({quote(AOI)}, DATE '1999-01-01', "
                               f"DATE '2030-12-31', 'v0-raw', 0)"), [["0"]])


class TestRestore(unittest.TestCase):
    def test_restore_ok(self):
        self.assertEqual(FIRST_RESTORE.returncode, 0, FIRST_RESTORE.stdout + FIRST_RESTORE.stderr)
        self.assertEqual(FIRST_RESTORE.stdout.splitlines()[-1], "OK")
        expected = [[p.name, hashlib.sha256(p.read_bytes()).hexdigest()]
                    for p in sorted((FIRMSDB / "sql").glob("*.sql"))]
        self.assertEqual([p[0] for p in expected], ["00_extensions.sql", "01_tables.sql", "02_functions.sql",
                                                    "03_indexes.sql"])
        self.assertEqual(query("SELECT file, sha256 FROM firms.schema_migrations ORDER BY file"), expected)
        self.assertEqual(scalar("SELECT count(*) FROM firms.grid_cell"), "1036800")
        self.assertEqual(scalar("SELECT count(*) FROM firms.hotspot_static_2021"), "2")  # from two files
        # Nothing new in public: restore.sh only adds rows to public.ingest_runs.
        self.assertEqual(query("SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace "
                               "ORDER BY 1"), PUBLIC_BEFORE)

    def test_ingest_runs(self):
        rows = query("""SELECT s.code, r.status, r.period_from, r.period_to, r.records_count, r.error IS NULL,
                               r.started_at <= r.finished_at
                        FROM public.ingest_runs r JOIN public.data_sources s ON s.id = r.data_source_id
                        WHERE r.id <= 3 ORDER BY s.code""")
        # records_count: the rows loaded from the source's files, fires and non-fires.
        self.assertEqual(rows, [["MODIS_SP", "success", "2010-06-01", "2021-12-31", "22", "t", "t"],
                                ["VIIRS_NOAA20_NRT", "success", "2026-11-01", "2026-11-14", "3", "t", "t"],
                                ["VIIRS_SNPP_SP", "success", "2021-01-01", "2021-12-31", "7", "t", "t"]])

    def test_dataset_info(self):
        info = json.loads(scalar("SELECT firms.dataset_info()"))
        self.assertEqual(sorted(info), ["built_at", "countries", "name", "scope"])
        self.assertEqual((info["name"], info["scope"], info["countries"]),
                         ("test-sql", "countries", ["Australia", "Brazil", "Ukraine"]))
        method = json.loads(scalar("SELECT firms.method_info('v0-raw')"))
        self.assertEqual(sorted(method), ["created_at", "label", "params", "version"])
        self.assertEqual(method["version"], "v0-raw")
        self.assertIn("confidence_filter", method["params"])
        self.assertIsNone(method["params"]["confidence_filter"])
        self.assertIsNone(scalar("SELECT firms.method_info('no-such-version')"))

    def test_grid_functions(self):
        cases = [((-9000000, -18000000), 0), ((9000000, 18000000), 1036799), ((0, 0), 519120),
                 ((5045000, 3050000), 808682)]
        for (lat, lon), cid in cases:
            with self.subTest(lat=lat, lon=lon):
                self.assertEqual(query(f"SELECT firms.cell_id_e5({lat}, {lon}), "
                                       f"firms.cell_id({lat / 1e5}::float8, {lon / 1e5}::float8)"),
                                 [[str(cid), str(cid)]])
        self.assertEqual(scalar("SELECT firms.cell2_id(808682)"), "12705")
        self.assertEqual(query("SELECT ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g), ST_SRID(g), "
                               "ST_GeometryType(g) FROM firms.cell_geom(808682) g"),
                         [["30.5", "50.25", "30.75", "50.5", "4326", "ST_Polygon"]])
        self.assertEqual(scalar("SELECT ST_Equals(geom, firms.cell_geom(808682)) FROM firms.grid_cell "
                                "WHERE cell_id = 808682"), "t")
        self.assertIsNone(scalar("SELECT firms.cell_id_e5(NULL, 0)"))


COUNTS = """SELECT (SELECT count(*) FROM firms.hotspot), (SELECT count(*) FROM firms.hotspot_static),
                   (SELECT count(*) FROM firms.day_source), (SELECT count(*) FROM firms.load_batch),
                   (SELECT count(*) FROM firms.cell_month_series), (SELECT count(*) FROM firms.method_month),
                   (SELECT count(*) FROM firms.method_weight), (SELECT count(*) FROM firms.dataset)"""


class TestRestoreAgain(unittest.TestCase):
    def test_package_replaces_what_it_carries(self):
        before = query(COUNTS)
        # Left by an older package: a gap day of v0-raw, which this package carries without gaps, and a function.
        query("INSERT INTO firms.method_gap VALUES ('v0-raw', '2021-03-02');"
              "CREATE FUNCTION firms.left_over() RETURNS int LANGUAGE sql RETURN 1;")
        result = restore("--jobs", "3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], "OK")
        self.assertEqual(query(COUNTS), before)
        self.assertEqual(scalar("SELECT count(*) FROM firms.method_gap WHERE version = 'v0-raw'"), "0")
        self.assertIsNone(scalar("SELECT to_regprocedure('firms.left_over()')"))

    def test_objects_outside_firms_stop_the_restore(self):
        # The application's objects over firms functions and views are not dropped (review, Important 2).
        query("CREATE VIEW public.app_cov AS SELECT * FROM firms.coverage('v0-raw');"
              "CREATE FUNCTION public.app_square(c int) RETURNS int LANGUAGE sql RETURN firms.cell2_id(c);")
        try:
            result = restore("--jobs", "3")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("objects outside the schema firms depend on its functions, views or their row types",
                          result.stderr)
            self.assertIn("app_cov", result.stderr)
            self.assertIn("app_square", result.stderr)
            self.assertEqual(query("SELECT to_regclass('public.app_cov') IS NOT NULL, "
                                   "to_regprocedure('public.app_square(int)') IS NOT NULL"), [["t", "t"]])
        finally:
            query("DROP VIEW IF EXISTS public.app_cov; DROP FUNCTION IF EXISTS public.app_square(int);")

    def test_row_types_outside_firms_stop_the_restore(self):
        # A firms view brings a row type and its array; what uses them outside firms counts too (re-review,
        # Important 2).
        query("CREATE FUNCTION public.p_rowtype() RETURNS SETOF firms.v_series_point LANGUAGE sql "
              "AS 'SELECT * FROM firms.v_series_point LIMIT 0';"
              "CREATE FUNCTION public.p_arr(firms.v_series_point[]) RETURNS int LANGUAGE sql AS 'SELECT 1';"
              "CREATE TABLE public.app_t (c firms.v_series_point);")
        present = ("SELECT to_regprocedure('public.p_rowtype()') IS NOT NULL, "
                   "to_regprocedure('public.p_arr(firms.v_series_point[])') IS NOT NULL, "
                   "(SELECT count(*) FROM pg_attribute WHERE attrelid = 'public.app_t'::regclass AND attname = 'c')")
        try:
            result = restore("--jobs", "3")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("objects outside the schema firms depend on its functions, views or their row types",
                          result.stderr)
            for name in ("function p_rowtype()", "function p_arr(firms.v_series_point[])", "column c of table app_t"):
                self.assertIn(name, result.stderr)
            self.assertEqual(query(present), [["t", "t", "1"]])
        finally:
            query("DROP FUNCTION IF EXISTS public.p_rowtype(); DROP FUNCTION IF EXISTS public.p_arr(firms.v_series_point[]);"
                  "DROP TABLE IF EXISTS public.app_t;")

    def test_journal_that_refuses_the_counts_is_marked_failed(self):
        # The rows do not stay running when the application's table refuses the update (re-review, Minor 2).
        query("CREATE FUNCTION public.no_success() RETURNS trigger LANGUAGE plpgsql "
              "AS $$ BEGIN RAISE EXCEPTION 'the app refuses success'; END $$;"
              "CREATE TRIGGER no_success BEFORE UPDATE ON public.ingest_runs FOR EACH ROW "
              "WHEN (NEW.status = 'success') EXECUTE FUNCTION public.no_success();")
        runs = int(scalar("SELECT coalesce(max(id), 0) FROM public.ingest_runs"))
        try:
            result = restore("--jobs", "3")
        finally:
            query("DROP TRIGGER no_success ON public.ingest_runs; DROP FUNCTION public.no_success();")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], "OK")
        self.assertIn("public.ingest_runs did not take the counts", result.stderr)
        self.assertEqual({tuple(r) for r in query(f"SELECT status, error LIKE '%the app refuses success%' "
                                                  f"FROM public.ingest_runs WHERE id > {runs}")}, {("failed", "t")})

    def test_changed_tables_file_stops_the_restore(self):
        # CREATE TABLE IF NOT EXISTS would keep the old tables (review, Minor 5).
        sha = hashlib.sha256((FIRMSDB / "sql" / "01_tables.sql").read_bytes()).hexdigest()
        query("UPDATE firms.schema_migrations SET sha256 = 'older' WHERE file = '01_tables.sql'")
        try:
            result = restore("--jobs", "3")
        finally:
            query(f"UPDATE firms.schema_migrations SET sha256 = '{sha}' WHERE file = '01_tables.sql'")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("schema/01_tables.sql differs from the file the tables of this database were made with",
                      result.stderr)

    def test_part_not_in_package_is_reported(self):
        # The name of the part comes from the catalog and needs quoting in SQL (review, Minor 6).
        query("""CREATE TABLE firms.hotspot_2019 PARTITION OF firms.hotspot
                     FOR VALUES FROM ('2019-01-01') TO ('2020-01-01') PARTITION BY LIST (satellite);
                 CREATE TABLE firms."hotspot_2019_Old" PARTITION OF firms.hotspot_2019 FOR VALUES IN (1);
                 INSERT INTO firms."hotspot_2019_Old"
                     VALUES ('2019-05-01', 1200, 1, 808682, 5030000, 3060000, 1, 1, 1, 1, 1, 'n', 50, true, false, 1);""")
        runs = int(scalar("SELECT coalesce(max(id), 0) FROM public.ingest_runs"))
        try:
            result = restore("--jobs", "3")
        finally:
            query("DROP TABLE firms.hotspot_2019")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("MISMATCH hotspot_2019_Old: not in manifest.json, 1 rows in the database",
                      result.stdout.splitlines())
        self.assertEqual({r[0] for r in query(f"SELECT status FROM public.ingest_runs WHERE id > {runs}")},
                         {"failed"})


class TestRestoreOnlyYear(unittest.TestCase):
    def test_only_year(self):
        before = query(COUNTS)
        months = monthly("v0-raw")
        runs = int(scalar("SELECT coalesce(max(id), 0) FROM public.ingest_runs"))
        result = restore("--only-year", "2021", "--jobs", "2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], "OK")
        self.assertEqual(query(COUNTS), before)
        self.assertEqual(monthly("v0-raw"), months)
        self.assertEqual(query(f"SELECT s.code, r.status, r.period_from, r.period_to FROM public.ingest_runs r "
                               f"JOIN public.data_sources s ON s.id = r.data_source_id WHERE r.id > {runs} "
                               f"ORDER BY s.code"),
                         [["MODIS_SP", "success", "2021-01-01", "2021-12-31"],
                          ["VIIRS_SNPP_SP", "success", "2021-01-01", "2021-12-31"]])


class TestRestoreYearPackage(unittest.TestCase):
    """A package of one year over the database of the full package (review, Minor 3 and 4). It runs last: it
    leaves the database with the one-year package's batch 3 and built_at."""

    @classmethod
    def setUpClass(cls):
        # Suomi NPP's file reaches into 2022 and claims more fires than its rows of 2021.
        variant_package("/pkg-2021",
                        manifest={"name": "test-sql-2021", "built_at": "2026-11-16T08:00:00Z", "scope": "world",
                                  "countries": None},
                        files={"data/load_batch.tsv.gz": load_batch_rows({3: {"date_to": "2022-03-31",
                                                                              "rows_fire": 50}})})
        # Left by earlier runs: a part of 2021 the package does not have, and a version the package does not carry
        # whose weights miss squares with fires.
        query(f"""CREATE TABLE firms.hotspot_2021_terra PARTITION OF firms.hotspot_2021 FOR VALUES IN (1);
                  INSERT INTO firms.hotspot_2021_terra
                      VALUES ('2021-05-01', 1200, 1, 808682, 5030000, 3060000, 1, 1, 1, 1, 1, 'n', 50, true, false, 1);
                  INSERT INTO firms.method VALUES ('vold', 'an older version', '{{}}', now());
                  INSERT INTO firms.method_weight VALUES ('vold', 2, '2021-01-01', '2021-12-31', {UA_CELL2}, 3, NULL, 1);""")
        cls.addClassCleanup(query, "DELETE FROM firms.method_weight WHERE version = 'vold';"
                                   "DELETE FROM firms.method WHERE version = 'vold';"
                                   "DROP TABLE IF EXISTS firms.hotspot_2021_terra;")
        cls.runs = int(scalar("SELECT coalesce(max(id), 0) FROM public.ingest_runs"))
        cls.result = restore("--only-year", "2021", "--jobs", "2", package="/pkg-2021")
        cls.runs_after = int(scalar("SELECT coalesce(max(id), 0) FROM public.ingest_runs"))

    def test_run_ends_ok_with_a_warning(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertEqual(self.result.stdout.splitlines()[-1], "OK")
        self.assertIn("warning: the series of vold, which the package does not carry, was not rebuilt",
                      self.result.stderr)

    def test_part_of_the_year_missing_from_the_package_is_emptied(self):
        self.assertIn("  emptied hotspot_2021_terra: the package has no file of it", self.result.stdout.splitlines())
        self.assertEqual(scalar("SELECT count(*) FROM firms.hotspot_2021_terra"), "0")

    def test_dataset_keeps_the_full_package(self):
        info = json.loads(scalar("SELECT firms.dataset_info()"))
        self.assertEqual(info, {"name": "test-sql", "scope": "countries",
                                "countries": ["Australia", "Brazil", "Ukraine"],
                                "built_at": "2026-11-16T08:00:00+00:00"})
        updates = json.loads(scalar("SELECT manifest -> 'updates' FROM firms.dataset"))
        self.assertIn(("test-sql-2021", 2021), [(u["name"], u["only_year"]) for u in updates])

    def test_journal_counts_the_rows_of_the_year(self):
        # 2021 holds 16 fires and 1 non-fire of the MODIS file, 6 and 1 of the Suomi NPP one, whatever the batch
        # rows claim.
        self.assertEqual(query(f"SELECT s.code, r.status, r.period_from, r.period_to, r.records_count "
                               f"FROM public.ingest_runs r JOIN public.data_sources s ON s.id = r.data_source_id "
                               f"WHERE r.id > {self.runs} AND r.id <= {self.runs_after} ORDER BY s.code"),
                         [["MODIS_SP", "success", "2021-01-01", "2021-12-31", "17"],
                          ["VIIRS_SNPP_SP", "success", "2021-01-01", "2022-03-31", "7"]])

    def test_older_package_keeps_the_newer_built_at(self):
        # greatest(), not the last package's built_at (re-review, Minor 3).
        variant_package("/pkg-older", manifest={"name": "test-sql-older", "built_at": "2026-11-01T00:00:00Z"})
        result = restore("--only-year", "2021", "--jobs", "2", package="/pkg-older")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(scalar("SELECT firms.dataset_info()"))["built_at"], "2026-11-16T08:00:00+00:00")
        updates = json.loads(scalar("SELECT manifest -> 'updates' FROM firms.dataset"))
        self.assertEqual(updates[-1]["name"], "test-sql-older")

    def test_version_missing_from_the_database_stops_a_year_run(self):
        # A run of one year loads no method tables, so it cannot build a new version (re-review, Minor 1).
        variant_package("/pkg-new-version",
                        files={"data/method/vnew/method.tsv.gz": [("vnew", "new", "{}", "2026-11-16 00:00:00+00")]},
                        entries=[{"table": "method", "version": "vnew", "file": "data/method/vnew/method.tsv.gz",
                                  "rows": 1}])
        result = restore("--only-year", "2021", "--jobs", "2", package="/pkg-new-version")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("version vnew is not in the database; run a full restore", result.stderr)
        self.assertEqual(scalar("SELECT count(*) FROM firms.method WHERE version = 'vnew'"), "0")


if __name__ == "__main__":
    unittest.main()
