#!/usr/bin/env python3
"""Does a map of static places built from past years label next year's rows right?

Hide the FIRMS `type` of the test year, label its rows with a mask built from the
earlier years, compare with the hidden `type`.

Usage: python3 -I mask_test.py <folder with *_Ukraine.csv>

The splits depend on the years the folder holds.
"""
import csv
import glob
import os
import sys
from collections import Counter, defaultdict

DATA = sys.argv[1]
LAT0, LON0, DLAT, DLON, NLON = 43.0, 21.0, 0.01, 0.015, 2000  # ~1.1 km cells


def cell_of(lat: float, lon: float) -> int:
    return int((lat - LAT0) / DLAT) * NLON + int((lon - LON0) / DLON)


def around(cell: int):
    la, lo = divmod(cell, NLON)
    return [(la + i) * NLON + lo + j for i in (-1, 0, 1) for j in (-1, 0, 1)]


def load(family: str):
    """Rows of one family as (year, cell, type, date, daynight)."""
    rows = []
    for path in sorted(glob.glob(os.path.join(DATA, f"{family}_*_Ukraine.csv"))):
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                rows.append((int(r["acq_date"][:4]), cell_of(float(r["latitude"]), float(r["longitude"])),
                             int(r["type"]), r["acq_date"], r["daynight"]))
    return rows


def report(name: str, train, test) -> None:
    static = {c for _, c, t, _, _ in train if t != 0}
    wide = {x for c in static for x in around(c)}
    days = defaultdict(set)
    for _, c, _, d, _ in train:
        days[c].add(d)
    often = {c for c, v in days.items() if len(v) >= 15}
    n = Counter()
    for _, c, t, _, dn in test:
        kind = "fire" if t == 0 else "static"
        n[kind] += 1
        n[kind, dn] += 1
        for tag, mask in (("cell", static), ("cell+1km", wide), ("often", often)):
            if c in mask:
                n[kind, tag] += 1
                n[kind, tag, dn] += 1
    print(f"{name}: test rows fire={n['fire']} static={n['static']}; mask cells: {len(static)} (with neighbours {len(wide)}), 'burns on 15+ days' cells: {len(often)}")
    for tag, label in (("cell", "same ~1 km cell as a past static row"), ("cell+1km", "same cell or a neighbour"), ("often", "no type used: cell burned on 15+ days before")):
        print(f"   {label:45s} catches {n['static', tag] / n['static']:6.1%} of static rows "
              f"(night {n['static', tag, 'N'] / max(n['static', 'N'], 1):6.1%}, day {n['static', tag, 'D'] / max(n['static', 'D'], 1):6.1%})"
              f" | wrongly drops {n['fire', tag] / n['fire']:5.2%} of fire rows")


snpp = load("viirs-snpp")
modis = load("modis")
n20 = load("viirs-jpss1")
ys = sorted({r[0] for r in snpp})
print("years: SNPP", ys, "MODIS", sorted({r[0] for r in modis}), "NOAA-20", sorted({r[0] for r in n20}))


def split(rows, last_train, first_test, last_test):
    return [r for r in rows if r[0] <= last_train], [r for r in rows if first_test <= r[0] <= last_test]


report("SNPP  mask 2012-2014 -> rows of 2015", *split(snpp, 2014, 2015, 2015))
if ys[-1] >= 2021:
    report("SNPP  mask 2012-2016 -> rows of 2017-2021", *split(snpp, 2016, 2017, 2021))
    report("SNPP  mask 2012-2019 -> rows of 2020-2021", *split(snpp, 2019, 2020, 2021))
report("MODIS mask 2012-2019 -> rows of 2020-2021", *split(modis, 2019, 2020, 2021))
if n20 and ys[-1] >= 2019:
    report("NOAA-20 rows of 2020-2021, mask from SNPP 2012-2019", [r for r in snpp if r[0] <= 2019], [r for r in n20 if r[0] >= 2020])
