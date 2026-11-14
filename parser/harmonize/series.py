"""Which satellite makes up the long record on which day, and the weight rows that say so.

Each day has a primary satellite. A day on which the primary gave no point at all takes the first backup that
has data that day; a day with no backup goes into the gaps, and its month is incomplete. A day on which the
primary gave even one point is left to it, so the same fires are never counted twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from itertools import repeat
from typing import Final

import numpy as np

from .days import EPOCH, day_index

ROWS: Final[int] = 90
COLS: Final[int] = 180


@dataclass(frozen=True)
class Segment:
    """A run of days with one satellite in the record; `end` is None for a period with no end."""

    satellite: str
    start: date
    end: date | None


PERIODS: Final[tuple[Segment, ...]] = (
    Segment("terra", date(2000, 11, 1), date(2002, 7, 3)),
    Segment("aqua", date(2002, 7, 4), date(2012, 1, 19)),
    Segment("snpp", date(2012, 1, 20), date(2026, 11, 2)),
    Segment("noaa20", date(2026, 11, 3), None),
)
BACKUPS: Final[dict[str, tuple[str, ...]]] = {
    "snpp": ("noaa20", "aqua", "terra"),
    "aqua": ("terra",),
    "terra": (),
    "noaa20": (),
}


def backup_segments(days: dict[str, np.ndarray]) -> tuple[list[Segment], list[date]]:
    """The runs of days taken by a backup satellite and the days no satellite covers. `days` maps a satellite
    code to a flag per day from EPOCH; days after the end of the arrays are not looked at."""
    length = len(next(iter(days.values())))
    absent = np.zeros(length, dtype=bool)
    segments: list[Segment] = []
    gaps: list[date] = []
    for period in PERIODS:
        first = day_index(period.start)
        last = length - 1 if period.end is None else min(day_index(period.end), length - 1)
        if first > last:
            continue
        empty = ~days.get(period.satellite, absent)[first:last + 1]
        for offset in np.flatnonzero(empty):
            index = first + int(offset)
            day = EPOCH + timedelta(days=index)
            backup = next((b for b in BACKUPS[period.satellite] if days.get(b, absent)[index]), None)
            if backup is None:
                gaps.append(day)
            elif segments and segments[-1].satellite == backup and segments[-1].end == day - timedelta(days=1):
                segments[-1] = Segment(backup, segments[-1].start, day)
            else:
                segments.append(Segment(backup, day, day))
    return segments, gaps


def _months(start: date, end: date | None) -> list[int]:
    """The calendar months (1-12) a run of days touches."""
    if end is None or (end.year - start.year) * 12 + end.month - start.month >= 11:
        return list(range(1, 13))
    months, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return sorted(months)


def weight_rows(factors: dict[str, np.ndarray],
                backups: list[Segment]) -> list[tuple[str, date, date | None, int, int, float]]:
    """Rows (satellite, date_from, date_to, cell2_id, calendar_month, weight): every primary period for all
    12 months, every backup run for the months it touches, each for all 16 200 squares. The weight is the
    factor of the square and month for Terra and Aqua (factors[s] shaped (90, 180, 12)) and 1.0 for VIIRS."""
    cells = np.arange(ROWS * COLS)
    rows_of, cols_of = cells // COLS, cells % COLS
    out: list[tuple[str, date, date | None, int, int, float]] = []
    for seg, months in [(p, list(range(1, 13))) for p in PERIODS] + [(b, _months(b.start, b.end)) for b in backups]:
        for month in months:
            if seg.satellite in factors:
                weights = factors[seg.satellite][rows_of, cols_of, month - 1].astype(float).tolist()
            else:
                weights = [1.0] * len(cells)
            out.extend(zip(repeat(seg.satellite), repeat(seg.start), repeat(seg.end), cells.tolist(),
                           repeat(month), weights))
    out.sort(key=lambda r: (r[1], r[0], r[3], r[4]))
    return out
