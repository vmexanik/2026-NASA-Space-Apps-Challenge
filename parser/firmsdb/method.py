"""The rows of the tables of a harmonization method version: firms.method, method_weight, method_factor, method_error
and method_gap.

v0_raw() makes the version v0-raw, which counts every fire of the series with weight 1, without harmonization.
read_version() reads a version that build_factors.py wrote into data/harmonization/<version>/. A row is a tuple of
Python values in the column order of its table (the shared package format): None for NULL, dates as dates, a satellite
as its firms.satellite id, params as a dict.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Final

from .rows import CODES, SATELLITES

#: The tables of a version, in the order the package lists them.
TABLES: Final[tuple[str, ...]] = ("method", "method_weight", "method_factor", "method_error", "method_gap")

V0_RAW: Final[str] = "v0-raw"
#: The satellite of the series of v0-raw on each period, first and last day (factors design, 6.3); None: no end.
V0_RAW_SEGMENTS: Final[tuple[tuple[int, date, date | None], ...]] = (
    (SATELLITES["terra"], date(2000, 11, 1), date(2002, 7, 3)),
    (SATELLITES["aqua"], date(2002, 7, 4), date(2012, 1, 19)),
    (SATELLITES["snpp"], date(2012, 1, 20), date(2026, 11, 2)),
    (SATELLITES["noaa20"], date(2026, 11, 3), None),
)
SQUARES2: Final[int] = 180 * 90  # the 2-degree squares of firms.grid

_METHOD_KEYS: Final[frozenset[str]] = frozenset({"version", "label", "params", "created_at"})
_SATELLITE_IDS: Final[dict[str, int]] = {code: sid for sid, code in CODES.items()}
_SOURCES: Final[frozenset[str]] = frozenset({"modis", "viirs"})
_INTEGER: Final[re.Pattern[str]] = re.compile(r"-?[0-9]+")
_NUMBER: Final[re.Pattern[str]] = re.compile(r"-?[0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)?")
_DATE: Final[re.Pattern[str]] = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_BOOLEANS: Final[dict[str, bool]] = {"True": True, "true": True, "t": True, "False": False, "false": False, "f": False}


def v0_raw() -> dict[str, list[tuple]]:
    """The rows of method and method_weight of v0-raw: weight 1 on every 2-degree square and calendar month of each
    period of V0_RAW_SEGMENTS, day and night.

    created_at is NULL, so that every package carries the same bytes for it.
    """
    method = [(V0_RAW, "Weight 1 for every fire, not harmonized",
               {"confidence_filter": None, "harmonized": False}, None)]
    weights = [(V0_RAW, satellite, first, last, cell2, month, None, 1.0)
               for satellite, first, last in V0_RAW_SEGMENTS for cell2 in range(SQUARES2) for month in range(1, 13)]
    return {"method": method, "method_weight": weights}


def read_version(folder: Path) -> dict[str, list[tuple]]:
    """The rows of the five tables of the version in folder: method.json and the files <table>.csv.

    The columns of a CSV file are found by its header, in any order; a missing or unknown column raises ValueError.
    An empty field is NULL: an open-ended date_to, a NULL is_day, a NULL satellite in method_error. A satellite is
    written as its code (terra, aqua, snpp, noaa20, noaa21) and becomes its id. A value that does not read, an empty
    field in a column that is not NULL, and a row or method.json of another version than the folder's name raise
    ValueError; a missing file raises FileNotFoundError.
    """
    version = folder.name
    paths = [folder / "method.json"] + [folder / f"{table}.csv" for table in _COLUMNS]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"{path}: no such file; a method version has {', '.join(p.name for p in paths)}")
    tables = {"method": [_method_row(folder / "method.json", version)]}
    for table, columns in _COLUMNS.items():
        tables[table] = _read_csv(folder / f"{table}.csv", columns, version)
    return tables


def _method_row(path: Path, version: str) -> tuple:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not set(data) <= _METHOD_KEYS:
        raise ValueError(f"{path}: an object with the keys {', '.join(sorted(_METHOD_KEYS))} only")
    if data.get("version") != version:
        raise ValueError(f"{path}: the version {data.get('version')!r} is not the folder's {version!r}")
    label, params, created_at = data.get("label"), data.get("params"), data.get("created_at")
    if not isinstance(label, str | None) or not isinstance(params, dict | None):
        raise ValueError(f"{path}: label must be text and params an object")
    if created_at is not None:
        created_at = datetime.fromisoformat(created_at)
        if created_at.tzinfo is None:
            raise ValueError(f"{path}: created_at {data['created_at']!r} has no time zone")
    return version, label, params, created_at


def _read_csv(path: Path, columns: tuple[tuple[str, Callable[[str], object], bool], ...],
              version: str) -> list[tuple]:
    names = [name for name, _, _ in columns]
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None or sorted(header) != sorted(names):
            raise ValueError(f"{path}: the columns are {header}, not {', '.join(names)} in any order")
        index = [header.index(name) for name in names]
        rows = []
        for fields in reader:
            if len(fields) != len(header):
                raise ValueError(f"{path}: line {reader.line_num} has {len(fields)} fields, the header has "
                                 f"{len(header)}")
            row = []
            for (name, read, nullable), i in zip(columns, index):
                text = fields[i]
                try:
                    if text == "" and not nullable:
                        raise ValueError("is empty, and the column is not NULL")
                    row.append(None if text == "" else read(text))
                except ValueError as err:
                    raise ValueError(f"{path}: line {reader.line_num}: {name} {text!r}: {err}") from None
            if row[0] != version:
                raise ValueError(f"{path}: line {reader.line_num} is of the version {row[0]!r}, not {version!r}")
            rows.append(tuple(row))
    return rows


def _satellite(text: str) -> int:
    if text not in _SATELLITE_IDS:
        raise ValueError(f"not a satellite code ({', '.join(_SATELLITE_IDS)})")
    return _SATELLITE_IDS[text]


def _integer(text: str) -> int:
    if _INTEGER.fullmatch(text) is None:
        raise ValueError("not an integer")
    return int(text)


def _number(text: str) -> float:
    if _NUMBER.fullmatch(text) is None:  # float() alone takes nan, inf, spaces and 1_0
        raise ValueError("not a finite number")
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("not a finite number")
    return value


def _day(text: str) -> date:
    if _DATE.fullmatch(text) is None:
        raise ValueError("not YYYY-MM-DD")
    return date.fromisoformat(text)


def _boolean(text: str) -> bool:
    if text not in _BOOLEANS:
        raise ValueError(f"not one of {', '.join(_BOOLEANS)}")
    return _BOOLEANS[text]


def _source(text: str) -> str:
    if text not in _SOURCES:
        raise ValueError(f"not one of {', '.join(sorted(_SOURCES))}")
    return text


# The columns of the CSV file of each table, in the column order of the table: name, reader, NULL allowed.
_COLUMNS: Final[dict[str, tuple[tuple[str, Callable[[str], object], bool], ...]]] = {
    "method_weight": (("version", str, False), ("satellite", _satellite, False), ("date_from", _day, False),
                      ("date_to", _day, True), ("cell2_id", _integer, False), ("calendar_month", _integer, False),
                      ("is_day", _boolean, True), ("weight", _number, False)),
    "method_factor": (("version", str, False), ("satellite", _satellite, False), ("cell2_id", _integer, False),
                      ("calendar_month", _integer, False), ("factor", _number, True), ("own_modis", _integer, True),
                      ("own_viirs", _integer, True), ("own_share", _number, True), ("cross_factor", _number, True),
                      ("cross_modis", _integer, True), ("square8_factor", _number, True),
                      ("world_factor", _number, True)),
    "method_error": (("version", str, False), ("source", _source, False), ("satellite", _satellite, True),
                     ("n_min", _integer, False), ("rel_error", _number, False)),
    "method_gap": (("version", str, False), ("day", _day, False)),
}
