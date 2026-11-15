#!/usr/bin/env python3
"""A text sketch of the harmonized burning calendar for Ukraine.

Usage: python3 -I calendar_sketch.py <folder with modis_*_Ukraine.csv, all years> <folder with viirs-snpp_*_Ukraine.csv>
"""
import bisect
import csv
import glob
import os
import statistics as st
import sys
from collections import Counter

MOD, VII = sys.argv[1], sys.argv[2]
MONTHS = ["Січ", "Лют", "Бер", "Кві", "Тра", "Чер", "Лип", "Сер", "Вер", "Жов", "Лис", "Гру"]
EDGES, SHADE = [0.5, 0.8, 1.25, 2.0], [" · ", " ░ ", " ▒ ", " ▓ ", " █ "]


def counts(folder, pattern, sat=None):
    c = Counter()
    for path in sorted(glob.glob(os.path.join(folder, pattern))):
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("type", "0") not in ("0", "") or (sat and r["satellite"] != sat):
                    continue
                c[int(r["acq_date"][:4]), int(r["acq_date"][5:7])] += 1
    return c


A = counts(MOD, "modis_*_Ukraine.csv", "Aqua")
S = counts(VII, "viirs-snpp_*_Ukraine.csv")
overlap = sorted(y for y in {k[0] for k in S} if y <= 2021 and sum(S[y, m] for m in range(1, 13)) > 0)
k = {m: sum(S[y, m] for y in overlap) / sum(A[y, m] for y in overlap) for m in range(1, 13)}
print(f"overlap years used for the multipliers: {overlap[0]}-{overlap[-1]}")
print("multiplier by month: " + "  ".join(f"{MONTHS[m - 1]} {k[m]:.1f}" for m in range(1, 13)))

years = list(range(2003, overlap[-1] + 1))
H = {(y, m): (S[y, m] if y in overlap else A[y, m] * k[m]) for y in years for m in range(1, 13)}
HM = {(y, m): A[y, m] * k[m] for y in years for m in range(1, 13)}          # everything from MODIS
normal = {m: st.mean(H[y, m] for y in years) for m in range(1, 13)}
shade = lambda v, m: SHADE[bisect.bisect(EDGES, v / normal[m])]

print("\nUkraine, fire points per month, counted the VIIRS way.  · far below  ░ below  ▒ usual  ▓ above  █ far above the usual for that month")
print("       " + " ".join(f"{n}" for n in MONTHS) + "   year total   source")
for y in years:
    src = "VIIRS" if y in overlap else "MODIS x multiplier"
    print(f"{y}   " + " ".join(shade(H[y, m], m) for m in range(1, 13)) + f"   {sum(H[y, m] for m in range(1, 13)):9.0f}   {src}")
print("usual  " + " ".join(f"{normal[m] / 1000:3.0f}" for m in range(1, 13)) + "   (thousand points)")

print("\nThe same years drawn twice: from VIIRS (V) and from MODIS x multiplier (M)")
same = tot = 0
for y in overlap:
    print(f"{y} V " + " ".join(shade(H[y, m], m) for m in range(1, 13)))
    print(f"     M " + " ".join(shade(HM[y, m], m) for m in range(1, 13)))
    for m in range(1, 13):
        if normal[m] >= 1000:
            tot += 1
            same += bisect.bisect(EDGES, H[y, m] / normal[m]) == bisect.bisect(EDGES, HM[y, m] / normal[m])
print(f"cells with the same shade (months with a usual of 1000+ points): {same} of {tot} = {same / tot:.0%}")

print("\nAugust, year by year")
for y in (2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015):
    if y in overlap:
        print(f"  {y}  VIIRS counted {S[y, 8]:6d}                                  -> {H[y, 8]:7.0f} = x{H[y, 8] / normal[8]:.2f} of a usual August   (MODIS counted {A[y, 8]}, x{k[8]:.1f} = {HM[y, 8]:.0f})")
    else:
        print(f"  {y}  MODIS counted {A[y, 8]:6d}, x{k[8]:.1f} for August           -> {H[y, 8]:7.0f} = x{H[y, 8] / normal[8]:.2f} of a usual August")

print("\nShape of the year over the overlap years: share of the year's points in each month")
ta, ts = sum(A[y, m] for y in overlap for m in range(1, 13)), sum(S[y, m] for y in overlap for m in range(1, 13))
print("  MODIS as counted : " + " ".join(f"{sum(A[y, m] for y in overlap) / ta:4.0%}" for m in range(1, 13)))
print("  VIIRS            : " + " ".join(f"{sum(S[y, m] for y in overlap) / ts:4.0%}" for m in range(1, 13)))
