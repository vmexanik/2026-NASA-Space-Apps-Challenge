"""Reading FIRMS hotspot files: the members of the yearly world archives and the CSV files of the area API.

Only what harmonization needs is kept: the 0.25-degree cell and 2-degree square of the point (from the
shared grid of firms.grid), the day, the satellite and the type. A row that cannot be read is skipped and
counted in the log.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import numpy as np

from firms.grid import cell2_id, cell_id

from .days import EPOCH

SAT_IDS: Final[dict[str, int]] = {"terra": 1, "aqua": 2, "snpp": 3, "noaa20": 4, "noaa21": 5}
SAT_NAMES: Final[dict[str, str]] = {"Terra": "terra", "T": "terra", "Aqua": "aqua", "A": "aqua", "N": "snpp",
                                    "N20": "noaa20", "N21": "noaa21"}
NO_TYPE: Final[int] = -1

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Member:
    """A CSV file: a member of a zip archive, or a plain file when `member` is None."""

    path: Path
    member: str | None


@dataclass
class Rows:
    """The readable rows of one file: cell (int32), cell2 (int16), day from EPOCH (int32), satellite id
    from SAT_IDS (int8) and type (int8, NO_TYPE when the file has no such column)."""

    cell: np.ndarray
    cell2: np.ndarray
    day: np.ndarray
    sat: np.ndarray
    type: np.ndarray


def archive_members(archive_dir: Path, sensor: str, years: Iterable[int]) -> list[Member]:
    """The CSV members of <sensor>_<year>_all_countries.zip for the given years; a missing zip is skipped."""
    members = []
    for year in years:
        path = archive_dir / f"{sensor}_{year}_all_countries.zip"
        if not path.exists():
            log.warning("no archive %s", path)
            continue
        with zipfile.ZipFile(path) as archive:
            members.extend(Member(path, name) for name in sorted(archive.namelist()) if name.endswith(".csv"))
    return members


def api_files(api_dir: Path) -> list[Member]:
    """The CSV files under api_dir/<SOURCE>/."""
    return [Member(path, None) for path in sorted(api_dir.glob("*/*.csv"))]


def country_of(member: Member) -> str | None:
    """The country of an archive member: modis/2015/modis_2015_Ukraine.csv gives Ukraine."""
    if member.member is None:
        return None
    parts = Path(member.member).stem.split("_", 2)
    return parts[2] if len(parts) == 3 else None


def read_member(member: Member) -> Rows:
    """The readable rows of a FIRMS CSV file."""
    cells: list[int] = []
    squares: list[int] = []
    days: list[int] = []
    sats: list[int] = []
    types: list[int] = []
    day_of: dict[str, int] = {}
    skipped = 0
    with ExitStack() as stack:
        if member.member is None:
            text = stack.enter_context(member.path.open(newline="", encoding="utf-8"))
        else:
            archive = stack.enter_context(zipfile.ZipFile(member.path))
            text = io.TextIOWrapper(stack.enter_context(archive.open(member.member)), encoding="utf-8", newline="")
        reader = csv.reader(text)
        header = {name: i for i, name in enumerate(next(reader, []))}
        try:
            i_lat, i_lon, i_date, i_sat = (header[c] for c in ("latitude", "longitude", "acq_date", "satellite"))
        except KeyError:
            log.warning("%s %s: not a FIRMS hotspot file", member.path, member.member or "")
            return _rows([], [], [], [], [])
        i_type = header.get("type")
        for row in reader:
            try:
                sat = SAT_IDS[SAT_NAMES[row[i_sat]]]
                text_day = row[i_date]
                day = day_of.get(text_day)
                if day is None:
                    year, month, mday = text_day.split("-")
                    day = day_of[text_day] = (date(int(year), int(month), int(mday)) - EPOCH).days
                cell = cell_id(float(row[i_lat]), float(row[i_lon]))
                kind = int(row[i_type]) if i_type is not None else NO_TYPE
            except (KeyError, ValueError, IndexError):
                skipped += 1
                continue
            cells.append(cell)
            squares.append(cell2_id(cell))
            days.append(day)
            sats.append(sat)
            types.append(kind)
    if skipped:
        log.warning("%s %s: skipped %d rows that cannot be read", member.path, member.member or "", skipped)
    return _rows(cells, squares, days, sats, types)


def _rows(cells: list[int], squares: list[int], days: list[int], sats: list[int], types: list[int]) -> Rows:
    return Rows(cell=np.array(cells, dtype=np.int32), cell2=np.array(squares, dtype=np.int16),
                day=np.array(days, dtype=np.int32), sat=np.array(sats, dtype=np.int8),
                type=np.array(types, dtype=np.int8))
