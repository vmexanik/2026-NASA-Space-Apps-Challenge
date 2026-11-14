"""Days of the record: day numbers counted from 2000-01-01, and the days each satellite gave points."""

from __future__ import annotations

from datetime import date
from multiprocessing import Pool
from typing import TYPE_CHECKING, Final

import numpy as np

if TYPE_CHECKING:
    from .sources import Member

EPOCH: Final[date] = date(2000, 1, 1)


def day_index(day: date) -> int:
    """The number of a day, counted from EPOCH (2000-01-01 is 0)."""
    return (day - EPOCH).days


def _days_of(member: Member) -> dict[int, np.ndarray]:
    """The days on which each satellite has at least one row of any type in one file."""
    from .sources import read_member  # sources imports EPOCH from here

    rows = read_member(member)
    return {int(sat): np.unique(rows.day[rows.sat == sat]) for sat in np.unique(rows.sat)}


def satellite_days(members: list[Member], jobs: int) -> dict[str, np.ndarray]:
    """For each satellite code, a flag per day from EPOCH to the last day any file has: True when the
    satellite gave at least one row of any type that day."""
    from .sources import SAT_IDS

    seen: dict[int, list[np.ndarray]] = {}
    with Pool(max(1, jobs)) as pool:
        for found in pool.imap_unordered(_days_of, members):
            for sat, days in found.items():
                seen.setdefault(sat, []).append(days)
    last = max((int(d.max()) for parts in seen.values() for d in parts if d.size), default=-1)
    flags = {}
    for code, sat in SAT_IDS.items():
        present = np.zeros(last + 1, dtype=bool)
        for days in seen.get(sat, []):
            present[days] = True
        flags[code] = present
    return flags
