"""What the dump exporter decides from the list of raw files alone: the firms.load_batch id of each file, and which
file holds each day of each family of satellites, so that every point gets into the package once.

For each family (modis, snpp, noaa20, noaa21) and day:

- an archive zip of the family holds every day of its year, and no API file keeps those days;
- on the other days, an API file of standard processing (SP) beats a near real time (NRT) one;
- among API files of one kind the newer mtime wins, and on the same mtime the later path, so that the answer never
  depends on the order of the list;
- the days of an API file come from its name <start>_<N>d.csv.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final

from .sources import SourceFile

#: The number of each family in the load_batch ids.
FAMILY_INDEX: Final[dict[str, int]] = {"modis": 1, "snpp": 2, "noaa20": 3, "noaa21": 4}

_API_IDS: Final[int] = 1_000_000_000  # the lowest id of an API file; an archive zip gets year * 10 + family
_ID_EPOCH: Final[date] = date(2000, 1, 1)
_MAX_ID: Final[int] = 2_147_483_647  # the largest PostgreSQL integer


def assign_batches(files: list[SourceFile]) -> dict[Path, int]:
    """The firms.load_batch id of each file. The id comes from the file alone, so a file gets the same id in every
    package, and restore.sh --only-year can replace the rows of load_batch by id.

    An archive zip gets year * 10 + family: modis_2021_all_countries.zip gets 20211. An API file gets
    1 000 000 000 + its first day's number from 2000-01-01 * 100 + family * 20 + 10 for NRT + its days, which leaves
    room for 1 to 9 days. The family numbers are those of FAMILY_INDEX. A file the rule cannot number and two files
    with the same id raise ValueError.
    """
    ids = {src.path: _batch_id(src) for src in files}
    owners: dict[int, Path] = {}
    for path, number in ids.items():
        owner = owners.setdefault(number, path)
        if owner != path:
            raise ValueError(f"{owner} and {path} get the same load_batch id {number}")
    return ids


def winners(files: list[SourceFile]) -> dict[tuple[str, date], Path]:
    """The file that holds each (family, day): an archive zip on every day of its year, an API file on the days it
    won among the API files of its family."""
    win: dict[tuple[str, date], Path] = {}
    for src in sorted(files, key=_rank):  # the stronger file comes later and takes the day
        first, count = _span(src)
        for offset in range(count):
            win[(src.family, first + timedelta(days=offset))] = src.path
    return win


def keeps(src: SourceFile, day: date, win: dict[tuple[str, date], Path]) -> bool:
    """True when the rows of src on day go into the package: always for an archive zip, and for an API file on the
    days it won."""
    return src.is_archive or win.get((src.family, day)) == src.path


def _rank(src: SourceFile) -> tuple[bool, bool, datetime, Path]:
    """The strength of a file: an archive zip above every API file, then SP above NRT, then the newer mtime, then
    the later path."""
    return (src.is_archive, not src.is_nrt, src.mtime, src.path)


def _span(src: SourceFile) -> tuple[date, int]:
    """The first day and the number of days of a file: the whole year of an archive zip, the days that the name of
    an API file gives."""
    if src.year is not None:
        first = date(src.year, 1, 1)
        return first, (date(src.year + 1, 1, 1) - first).days
    if src.first_day is None or src.days is None:
        raise ValueError(f"{src.path}: neither the year of a zip nor the days of an API file")
    return src.first_day, src.days


def _batch_id(src: SourceFile) -> int:
    family = FAMILY_INDEX[src.family]
    if src.year is not None:
        return src.year * 10 + family
    first, days = _span(src)
    if not 1 <= days <= 9:
        raise ValueError(f"{src.path}: {days} days, and a load_batch id has room for 1 to 9")
    number = _API_IDS + (first - _ID_EPOCH).days * 100 + family * 20 + (10 if src.is_nrt else 0) + days
    if number > _MAX_ID:
        raise ValueError(f"{src.path}: the load_batch id {number} is larger than a PostgreSQL integer")
    return number
