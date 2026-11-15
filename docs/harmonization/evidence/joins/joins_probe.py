"""Does the harmonized series jump where one satellite hands over to the next?

The series of version v1-2026-11-14 is Terra until 2002-07-03, Aqua until 2012-01-19 and Suomi NPP after, with
backups on the days the main satellite gave no point. At each handover both satellites fly, so the step the
calendar shows is the ratio of the two harmonized counts in the same months, on the days both gave points:

    2002 join  harmonized Aqua / harmonized Terra, the months 2002-07 ... 2003-06
    2012 join  Suomi NPP / harmonized Aqua,       the months 2012-01 ... 2012-12

The raw counts of the same days give the step the calendar would show without harmonization. The script also
writes the monthly series for the world and for Ukraine, Brazil and Australia, and the months that backups
filled, against NOAA-20 alone.

Reads the FIRMS yearly archives 2000-2025 and the factors of the version (method_factor.csv) with the readers of
the harmonize package. Only vegetation fires (type 0), no confidence filter, as the method.

Run from a folder outside the data:
    python3 -I joins_probe.py <folder with harmonize/ and data/> <version folder> results.json
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

YEARS = tuple(range(2000, 2026))
REGIONS = ("world", "Ukraine", "Brazil", "Australia")
SATS = ("terra", "aqua", "snpp", "noaa20")
EPOCH64 = np.datetime64("2000-01-01")
MONTHS = len(YEARS) * 12
JOBS = 24

_STATE: dict = {}


def _init(state: dict) -> None:
    _STATE.update(state)


def _count(member):
    """Monthly sums of one file: raw and harmonized counts per satellite, the series, and the shared-day sums."""
    from harmonize.sources import SAT_IDS, country_of, read_member

    rows = read_member(member)
    fire = rows.type == 0
    months = (EPOCH64 + rows.day.astype("timedelta64[D]")).astype("datetime64[M]").astype(np.int64) - 360
    inside = fire & (months >= 0) & (months < MONTHS) & (rows.day < len(_STATE["series_sat"]))
    region = [0] + ([REGIONS.index(c)] if (c := country_of(member)) in REGIONS else [])
    out = np.zeros((len(REGIONS), 7, len(SATS), MONTHS))
    row2, col2 = rows.cell2.astype(np.int64) // 180, rows.cell2.astype(np.int64) % 180
    for s, sat in enumerate(SATS):
        sel = inside & (rows.sat == SAT_IDS[sat])
        if not sel.any():
            continue
        m = months[sel]
        if sat in ("terra", "aqua"):
            weight = _STATE["factors"][sat][row2[sel], col2[sel], m % 12]
        else:
            weight = np.ones(sel.sum())
        day = rows.day[sel]
        in_series = _STATE["series_sat"][day] == SAT_IDS[sat]
        both_ta = _STATE["terra"][day] & _STATE["aqua"][day]
        both_as = _STATE["aqua"][day] & _STATE["snpp"][day]
        parts = (np.ones(len(m)), weight, weight * in_series, both_ta, weight * both_ta, both_as, weight * both_as)
        for k, values in enumerate(parts):
            sums = np.bincount(m, weights=values.astype(float), minlength=MONTHS)
            for r in region:
                out[r, k, s] += sums
    return out


def _flags(days: dict[str, np.ndarray], length: int) -> dict[str, np.ndarray]:
    flags = {}
    for sat in SATS:
        f = np.zeros(length, dtype=bool)
        f[:min(length, len(days[sat]))] = days[sat][:length]
        flags[sat] = f
    return flags


def main() -> int:
    root, version, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    sys.path.insert(0, str(root))
    from multiprocessing import Pool

    from harmonize.days import day_index, satellite_days
    from harmonize.series import PERIODS, backup_segments
    from harmonize.sources import SAT_IDS, archive_members

    archive = root / "data" / "raw" / "archive"
    members = [m for s in ("modis", "viirs-snpp", "viirs-jpss1") for m in archive_members(archive, s, YEARS)]
    days = satellite_days(members, JOBS)
    backups, gaps = backup_segments(days)
    length = day_index(date(YEARS[-1] + 1, 1, 1))
    series_sat = np.zeros(length, dtype=np.int8)
    for seg in PERIODS:
        lo = day_index(seg.start)
        hi = length if seg.end is None else min(length, day_index(seg.end) + 1)
        series_sat[lo:hi] = SAT_IDS[seg.satellite]
    for seg in backups:
        lo, hi = day_index(seg.start), min(length, day_index(seg.end) + 1)
        series_sat[lo:hi] = SAT_IDS[seg.satellite]
    for gap in gaps:
        if day_index(gap) < length:
            series_sat[day_index(gap)] = 0

    factors = {s: np.zeros((90, 180, 12)) for s in ("terra", "aqua")}
    with (version / "method_factor.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            r, c = divmod(int(row["cell2_id"]), 180)
            factors[row["satellite"]][r, c, int(row["calendar_month"]) - 1] = float(row["factor"])

    state = {"factors": factors, "series_sat": series_sat, **_flags(days, length)}
    total = np.zeros((len(REGIONS), 7, len(SATS), MONTHS))
    with Pool(JOBS, initializer=_init, initargs=(state,)) as pool:
        for part in pool.imap_unordered(_count, members, chunksize=2):
            total += part

    def month_of(d: date) -> int:
        return (d.year - YEARS[0]) * 12 + d.month - 1

    def window(start: date) -> slice:
        return slice(month_of(start), month_of(start) + 12)

    result = {"version": version.name, "regions": {}, "backups": [[b.satellite, b.start.isoformat(),
                                                                    b.end.isoformat()] for b in backups]}
    t, a, n = SATS.index("terra"), SATS.index("aqua"), SATS.index("snpp")
    for i, region in enumerate(REGIONS):
        raw, harm, series = total[i, 0], total[i, 1], total[i, 2].sum(axis=0)
        w02, w12 = window(date(2002, 7, 1)), window(date(2012, 1, 1))
        step02 = total[i, 4, a, w02].sum() / total[i, 4, t, w02].sum() - 1
        step02_raw = total[i, 3, a, w02].sum() / total[i, 3, t, w02].sum() - 1
        step12 = total[i, 5, n, w12].sum() / total[i, 6, a, w12].sum() - 1
        step12_raw = total[i, 5, n, w12].sum() / total[i, 5, a, w12].sum() - 1
        yearly12 = {y: float(total[i, 5, n, (y - 2000) * 12:(y - 1999) * 12].sum()
                             / total[i, 6, a, (y - 2000) * 12:(y - 1999) * 12].sum() - 1) for y in range(2012, 2023)}
        result["regions"][region] = {
            "step_2002": float(step02), "step_2002_raw": float(step02_raw),
            "step_2012": float(step12), "step_2012_raw": float(step12_raw), "snpp_over_aqua_by_year": yearly12,
            "series": series.tolist(), "raw": {s: raw[k].tolist() for k, s in enumerate(SATS)},
            "harmonized": {s: harm[k].tolist() for k, s in enumerate(SATS)},
        }
    world = result["regions"]["world"]
    filled = {}
    for b in backups:
        if b.satellite != "noaa20":
            continue
        m = month_of(b.start)
        if 0 <= m < MONTHS:
            filled[f"{b.start.year}-{b.start.month:02d}"] = {"series": world["series"][m],
                                                             "noaa20": world["raw"]["noaa20"][m]}
    result["backup_months"] = filled
    out_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    for region, r in result["regions"].items():
        print(region, {k: round(r[k], 4) for k in ("step_2002", "step_2002_raw", "step_2012", "step_2012_raw")})
    print({k: round(v["series"] / v["noaa20"] - 1, 4) for k, v in filled.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
