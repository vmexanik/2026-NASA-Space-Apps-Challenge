"""The raw FIRMS files the dump exporter reads: the yearly world archives and the CSV files of the area API.

data/raw/archive holds the zips <prefix>_<year>_all_countries.zip of fetch_archive.py, with one CSV member per
country, <prefix>/<year>/<prefix>_<year>_<Country>.csv. data/raw/api holds the files <SOURCE>/<start>_<N>d.csv of
fetch_current_year.py, each with the N days of one FIRMS source from <start>. A name that these rules do not know
raises ValueError, so that a change in the FIRMS files stops the export instead of slipping into the database.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final

from firms.archive import Sensor
from firms.constants import Source

#: The family of satellites of each source. The files of one family compete for each day (firmsdb.precedence).
FAMILIES: Final[dict[Source, str]] = {
    Source.MODIS_SP: "modis", Source.MODIS_NRT: "modis",
    Source.VIIRS_SNPP_SP: "snpp", Source.VIIRS_SNPP_NRT: "snpp",
    Source.VIIRS_NOAA20_SP: "noaa20", Source.VIIRS_NOAA20_NRT: "noaa20",
    Source.VIIRS_NOAA21_SP: "noaa21", Source.VIIRS_NOAA21_NRT: "noaa21",
}

#: The source of the yearly archives of each zip prefix: they hold standard processing (SP) data.
ARCHIVE_SOURCES: Final[dict[Sensor, Source]] = {
    Sensor.MODIS: Source.MODIS_SP,
    Sensor.VIIRS_SNPP: Source.VIIRS_SNPP_SP,
    Sensor.VIIRS_NOAA20: Source.VIIRS_NOAA20_SP,
}

_ARCHIVE_NAME: Final[re.Pattern[str]] = re.compile(r"(?P<prefix>.+)_(?P<year>[0-9]{4})_all_countries\.zip")
_API_NAME: Final[re.Pattern[str]] = re.compile(r"(?P<start>[0-9]{4}-[0-9]{2}-[0-9]{2})_(?P<days>[1-9][0-9]*)d\.csv")


@dataclass(frozen=True)
class SourceFile:
    """One raw FIRMS file: a yearly archive zip or a CSV file of the area API."""

    path: Path
    source_code: str  # the FIRMS source: MODIS_SP, VIIRS_SNPP_NRT ...
    family: str  # modis, snpp, noaa20 or noaa21
    is_nrt: bool  # near real time; False for standard processing (SP)
    year: int | None  # the year of an archive zip; None for an API file
    first_day: date | None  # the first day of an API file, from its name; None for a zip
    days: int | None  # how many days an API file holds, from its name; None for a zip
    size: int  # bytes
    mtime: datetime  # when the file was changed last, in UTC

    @property
    def is_archive(self) -> bool:
        """True for a yearly archive zip, False for an API file."""
        return self.year is not None


def list_archive(archive_dir: Path, years: tuple[int, int] | None) -> list[SourceFile]:
    """The yearly archive zips in archive_dir, sorted by path; with years (first, last), only the zips of those
    years. Raises FileNotFoundError when archive_dir is missing."""
    files = []
    for path in _listing(archive_dir, "*.zip"):
        match = _ARCHIVE_NAME.fullmatch(path.name)
        if match is None or match["prefix"] not in ARCHIVE_SOURCES:
            raise ValueError(f"{path}: not <prefix>_<year>_all_countries.zip with a prefix of "
                             f"{', '.join(ARCHIVE_SOURCES)}")
        year = int(match["year"])
        if years is None or years[0] <= year <= years[1]:
            files.append(_source_file(path, ARCHIVE_SOURCES[Sensor(match["prefix"])], year=year))
    return files


def list_api(api_dir: Path, years: tuple[int, int] | None) -> list[SourceFile]:
    """The files <SOURCE>/<start>_<N>d.csv in api_dir, sorted by path; with years (first, last), only the files
    with at least one day in those years. Raises FileNotFoundError when api_dir is missing.

    A file can hold days of two years, such as 2026-12-30_5d.csv; its days outside years are the caller's to drop.
    """
    files = []
    for path in _listing(api_dir, "*/*.csv"):
        code = path.parent.name
        if code not in FAMILIES:
            raise ValueError(f"{path}: {code} is not a FIRMS source of this database ({', '.join(FAMILIES)})")
        match = _API_NAME.fullmatch(path.name)
        if match is None:
            raise ValueError(f"{path}: the name is not <start>_<N>d.csv")
        try:
            first_day = date.fromisoformat(match["start"])
        except ValueError as err:
            raise ValueError(f"{path}: {err}") from None
        days = int(match["days"])
        last_day = first_day + timedelta(days=days - 1)
        if years is None or (first_day.year <= years[1] and last_day.year >= years[0]):
            files.append(_source_file(path, Source(code), first_day=first_day, days=days))
    return files


def archive_members(src: SourceFile, countries: list[str] | None) -> list[str]:
    """The country members <prefix>/<year>/<prefix>_<year>_<Country>.csv of an archive zip, sorted; with countries,
    only theirs. A country is matched whole: Guinea does not take Equatorial_Guinea or Papua_New_Guinea.

    Members that are not CSV files, such as the folder and AttributesReadme.txt, are skipped; a CSV member of
    any other name raises ValueError.
    """
    prefix = src.path.name.removesuffix(f"_{src.year}_all_countries.zip")
    stem = f"{prefix}/{src.year}/{prefix}_{src.year}_"
    member_name = re.compile(rf"{re.escape(stem)}(?P<country>[^/]+)\.csv")
    wanted = None if countries is None else set(countries)
    members = []
    with zipfile.ZipFile(src.path) as archive:
        for name in archive.namelist():
            if not name.endswith(".csv"):
                continue
            match = member_name.fullmatch(name)
            if match is None:
                raise ValueError(f"{src.path}: the member {name} is not {stem}<Country>.csv")
            if wanted is None or match["country"] in wanted:
                members.append(name)
    return sorted(members)


def read_rows(src: SourceFile, member: str | None = None) -> Iterator[dict[str, str]]:
    """The rows of an API file, or of one member of an archive zip, as {column: text} by the file's header.

    The text is as FIRMS wrote it: acq_time 28 stays "28", for firmsdb.rows to read. A file without a header and
    a row whose number of fields differs from the header's raise ValueError. The call itself refuses an archive
    zip without a member and an API file with one.
    """
    if src.is_archive != (member is not None):
        raise ValueError(f"{src.path}: " + ("a zip is read one member at a time" if src.is_archive
                                            else "an API file has no members"))
    return _rows(src, member)


def _rows(src: SourceFile, member: str | None) -> Iterator[dict[str, str]]:
    where = str(src.path) if member is None else f"{src.path}: {member}"
    with ExitStack() as stack:
        if member is None:
            text = stack.enter_context(src.path.open(encoding="utf-8", newline=""))
        else:
            archive = stack.enter_context(zipfile.ZipFile(src.path))
            text = stack.enter_context(io.TextIOWrapper(archive.open(member), encoding="utf-8", newline=""))
        reader = csv.reader(text)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"{where}: no header")
        for fields in reader:
            if len(fields) != len(header):
                raise ValueError(f"{where}: line {reader.line_num} has {len(fields)} fields, "
                                 f"the header has {len(header)}")
            yield dict(zip(header, fields))


def _listing(folder: Path, pattern: str) -> list[Path]:
    """The paths in folder that match pattern, sorted. A missing folder is an error, not an empty list: a wrong
    path must not build a package without these files."""
    if not folder.is_dir():
        raise FileNotFoundError(f"{folder}: no such folder")
    return sorted(folder.glob(pattern))


def _source_file(path: Path, source: Source, *, year: int | None = None, first_day: date | None = None,
                 days: int | None = None) -> SourceFile:
    stat = path.stat()
    return SourceFile(path=path, source_code=source.value, family=FAMILIES[source], is_nrt=source.is_near_real_time,
                      year=year, first_day=first_day, days=days, size=stat.st_size,
                      mtime=datetime.fromtimestamp(stat.st_mtime, UTC))
