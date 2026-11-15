#!/usr/bin/env python3
"""Concrete examples from the Ukraine spike: one same-minute pass, and months against their normal.

Usage: python3 -I examples.py <folder with *_Ukraine.csv>
"""
import bisect
import csv
import glob
import os
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import date

DATA = sys.argv[1]
D0 = date(2012, 1, 1).toordinal()
LAT0, LON0, DLAT, DLON, NLON = 43.0, 21.0, 0.01, 0.015, 2000
YEARS = (2012, 2013, 2014, 2015)


def load(pattern, sat=None):
    rows = []
    for path in sorted(glob.glob(os.path.join(DATA, pattern))):
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["type"] != "0" or (sat and r["satellite"] != sat):
                    continue
                y, m, d = int(r["acq_date"][:4]), int(r["acq_date"][5:7]), int(r["acq_date"][8:10])
                if y not in YEARS:
                    continue
                t = int(r["acq_time"])
                lat, lon = float(r["latitude"]), float(r["longitude"])
                rows.append((date(y, m, d).toordinal() - D0, (t // 100) * 60 + t % 100,
                             int((lat - LAT0) / DLAT) * NLON + int((lon - LON0) / DLON), float(r["frp"] or 0),
                             r["daynight"], y, m, lat, lon))
    return rows


def passes(rows):
    at = [r[0] * 1440 + r[1] for r in rows]
    starts, pid, last = [], {}, -10**9
    for t in sorted(set(at)):
        if t - last > 20:
            starts.append(t)
        pid[t] = len(starts) - 1
        last = t
    g = defaultdict(list)
    for i, t in enumerate(at):
        g[pid[t]].append(i)
    return [st.median(at[i] for i in g[k]) for k in range(len(starts))], g


def near(cell):
    la, lo = divmod(cell, NLON)
    return [(la + i) * NLON + lo + j for i in (-1, 0, 1) for j in (-1, 0, 1)]


aq, sn = load("modis_*_Ukraine.csv", "Aqua"), load("viirs-snpp_*_Ukraine.csv")
amid, ag = passes(aq)
smid, sg = passes(sn)
fmt = lambda t: f"{date.fromordinal(D0 + int(t) // 1440)} {int(t) % 1440 // 60:02d}:{int(t) % 60:02d} UTC"
pairs = []
for ia, t in enumerate(amid):
    j = bisect.bisect_left(smid, t)
    best = min((jj for jj in (j - 1, j) if 0 <= jj < len(smid)), key=lambda jj: abs(smid[jj] - t), default=None)
    if best is not None and abs(smid[best] - t) <= 5 and aq[ag[ia][0]][4] == "D":
        pairs.append((len(ag[ia]), ia, best))
print("== same-minute daytime passes, the busiest ones")
for n, ia, js in sorted(pairs, reverse=True)[:4]:
    ac = {aq[i][2] for i in ag[ia]}
    sc = {sn[i][2] for i in sg[js]}
    a_seen = sum(1 for c in ac if any(x in sc for x in near(c)))
    s_seen = sum(1 for c in sc if any(x in ac for x in near(c)))
    lons = [aq[i][8] for i in ag[ia]]
    print(f"  Aqua {fmt(amid[ia])} | Suomi NPP {fmt(smid[js])} | points: Aqua {n}, Suomi NPP {len(sg[js])} "
          f"| ~1 km fire cells: Aqua {len(ac)}, Suomi NPP {len(sc)} | Suomi NPP also has {a_seen} of Aqua's ({a_seen / len(ac):.0%}) "
          f"| Aqua also has {s_seen} of Suomi NPP's ({s_seen / len(sc):.0%}) | Aqua lon {min(lons):.1f}..{max(lons):.1f}")

print("\n== a month against its own normal (mean of the same month in the other three years)")
A = Counter((r[5], r[6]) for r in aq)
Sn = Counter((r[5], r[6]) for r in sn)
edges, names = [0.5, 0.8, 1.25, 2.0], ["far below", "below", "normal", "above", "far above"]
for y in (2014, 2015):
    for m in range(1, 13):
        na = st.mean(A[yy, m] for yy in YEARS if yy != y)
        ns = st.mean(Sn[yy, m] for yy in YEARS if yy != y)
        if ns < 100:
            continue
        ra, rs = A[y, m] / na, Sn[y, m] / ns
        print(f"  {y}-{m:02d}  Aqua {A[y, m]:6d} (normal {na:7.0f}) = x{ra:4.2f} {names[bisect.bisect(edges, ra)]:9s} | "
              f"Suomi NPP {Sn[y, m]:6d} (normal {ns:7.0f}) = x{rs:4.2f} {names[bisect.bisect(edges, rs)]:9s} "
              f"{'same' if bisect.bisect(edges, ra) == bisect.bisect(edges, rs) else 'NEIGHBOUR'}")
