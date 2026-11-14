"""The files of a method version, which the database dump reads by their column names.

data/harmonization/<version>/ holds method.json, method_weight.csv, method_factor.csv, method_error.csv,
method_gap.csv, report.html and report.json. An empty field is NULL: an open-ended date_to, a NULL is_day.
The same input always gives the same bytes, so method.json carries no build time (the report does).
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Final

from .validate import write_report

WEIGHT_COLUMNS: Final[tuple[str, ...]] = (
    "version", "satellite", "date_from", "date_to", "cell2_id", "calendar_month", "is_day", "weight")
FACTOR_COLUMNS: Final[tuple[str, ...]] = (
    "version", "satellite", "cell2_id", "calendar_month", "factor", "own_modis", "own_viirs", "own_share",
    "cross_factor", "cross_modis", "square8_factor", "world_factor")
ERROR_COLUMNS: Final[tuple[str, ...]] = ("version", "source", "satellite", "n_min", "rel_error")
GAP_COLUMNS: Final[tuple[str, ...]] = ("version", "day")


def _field(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _write_csv(path: Path, columns: tuple[str, ...], rows: Iterable[tuple]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_field(v) for v in row])


def write_version(out_dir: Path, method: dict, weights: list[tuple], factors: list[tuple], errors: list[tuple],
                  gaps: list[date], report: dict) -> None:
    """Write the files of version method['version'] into out_dir.

    weights  (satellite, date_from, date_to, cell2_id, calendar_month, weight)
    factors  (satellite, cell2_id, calendar_month, factor, own_modis, own_viirs, own_share, cross_factor,
              cross_modis, square8_factor, world_factor)
    errors   (source, satellite, n_min, rel_error)
    """
    version = method["version"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "method.json").write_text(json.dumps(method, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                         encoding="utf-8")
    _write_csv(out_dir / "method_weight.csv", WEIGHT_COLUMNS,
               ((version, s, d0, d1, cell, month, None, float(w)) for s, d0, d1, cell, month, w in weights))
    _write_csv(out_dir / "method_factor.csv", FACTOR_COLUMNS,
               ((version, *row[:3], *(float(v) if isinstance(v, float) else v for v in row[3:])) for row in factors))
    _write_csv(out_dir / "method_error.csv", ERROR_COLUMNS,
               ((version, source, sat, n_min, float(rel)) for source, sat, n_min, rel in errors))
    _write_csv(out_dir / "method_gap.csv", GAP_COLUMNS, ((version, day) for day in sorted(gaps)))
    write_report(out_dir, report)
