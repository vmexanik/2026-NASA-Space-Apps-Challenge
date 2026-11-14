#!/usr/bin/env python3
"""When did Terra and Aqua pass over Ukraine each year (local solar time), and how did their counts compare?

Usage: python3 -I drift.py <folder with modis_*_Ukraine.csv>
"""
import csv
import glob
import os
import statistics as st
import sys
from collections import Counter, defaultdict

times = defaultdict(list)          # (sat, year) -> local solar hours of daytime rows
count = Counter()                  # (sat, year, season) -> daytime vegetation fire rows
versions = defaultdict(Counter)
for path in sorted(glob.glob(os.path.join(sys.argv[1], "modis_*_Ukraine.csv"))):
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["daynight"] != "D":
                continue
            y, m = int(r["acq_date"][:4]), int(r["acq_date"][5:7])
            t = int(r["acq_time"])
            local = (t // 100 + (t % 100) / 60 + float(r["longitude"]) / 15) % 24
            sat = r["satellite"]
            times[sat, y].append(local)
            versions[y][r["version"]] += 1
            if r.get("type", "0") in ("0", ""):
                season = "spring" if m in (3, 4) else "summer" if m in (7, 8) else "autumn" if m in (9, 10) else "other"
                count[sat, y, season] += 1
                count[sat, y, "all"] += 1

hm = lambda h: "%02d:%02d" % divmod(int(round(h * 60)), 60)
print("year | Terra local time (median, 10-90%) | Aqua local time (median, 10-90%) | Terra/Aqua daytime fires: all, Mar-Apr, Jul-Aug, Sep-Oct | versions")
for y in sorted({k[1] for k in times}):
    row = [str(y)]
    for sat in ("Terra", "Aqua"):
        v = sorted(times.get((sat, y), []))
        row.append(f"{hm(st.median(v))} ({hm(v[len(v) // 10])}-{hm(v[len(v) * 9 // 10])}) n={len(v):6d}" if len(v) > 20 else "   -  ")
    rat = []
    for s in ("all", "spring", "summer", "autumn"):
        a, t = count["Aqua", y, s], count["Terra", y, s]
        rat.append(f"{t / a:4.2f}" if a >= 50 else " n/a")
    print(" | ".join(row) + " | " + "  ".join(rat) + " | " + ",".join(f"{k}:{n}" for k, n in versions[y].most_common(3)))
