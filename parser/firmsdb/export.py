"""The dump package of the web database, written straight from the raw FIRMS files.

build_package reads the yearly archive zips and the CSV files of the area API, puts every point once into the part of
firms.hotspot or firms.hotspot_static it belongs to, and writes the package of the shared package format:
manifest.json, restore.sh, README.md, schema/*.sql and the gzip COPY files under data/. The steps, in this order:

1. the files, their load_batch ids, and the file that holds each day of each family (firmsdb.precedence), from the
   zips and the API files together, so that a zip keeps every day of its year;
2. the zips, in parallel: each writes its parts hotspot/<year>_<satellite> and hotspot_static/<year>_<family> and
   returns the cells of its points of any type and the first and last day of each satellite;
3. the footprint of the archive, firms.archive_cell: the cells of every zip, also of the zips outside the years of
   the package, and of the members of the chosen countries only for a slice of countries;
4. the API files, in parallel by family: a file gives its rows of the days it holds; a row outside the footprint is
   dropped from a slice of countries and set aside with type 3 in a package of the world;
5. each part sorted by (cell_id, acq_date, acq_time) with numpy.lexsort and written by gzip with mtime 0;
6. day_source: for a zip every day from the first to the last with a point of the satellite, for an API file every
   day it holds, for each satellite of its family;
7. the tables of each method version, satellite, load_batch and archive_cell, copies of firmsdb/sql/*.sql,
   restore.sh and package_readme.md, then manifest.json.

The package is built in <out>.partial and replaces <out> only when it is complete. The same raw files give the same
bytes in data/.
"""

from __future__ import annotations

import gzip
import json
import logging
import math
import re
import shutil
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import Executor, ProcessPoolExecutor, as_completed
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final, NamedTuple

import numpy as np

from firms.grid import cell_id_e5

from .method import TABLES, V0_RAW, read_version, v0_raw
from .precedence import FAMILY_INDEX, assign_batches, winners
from .rows import CODES, Detection, parse_row, static_type, to_e5
from .sources import SourceFile, archive_members, list_api, list_archive, read_rows

log = logging.getLogger(__name__)

FORMAT: Final[int] = 1  # the version of the package format in manifest.json
_HERE: Final[Path] = Path(__file__).resolve().parent

#: The rows of firms.satellite: id, code, the FIRMS satellite value, instrument, label.
SATELLITE_ROWS: Final[tuple[tuple[int, str, str, str, str], ...]] = (
    (1, "terra", "Terra", "MODIS", "Terra"),
    (2, "aqua", "Aqua", "MODIS", "Aqua"),
    (3, "snpp", "N", "VIIRS", "Suomi NPP"),
    (4, "noaa20", "N20", "VIIRS", "NOAA-20"),
    (5, "noaa21", "N21", "VIIRS", "NOAA-21"),
)
#: The satellites of each family of files.
FAMILY_SATELLITES: Final[dict[str, tuple[int, ...]]] = {"modis": (1, 2), "snpp": (3,), "noaa20": (4,),
                                                        "noaa21": (5,)}

_CELLS: Final[int] = 1440 * 720  # the 0.25-degree cells of firms.grid
_CHUNK: Final[int] = 65_536  # rows gathered or written at a time
_COMPRESSLEVEL: Final[int] = 6
_NULL: Final[str] = r"\N"
_VERSION_NAME: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_TSV_ESCAPES: Final[dict[int, str]] = str.maketrans({"\\": "\\\\", "\t": "\\t", "\n": "\\n", "\r": "\\r"})

#: One row of a part: the columns of firms.hotspot, then the type of firms.hotspot_static (0 in firms.hotspot).
_ROW: Final[np.dtype] = np.dtype([
    ("acq_date", "<i4"),  # date.toordinal()
    ("acq_time", "<i2"),
    ("satellite", "i1"),
    ("cell_id", "<i4"),
    ("lat_e5", "<i4"),
    ("lon_e5", "<i4"),
    ("frp", "<f8"),  # float64 as parsed, so that repr writes the number the file wrote
    ("brightness", "<f8"),
    ("brightness_2", "<f8"),
    ("scan", "<f8"),
    ("track", "<f8"),
    ("conf_class", "u1"),  # ord("l"), ord("n") or ord("h")
    ("conf_pct", "<i2"),  # -1 for NULL
    ("is_day", "?"),
    ("is_nrt", "?"),
    ("batch_id", "<i4"),
    ("type", "i1"),
])


def build_package(out: Path, *, archive_dir: Path, api_dir: Path, harmonization_dir: Path, methods: list[str],
                  countries: list[str] | None, years: tuple[int, int] | None, jobs: int, name: str) -> dict:
    """Write the dump package into out and return its manifest.

    methods are the method versions the package carries: v0-raw, or a folder of harmonization_dir. countries (the
    names of the archive members, such as Ukraine) make a slice of those countries; None makes the world. years
    (first, last) keep the points of those years only; the footprint still comes from every zip. jobs is the number
    of processes. A country that no zip has, a method version without its files and a package folder that holds
    something else than a package raise before any work.
    """
    out = Path(out)
    methods = list(dict.fromkeys(methods))
    countries = None if countries is None else sorted(set(countries))
    _check(out, methods=methods, countries=countries, years=years, jobs=jobs, name=name)
    zips = list_archive(archive_dir, None)
    package_zips = [src for src in zips if _in_years(src.year, years)]
    api_files = list_api(api_dir, years)
    batches = assign_batches(package_zips + api_files)
    win = winners(zips + api_files)
    members = _members(zips, countries)
    for version in methods:
        if version != V0_RAW:
            _check_version(harmonization_dir / version)

    work = _start(out)
    try:
        with ProcessPoolExecutor(jobs) if jobs > 1 else nullcontext() as pool:
            zip_results = _run(pool, _export_zip, [
                _ZipTask(src, batches.get(src.path, 0), tuple(members[src.path]),
                         work if src.path in batches else None) for src in zips])
            footprint = np.zeros(_CELLS, dtype=bool)
            for result in zip_results:
                footprint[result.cells] = True
            if api_files and not footprint.any():
                raise ValueError("the archive has no point, so the API files have no footprint to be read against; "
                                 f"see {archive_dir}")
            api_results = _run(pool, _export_api, [
                _ApiTask(family, tuple(files), tuple(batches[src.path] for src in files),
                         tuple(_kept_days(src, win, years) for src in files), footprint, countries is not None, work)
                for family, files in _by_family(api_files).items()])
        parts = [part for result in zip_results + api_results for part in result.parts]
        stats = {result.path: result.stats for result in zip_results if result.path in batches}
        for result in api_results:
            stats.update(result.stats)
        entries = _write_tables(work, package_zips, api_files, batches, win, years, zip_results, footprint, stats)
        entries += _part_entries(parts)
        for version in methods:
            entries += _write_method(work, version, harmonization_dir)
        _copy_package_files(work)
        part_years = sorted({part.year for part in parts})
        manifest = {
            "format": FORMAT,
            "name": name,
            "built_at": _iso(datetime.now(UTC).replace(microsecond=0)),
            "scope": "world" if countries is None else "countries",
            "countries": countries,
            "years": [part_years[0], part_years[-1]] if part_years else None,
            "methods": methods,
            "files": entries,
            "sources": [{"file": _raw_name(src), "size": src.size, "mtime": _iso(src.mtime.replace(microsecond=0))}
                        for src in sorted(zips + api_files, key=_raw_name)],
        }
        (work / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
        _finish(work, out)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return manifest


# --- what the workers do --------------------------------------------------------------------------------------


@dataclass
class _Stats:
    """What the package holds from one raw file: its row of firms.load_batch."""

    versions: set[str] = field(default_factory=set)  # the FIRMS version values of its rows
    first: date | None = None
    last: date | None = None
    rows_fire: int = 0
    rows_static: int = 0
    members: int | None = None  # the country members read from a zip; None for an API file

    def add(self, d: Detection, version: str, kind: int | None) -> None:
        self.versions.add(version)
        if self.first is None or d.acq_date < self.first:
            self.first = d.acq_date
        if self.last is None or d.acq_date > self.last:
            self.last = d.acq_date
        if kind is None:
            self.rows_fire += 1
        else:
            self.rows_static += 1


class _Part(NamedTuple):
    """One file of a part: hotspot/<year>_<satellite code> or hotspot_static/<year>_<family>."""

    table: str
    year: int
    name: str  # the satellite code of a hotspot part, the family of a hotspot_static part
    rows: int

    @property
    def file(self) -> str:
        return f"data/{self.table}/{self.year}_{self.name}.tsv.gz"


@dataclass(frozen=True)
class _ZipTask:
    src: SourceFile
    batch_id: int
    members: tuple[str, ...]
    out: Path | None  # the package folder; None for a zip outside the years, read for the footprint only


class _ZipResult(NamedTuple):
    path: Path
    cells: np.ndarray  # the cells with a point of any type, sorted
    spans: dict[int, tuple[date, date]]  # the first and last day with a point of each satellite
    stats: _Stats
    parts: list[_Part]


@dataclass(frozen=True)
class _ApiTask:
    family: str
    files: tuple[SourceFile, ...]
    batch_ids: tuple[int, ...]
    kept: tuple[frozenset[date], ...]  # the days each file gives to the package
    footprint: np.ndarray  # True for a cell of firms.archive_cell
    countries: bool  # a slice of countries: a row outside the footprint is dropped
    out: Path


class _ApiResult(NamedTuple):
    stats: dict[Path, _Stats]
    parts: list[_Part]


def _export_zip(task: _ZipTask) -> _ZipResult:
    """Read the members of one zip, write its parts unless it is read for the footprint only."""
    src = task.src
    cells = np.zeros(_CELLS, dtype=bool)
    spans: dict[int, list[int]] = {}
    stats = _Stats(members=len(task.members))
    parts = None if task.out is None else _Parts(task.out)
    for member in task.members:
        for row in read_rows(src, member):
            d = parse_row(row, is_nrt=False, batch_id=task.batch_id)
            _check_family(d, src, member)
            if d.acq_date.year != src.year:
                raise ValueError(f"{src.path}: {member}: a row of {d.acq_date} in the zip of {src.year}")
            cells[d.cell_id] = True
            day = d.acq_date.toordinal()
            span = spans.setdefault(d.satellite, [day, day])
            span[0], span[1] = min(span[0], day), max(span[1], day)
            if parts is not None:
                kind = static_type(d, True)  # every archive row is in the footprint it makes
                parts.add(d, src.family, kind)
                stats.add(d, row["version"], kind)
    return _ZipResult(src.path, np.flatnonzero(cells),
                      {sat: (date.fromordinal(a), date.fromordinal(b)) for sat, (a, b) in spans.items()}, stats,
                      [] if parts is None else parts.write())


def _export_api(task: _ApiTask) -> _ApiResult:
    """Read the API files of one family, write the parts of the rows of the days each file gives."""
    parts = _Parts(task.out)
    results: dict[Path, _Stats] = {}
    for src, batch_id, kept in zip(task.files, task.batch_ids, task.kept):
        stats = results[src.path] = _Stats()
        if not kept:
            continue
        # The days of the file's name, as FIRMS writes acq_date, and whether the package takes them from this file.
        days = {day.isoformat(): day in kept for day in _api_days(src)}
        for row in read_rows(src):
            keep = days.get(row["acq_date"])
            if keep is None:
                raise ValueError(f"{src.path}: acq_date {row['acq_date']!r} is not a day of the file's name")
            if not keep:
                continue
            if task.countries and not task.footprint[cell_id_e5(to_e5(row["latitude"]), to_e5(row["longitude"]))]:
                continue  # outside the countries: no need to read the rest of the row
            d = parse_row(row, is_nrt=src.is_nrt, batch_id=batch_id)
            _check_family(d, src, None)
            kind = static_type(d, bool(task.footprint[d.cell_id]))
            parts.add(d, src.family, kind)
            stats.add(d, row["version"], kind)
    return _ApiResult(results, parts.write())


def _check_family(d: Detection, src: SourceFile, member: str | None) -> None:
    if d.satellite not in FAMILY_SATELLITES[src.family]:
        where = f"{src.path}: {member}" if member else str(src.path)
        raise ValueError(f"{where}: a row of {CODES[d.satellite]} in a file of {src.family}")


class _Parts:
    """The rows of the parts one worker writes, gathered in numpy chunks to keep the memory of a big zip low."""

    def __init__(self, out: Path) -> None:
        self.out = out
        self._chunks: dict[tuple[str, int, str], list[np.ndarray]] = {}
        self._pending: dict[tuple[str, int, str], list[tuple]] = {}

    def add(self, d: Detection, family: str, kind: int | None) -> None:
        """Add a fire (kind None) to its hotspot part, or a point of hotspot_static type kind to its part."""
        part = ("hotspot", d.acq_date.year, CODES[d.satellite]) if kind is None else (
            "hotspot_static", d.acq_date.year, family)
        pending = self._pending.setdefault(part, [])
        pending.append((d.acq_date.toordinal(), d.acq_time, d.satellite, d.cell_id, d.lat_e5, d.lon_e5, d.frp,
                        d.brightness, d.brightness_2, d.scan, d.track, ord(d.conf_class),
                        -1 if d.conf_pct is None else d.conf_pct, d.is_day, d.is_nrt, d.batch_id, kind or 0))
        if len(pending) >= _CHUNK:
            self._chunks.setdefault(part, []).append(np.array(pending, dtype=_ROW))
            pending.clear()

    def write(self) -> list[_Part]:
        """Sort and write every part; the rows are let go part by part."""
        written = []
        for part in sorted(set(self._chunks) | set(self._pending)):
            chunks = self._chunks.pop(part, [])
            pending = self._pending.pop(part, [])
            if pending:
                chunks.append(np.array(pending, dtype=_ROW))
            rows = np.empty(sum(len(chunk) for chunk in chunks), dtype=_ROW)
            start = 0
            while chunks:  # each chunk is let go once copied, so the part never takes twice its memory
                chunk = chunks.pop(0)
                rows[start:start + len(chunk)] = chunk
                start += len(chunk)
            table, year, name = part
            written.append(_Part(table, year, name, _write_part(self.out, _Part(table, year, name, 0).file, rows,
                                                                static=table == "hotspot_static")))
        return written


def _write_part(out: Path, rel: str, rows: np.ndarray, *, static: bool) -> int:
    order = np.lexsort((rows["acq_time"], rows["acq_date"], rows["cell_id"]))  # the last key sorts first
    with _gzip(out / rel) as handle:
        for start in range(0, len(order), _CHUNK):
            handle.write(_part_lines(rows[order[start:start + _CHUNK]], static).encode())
    return len(rows)


def _part_lines(rows: np.ndarray, static: bool) -> str:
    """The COPY text lines of rows of a part."""
    days = rows["acq_date"].tolist()
    day_text = {day: date.fromordinal(day).isoformat() for day in set(days)}
    columns = [[day_text[day] for day in days]]
    columns += [list(map(str, rows[name].tolist())) for name in ("acq_time", "satellite", "cell_id", "lat_e5",
                                                                 "lon_e5")]
    columns += [list(map(repr, rows[name].tolist())) for name in ("frp", "brightness", "brightness_2", "scan",
                                                                  "track")]
    columns.append(list(map(chr, rows["conf_class"].tolist())))
    columns.append([_NULL if pct < 0 else str(pct) for pct in rows["conf_pct"].tolist()])
    columns += [["t" if value else "f" for value in rows[name].tolist()] for name in ("is_day", "is_nrt")]
    columns.append(list(map(str, rows["batch_id"].tolist())))
    if static:
        columns.append(list(map(str, rows["type"].tolist())))
    return "".join([line + "\n" for line in map("\t".join, zip(*columns))])


# --- the steps of build_package -------------------------------------------------------------------------------


def _check(out: Path, *, methods: list[str], countries: list[str] | None, years: tuple[int, int] | None, jobs: int,
           name: str) -> None:
    if not out.name:
        raise ValueError(f"{out} is not a folder for a package")
    if not name:
        raise ValueError("the package needs a name")
    if jobs < 1:
        raise ValueError(f"jobs {jobs}: at least 1")
    if years is not None and years[0] > years[1]:
        raise ValueError(f"years {years[0]}-{years[1]}: the first year is after the last")
    if countries is not None and (not countries or not all(countries)):
        raise ValueError("countries: at least one name, and no empty name")
    for version in methods:
        if _VERSION_NAME.fullmatch(version) is None:
            raise ValueError(f"method version {version!r}: letters, digits, '.', '_' and '-', starting with a letter "
                             "or digit")


def _check_version(folder: Path) -> None:
    """Fail before the long work when a method version lacks its files; read_version reads them at the end."""
    for name in ("method.json",) + tuple(f"{table}.csv" for table in TABLES[1:]):
        if not (folder / name).is_file():
            raise FileNotFoundError(f"{folder / name}: no such file of the method version {folder.name}")


def _in_years(year: int | None, years: tuple[int, int] | None) -> bool:
    return years is None or (year is not None and years[0] <= year <= years[1])


def _members(zips: list[SourceFile], countries: list[str] | None) -> dict[Path, list[str]]:
    """The members each zip gives to the package. Raises ValueError for a country that no zip has."""
    if countries is None:
        return {src.path: archive_members(src, None) for src in zips}
    members: dict[Path, list[str]] = {src.path: [] for src in zips}
    unknown = []
    for country in countries:
        found = False
        for src in zips:
            names = archive_members(src, [country])
            members[src.path] += names
            found = found or bool(names)
        if not found:
            unknown.append(country)
    if unknown:
        raise ValueError(f"no zip has a member of these countries: {', '.join(unknown)} (the names are those of the "
                         "members <prefix>_<year>_<Country>.csv, such as Russian_Federation)")
    return {path: sorted(names) for path, names in members.items()}


def _by_family(files: list[SourceFile]) -> dict[str, list[SourceFile]]:
    families: dict[str, list[SourceFile]] = {}
    for src in sorted(files, key=lambda src: src.path):
        families.setdefault(src.family, []).append(src)
    return dict(sorted(families.items(), key=lambda item: FAMILY_INDEX[item[0]]))


def _api_days(src: SourceFile) -> list[date]:
    """The days of an API file, from its name."""
    if src.first_day is None or src.days is None:
        raise ValueError(f"{src.path}: not an API file")
    return [src.first_day + timedelta(days=n) for n in range(src.days)]


def _kept_days(src: SourceFile, win: dict[tuple[str, date], Path], years: tuple[int, int] | None) -> frozenset[date]:
    """The days the package takes from an API file: those it holds in the years."""
    return frozenset(day for day in _api_days(src) if win.get((src.family, day)) == src.path
                     and _in_years(day.year, years))


def _run(pool: Executor | None, work: Callable, tasks: list) -> list:
    """The results of work on each task, in the order of the tasks; the bigger files start first."""
    results: list = [None] * len(tasks)
    order = sorted(range(len(tasks)), key=lambda i: -_task_size(tasks[i]))
    if pool is None:
        for i in order:
            results[i] = work(tasks[i])
            _log_done(tasks[i])
        return results
    futures = {pool.submit(work, tasks[i]): i for i in order}
    try:
        for future in as_completed(futures):
            results[futures[future]] = future.result()
            _log_done(tasks[futures[future]])
    except BaseException:
        for future in futures:
            future.cancel()
        raise
    return results


def _task_size(task: _ZipTask | _ApiTask) -> int:
    return task.src.size if isinstance(task, _ZipTask) else sum(src.size for src in task.files)


def _log_done(task: _ZipTask | _ApiTask) -> None:
    if isinstance(task, _ZipTask):
        log.info("%s %s", task.src.path.name, "read" if task.out is not None else "read for the footprint")
    else:
        log.info("%s: %d API files read", task.family, len(task.files))


def _write_tables(out: Path, package_zips: list[SourceFile], api_files: list[SourceFile], batches: dict[Path, int],
                  win: dict[tuple[str, date], Path], years: tuple[int, int] | None, zip_results: list[_ZipResult],
                  footprint: np.ndarray, stats: dict[Path, _Stats]) -> list[dict]:
    """Write satellite, load_batch, day_source and archive_cell; return their manifest entries."""
    days = []
    for result in zip_results:
        if result.path in batches:
            for satellite, (first, last) in result.spans.items():
                days += [(satellite, first + timedelta(days=n), False, batches[result.path])
                         for n in range((last - first).days + 1)]
    api = {src.path: src for src in api_files}
    for (family, day), path in win.items():
        if path in api and _in_years(day.year, years):  # the days of the zips come from their points, above
            days += [(satellite, day, api[path].is_nrt, batches[path]) for satellite in FAMILY_SATELLITES[family]]
    days.sort(key=lambda row: (row[0], row[1]))
    for previous, current in zip(days, days[1:]):
        if previous[:2] == current[:2]:
            raise ValueError(f"satellite {previous[0]} on {previous[1]} is held by two files")
    batch_rows = [(batches[src.path], src.source_code, src.is_nrt, _raw_name(src), stats[src.path].members,
                   src.size, src.mtime, sorted(stats[src.path].versions) or None, stats[src.path].first,
                   stats[src.path].last, stats[src.path].rows_fire, stats[src.path].rows_static)
                  for src in sorted(package_zips + api_files, key=lambda src: batches[src.path])]
    tables = [("satellite", SATELLITE_ROWS), ("load_batch", batch_rows), ("day_source", days),
              ("archive_cell", [(cell,) for cell in np.flatnonzero(footprint).tolist()])]
    return [{"table": table, "file": f"data/{table}.tsv.gz", "rows": _write_table(out / f"data/{table}.tsv.gz", rows)}
            for table, rows in tables]


def _part_entries(parts: list[_Part]) -> list[dict]:
    """The manifest entries of the parts, hotspot before hotspot_static, by year and satellite or family. Raises
    ValueError for a part that two workers wrote, which the precedence of the files rules out."""
    files = [part.file for part in parts]
    if len(files) != len(set(files)):
        raise ValueError(f"a part was written twice: {sorted(f for f in files if files.count(f) > 1)}")
    satellite_ids = {code: sid for sid, code in CODES.items()}
    entries = []
    for part in sorted(parts, key=lambda p: (p.table != "hotspot", p.year, satellite_ids.get(p.name, 0),
                                             FAMILY_INDEX.get(p.name, 0))):
        if part.table == "hotspot":
            entries.append({"table": "hotspot", "partition": f"hotspot_{part.year}_{part.name}", "year": part.year,
                            "satellite": part.name, "file": part.file, "rows": part.rows})
        else:
            entries.append({"table": "hotspot_static", "partition": f"hotspot_static_{part.year}", "year": part.year,
                            "file": part.file, "rows": part.rows})
    return entries


def _write_method(out: Path, version: str, harmonization_dir: Path) -> list[dict]:
    """Write the tables of one method version; return their manifest entries."""
    tables = v0_raw() if version == V0_RAW else read_version(harmonization_dir / version)
    entries = []
    for table in TABLES:
        if table in tables:
            rel = f"data/method/{version}/{table}.tsv.gz"
            entries.append({"table": table, "version": version, "file": rel,
                            "rows": _write_table(out / rel, tables[table])})
    return entries


def _copy_package_files(out: Path) -> None:
    """Copy the schema files and restore.sh when they exist, and the README of the package."""
    sql = sorted((_HERE / "sql").glob("*.sql"))
    if sql:
        (out / "schema").mkdir()
        for path in sql:
            shutil.copyfile(path, out / "schema" / path.name)
    if (_HERE / "restore.sh").is_file():
        shutil.copyfile(_HERE / "restore.sh", out / "restore.sh")
        (out / "restore.sh").chmod(0o755)
    shutil.copyfile(_HERE / "package_readme.md", out / "README.md")


# --- files ----------------------------------------------------------------------------------------------------


@contextmanager
def _gzip(path: Path) -> Iterator[gzip.GzipFile]:
    """A gzip file at path whose bytes depend on the data alone: no time and no name in its header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=_COMPRESSLEVEL,
                                               mtime=0) as handle:
        yield handle


def _write_table(path: Path, rows: Iterable[Sequence]) -> int:
    """Write rows of Python values as a gzip COPY text file; return their number."""
    count = 0
    lines: list[str] = []
    with _gzip(path) as handle:
        for row in rows:
            lines.append("\t".join(map(_field, row)) + "\n")
            count += 1
            if len(lines) >= _CHUNK:
                handle.write("".join(lines).encode())
                lines.clear()
        handle.write("".join(lines).encode())
    return count


def _field(value: object) -> str:
    """One value in the COPY text format of PostgreSQL."""
    if value is None:
        return _NULL
    if value is True or value is False:
        return "t" if value else "f"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{value} is not a finite number")
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):  # before date: a datetime is a date
        if value.tzinfo is None:
            raise ValueError(f"{value} has no time zone")
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value.translate(_TSV_ESCAPES)
    if isinstance(value, list | tuple):
        return _array(value).translate(_TSV_ESCAPES)
    if isinstance(value, dict):
        # ASCII only, so that the bytes reach jsonb alike in every client encoding of psql
        return json.dumps(value, ensure_ascii=True, sort_keys=True).translate(_TSV_ESCAPES)
    raise TypeError(f"{value!r}: no COPY form for {type(value).__name__}")


def _array(values: Sequence[str]) -> str:
    """A PostgreSQL array of text: {6.03,61.03}; an element with a character the syntax uses is quoted."""
    def element(text: str) -> str:
        if text and text.upper() != "NULL" and re.fullmatch(r'[^{}",\\\s]+', text):
            return text
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    return "{" + ",".join(element(v) for v in values) + "}"


def _start(out: Path) -> Path:
    """The empty folder the package is built in, beside out. Raises FileExistsError when out holds files and no
    manifest.json: such a folder is not a package to replace."""
    if out.exists() and not (out / "manifest.json").is_file() and any(out.iterdir()):
        raise FileExistsError(f"{out} holds files and no manifest.json: it is not a package to replace")
    work = out.with_name(out.name + ".partial")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    return work


def _finish(work: Path, out: Path) -> None:
    """Put the complete package in place of out."""
    if not out.exists():
        work.rename(out)
        return
    old = out.with_name(out.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    out.rename(old)
    work.rename(out)
    shutil.rmtree(old)


def _raw_name(src: SourceFile) -> str:
    """A raw file as the package names it, from the folder of its kind wherever that folder is:
    archive/modis_2021_all_countries.zip, api/VIIRS_SNPP_NRT/2026-10-30_4d.csv."""
    return f"archive/{src.path.name}" if src.is_archive else f"api/{src.source_code}/{src.path.name}"


def _iso(moment: datetime) -> str:
    """A UTC time as manifest.json writes it: 2026-11-14T12:52:00Z."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
