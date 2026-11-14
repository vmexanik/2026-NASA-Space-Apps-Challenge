#!/usr/bin/env python3
"""Day and night apart: how many MODIS and VIIRS vegetation-fire points, the multiplier, and how well it predicts.

Usage: python3 -I daynight_probe.py <folder with modis_*_Ukraine.csv and viirs-snpp_*_Ukraine.csv>
"""
import csv
import glob
import math
import os
import statistics as st
import sys
from collections import Counter

DATA = sys.argv[1]
YEARS = list(range(2012, 2022))
MS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def counts(pattern, sat=None):
    c = Counter()
    for path in sorted(glob.glob(os.path.join(DATA, pattern))):
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["type"] != "0" or (sat and r["satellite"] != sat):
                    continue
                c[r["daynight"], int(r["acq_date"][:4]), int(r["acq_date"][5:7])] += 1
    return c


A, S = counts("modis_*_Ukraine.csv", "Aqua"), counts("viirs-snpp_*_Ukraine.csv")
for dn, name in (("D", "DAY"), ("N", "NIGHT")):
    ta = sum(A[dn, y, m] for y in YEARS for m in range(1, 13))
    ts = sum(S[dn, y, m] for y in YEARS for m in range(1, 13))
    print(f"\n== {name}: Aqua {ta} points, Suomi NPP {ts} points in ten years, overall ratio {ts / ta:.1f}")
    print("        " + " ".join(f"{m:>6s}" for m in MS))
    print("  Aqua  " + " ".join(f"{sum(A[dn, y, m] for y in YEARS):6d}" for m in range(1, 13)))
    print("  SNPP  " + " ".join(f"{sum(S[dn, y, m] for y in YEARS):6d}" for m in range(1, 13)))
    print("  ratio " + " ".join(f"{sum(S[dn, y, m] for y in YEARS) / max(sum(A[dn, y, m] for y in YEARS), 1):6.1f}" for m in range(1, 13)))
    for thr in (50, 20, 10):
        n = sum(1 for y in YEARS for m in range(1, 13) if A[dn, y, m] >= thr)
        print(f"  year-months with at least {thr} Aqua points: {n} of 120")
    print("  Aqua points per year-month:")
    for y in YEARS:
        print(f"    {y}  " + " ".join(f"{A[dn, y, m]:6d}" for m in range(1, 13)))

print("\n== share of night in each sensor's vegetation-fire points, by month (ten years)")
print("  Aqua  " + " ".join(f"{sum(A['N', y, m] for y in YEARS) / max(sum(A['N', y, m] + A['D', y, m] for y in YEARS), 1):6.1%}" for m in range(1, 13)))
print("  SNPP  " + " ".join(f"{sum(S['N', y, m] for y in YEARS) / max(sum(S['N', y, m] + S['D', y, m] for y in YEARS), 1):6.1%}" for m in range(1, 13)))


def test(src, dst, train, test_years):
    """src, dst: f(y, m). Factor per calendar month learned on train; typical month error on test."""
    kg = sum(dst(y, m) for y in train for m in range(1, 13)) / max(sum(src(y, m) for y in train for m in range(1, 13)), 1)
    k = {}
    for m in range(1, 13):
        sa = sum(src(y, m) for y in train)
        k[m] = sum(dst(y, m) for y in train) / sa if sa >= 10 else kg
    vals = sorted(dst(y, m) for y in test_years for m in range(1, 13))
    thr = vals[len(vals) // 4]
    errs = [abs(math.log(max(k[m] * src(y, m), 0.5) / dst(y, m))) for y in test_years for m in range(1, 13) if dst(y, m) > thr]
    return math.exp(st.median(errs)) - 1, sum(e <= math.log(1.25) for e in errs) / len(errs), len(errs)


both = lambda C: (lambda y, m: C["D", y, m] + C["N", y, m])
day = lambda C: (lambda y, m: C["D", y, m])
night = lambda C: (lambda y, m: C["N", y, m])
print("\n== factor per calendar month, learn five years, test the other five: typical month error (months within 25%)")
for name, src, dst in (("all MODIS -> all VIIRS (the plan)", both(A), both(S)),
                       ("day MODIS -> day VIIRS", day(A), day(S)),
                       ("night MODIS -> night VIIRS", night(A), night(S)),
                       ("day MODIS -> night VIIRS", day(A), night(S)),
                       ("day MODIS -> all VIIRS", day(A), both(S)),
                       ("day VIIRS -> night VIIRS (same eyes)", day(S), night(S))):
    r1 = test(src, dst, YEARS[:5], YEARS[5:])
    r2 = test(src, dst, YEARS[5:], YEARS[:5])
    print(f"  {name:38s} {r1[0]:6.1%} ({r1[1]:4.0%})   {r2[0]:6.1%} ({r2[1]:4.0%})   n={r1[2]},{r2[2]}")
