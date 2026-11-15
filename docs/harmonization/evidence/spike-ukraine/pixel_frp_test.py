#!/usr/bin/env python3
"""Do the MODIS pixel size and the fire power (FRP) of a point improve the MODIS -> VIIRS conversion?

Part 1 counts the Suomi NPP points that fall inside one Aqua pixel seen in the same 10 minutes.
Part 2 predicts the Suomi NPP count of a day and of a month from the Aqua points, with the weight
of an Aqua point depending on the calendar month only, or also on its pixel size, its FRP, or both.

Usage: python3 -I pixel_frp_test.py <folder with *_Ukraine.csv> [<first year> <first test year> <last year>]
"""
import bisect
import csv
import glob
import math
import os
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import date

import numpy as np

DATA = sys.argv[1]
D0 = date(2012, 1, 1).toordinal()
LAT0, LON0, DLAT, DLON, NLON = 43.0, 21.0, 0.01, 0.015, 2000
_Y0, _YS, _Y1 = (int(v) for v in sys.argv[2:5]) if len(sys.argv) >= 5 else (2012, 2014, 2015)
YEARS = tuple(range(_Y0, _Y1 + 1))
TRAIN, TEST = tuple(range(_Y0, _YS)), tuple(range(_YS, _Y1 + 1))
SCAN_EDGES, SCAN_NAMES = [1.2, 1.5, 2.0, 3.0], ["1.0-1.2", "1.2-1.5", "1.5-2.0", "2.0-3.0", "3.0-4.8"]
FRP_EDGES, FRP_NAMES = [10, 20, 50, 100], ["<10", "10-20", "20-50", "50-100", ">100"]
SCAN3, FRP3 = [1.3, 2.0], [15, 50]
RIDGE = 0.3


def load(pattern: str, sat: str | None = None):
    """Vegetation fire rows: (day, minute, lat, lon, scan, track, frp, night, year, month)."""
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
                rows.append((date(y, m, d).toordinal() - D0, (t // 100) * 60 + t % 100, float(r["latitude"]),
                             float(r["longitude"]), float(r["scan"]), float(r["track"]), float(r["frp"] or 0),
                             0 if r["daynight"] == "D" else 1, y, m))
    return rows


def passes(rows):
    at = [r[0] * 1440 + r[1] for r in rows]
    starts, pid, last = [], {}, -10**9
    for t in sorted(set(at)):
        if t - last > 20:
            starts.append(t)
        pid[t] = len(starts) - 1
        last = t
    groups = defaultdict(list)
    for i, t in enumerate(at):
        groups[pid[t]].append(i)
    return [st.median(at[i] for i in groups[k]) for k in range(len(starts))], groups


aq = load("modis_*_Ukraine.csv", "Aqua")
sn = load("viirs-snpp_*_Ukraine.csv")
print(f"vegetation fire rows {YEARS[0]}-{YEARS[-1]}: Aqua {len(aq)}, Suomi NPP {len(sn)}")

# ------------------------------------------------------------------ part 1
print("\n== 1. Suomi NPP points inside one Aqua pixel, passes at most 10 min apart, daytime")
amid, agrp = passes(aq)
smid, sgrp = passes(sn)
inside = []   # (scan, frp, n of SNPP points inside, pixel area)
for ia, t in enumerate(amid):
    j = bisect.bisect_left(smid, t)
    best = min((jj for jj in (j - 1, j) if 0 <= jj < len(smid)), key=lambda jj: abs(smid[jj] - t), default=None)
    if best is None or abs(smid[best] - t) > 10:
        continue
    grid = defaultdict(list)
    for i in sgrp[best]:
        grid[int((sn[i][2] - LAT0) / DLAT), int((sn[i][3] - LON0) / DLON)].append((sn[i][2], sn[i][3]))
    for i in agrp[ia]:
        _, _, lat, lon, scan, track, frp, night, _, _ = aq[i]
        if night:
            continue
        dlat = (track / 2 + 0.3) / 111.2
        dlon = (scan / 2 + 0.3) / (111.2 * math.cos(math.radians(lat)))
        la, lo = int((lat - LAT0) / DLAT), int((lon - LON0) / DLON)
        ra, ro = int(dlat / DLAT) + 1, int(dlon / DLON) + 1
        n = sum(1 for a in range(la - ra, la + ra + 1) for o in range(lo - ro, lo + ro + 1)
                for (y, x) in grid.get((a, o), ()) if abs(y - lat) <= dlat and abs(x - lon) <= dlon)
        inside.append((scan, frp, n, scan * track))
print(f"  Aqua daytime points in such passes: {len(inside)}")


def table(title: str, key, names) -> None:
    print(f"  by {title}:")
    for b, name in enumerate(names):
        v = [r for r in inside if key(r) == b]
        if v:
            ns = [r[2] for r in v]
            print(f"    {name:>8s}  Aqua points {len(v):6d}  pixel area {st.mean(r[3] for r in v):5.1f} km2  "
                  f"Suomi NPP points inside: mean {st.mean(ns):5.2f}, median {st.median(ns):4.1f}, none inside {sum(n == 0 for n in ns) / len(ns):5.1%}")


table("Aqua pixel width (scan, km)", lambda r: bisect.bisect(SCAN_EDGES, r[0]), SCAN_NAMES)
table("Aqua point power (FRP, MW)", lambda r: bisect.bisect(FRP_EDGES, r[1]), FRP_NAMES)
print("  mean Suomi NPP points inside, by pixel width (rows) and power (columns: <15, 15-50, >50 MW):")
for c, cname in enumerate(("  <=1.3 km", "1.3-2.0 km", "  >2.0 km")):
    cells = []
    for f in range(3):
        v = [r[2] for r in inside if bisect.bisect(SCAN3, r[0]) == c and bisect.bisect(FRP3, r[1]) == f]
        cells.append(f"{st.mean(v):5.2f} (n={len(v)})" if v else "   n/a")
    print(f"    {cname}: " + "   ".join(cells))

# ------------------------------------------------------------------ part 2
print("\n== 2. predict Suomi NPP counts from Aqua points; an Aqua point's weight = month factor x class weight")
S = Counter(r[0] for r in sn)
ym = {}
for r in aq + sn:
    ym[r[0]] = (r[8], r[9])
scans = defaultdict(list)
frps = defaultdict(list)
for r in aq:
    scans[r[0]].append(r[4])
    frps[r[0]].append(r[6])
A = Counter(r[0] for r in aq)
num, den = Counter(), Counter()
for d in ym:
    num[ym[d][1]] += S[d]
    den[ym[d][1]] += A[d]
kall = {m: num[m] / den[m] for m in den if den[m]}
print("  days with 20+ Aqua points: Suomi NPP count / (Aqua count x month factor), by what Aqua's pixels were like that day")
for title, src, edges, names in (("median pixel width, km", scans, [1.15, 1.3, 1.6, 2.2], ["<1.15", "1.15-1.3", "1.3-1.6", "1.6-2.2", ">2.2"]),
                                 ("median point power, MW", frps, [8, 12, 18, 30], ["<8", "8-12", "12-18", "18-30", ">30"])):
    print(f"    by the day's {title}:")
    for b, name in enumerate(names):
        rs = [S[d] / (kall[ym[d][1]] * A[d]) for d in A if A[d] >= 20 and bisect.bisect(edges, st.median(src[d])) == b]
        if rs:
            print(f"      {name:>9s}  days {len(rs):4d}  median ratio {st.median(rs):5.2f}  middle half {np.percentile(rs, 25):4.2f}..{np.percentile(rs, 75):4.2f}")

FEATS = {
    "month only": (1, lambda r: 0),
    "month x pixel width": (5, lambda r: bisect.bisect(SCAN_EDGES, r[4])),
    "month x power (FRP)": (5, lambda r: bisect.bisect(FRP_EDGES, r[6])),
    "month x width x power": (9, lambda r: bisect.bisect(SCAN3, r[4]) * 3 + bisect.bisect(FRP3, r[6])),
}
feat = {}
for name, (ncls, cls) in FEATS.items():
    f = defaultdict(lambda n=ncls: np.zeros(n))
    for r in aq:
        f[r[0]][cls(r)] += 1
    feat[name] = f
area = defaultdict(lambda: np.zeros(1))
for r in aq:
    area[r[0]][0] += r[4] * r[5]
feat["month x pixel area, no fit"] = area
FEATS["month x pixel area, no fit"] = (1, None)
holes = [d for d in ym if A[d] >= 20 and S[d] == 0]
print(f"  days with 20+ Aqua points and no Suomi NPP point at all: {len(holes)} "
      + ", ".join(str(date.fromordinal(D0 + d)) for d in sorted(holes)[:12]) + "  (left out of the fits)")
ALL_DAYS = sorted(d for d in ym if d not in set(holes))


def fit(days, f, ncls):
    a = np.ones(ncls)
    k = {}
    for _ in range(40):
        num, den = Counter(), Counter()
        for d in days:
            num[ym[d][1]] += S[d]
            den[ym[d][1]] += float(a @ f[d])
        k = {m: (num[m] / den[m] if den[m] > 0 else 0.0) for m in range(1, 13)}
        if ncls == 1:
            break
        X, y = [], []
        for d in days:
            km = k[ym[d][1]]
            if km > 0:
                w = 1 / math.sqrt(float(f[d].sum()) + 1)
                X.append(f[d] * w)
                y.append(S[d] / km * w)
        X, y = np.array(X), np.array(y)
        lam = RIDGE * float(np.mean(np.sum(X * X, axis=0)))
        new = np.linalg.solve(X.T @ X + lam * np.eye(ncls), X.T @ y + lam * np.ones(ncls))
        new = np.clip(new, 0.05, None)
        tot = sum(f[d] for d in days)
        new = new * tot.sum() / float(new @ tot)
        done = np.allclose(new, a, rtol=1e-4)
        a = new
        if done:
            break
    num, den = Counter(), Counter()
    for d in days:
        num[ym[d][1]] += S[d]
        den[ym[d][1]] += float(a @ f[d])
    k = {m: (num[m] / den[m] if den[m] > 0 else 0.0) for m in range(1, 13)}
    return k, a


def evaluate(train, test) -> None:
    tr = [d for d in ALL_DAYS if ym[d][0] in train]
    te = [d for d in ALL_DAYS if ym[d][0] in test]
    print(f"  learn {train[0]}-{train[-1]}, test {test[0]}-{test[-1]}")
    for name, (ncls, _) in FEATS.items():
        f = feat[name]
        k, a = fit(tr, f, ncls)
        pred = {d: k[ym[d][1]] * float(a @ f[d]) for d in te}
        big = [d for d in te if S[d] >= 30]
        e_day = [abs(math.log((pred[d] + 1) / (S[d] + 1))) for d in big]
        pm, sm = Counter(), Counter()
        for d in te:
            pm[ym[d]] += pred[d]
            sm[ym[d]] += S[d]
        vals = sorted(sm.values())
        thr = vals[len(vals) // 4]
        e_mon = [abs(math.log(max(pm[key], 0.5) / sm[key])) for key in sm if sm[key] > thr]
        cls_w = "  class weights: " + " ".join(f"{x:.2f}" for x in a) if ncls > 1 else ""
        print(f"    {name:28s} typical day error {math.exp(st.median(e_day)) - 1:6.1%} (days within 50%: {sum(e <= math.log(1.5) for e in e_day) / len(e_day):4.0%}, n={len(e_day)})"
              f" | typical month error {math.exp(st.median(e_mon)) - 1:6.1%} (n={len(e_mon)}){cls_w}")


evaluate(TRAIN, TEST)
evaluate(TEST, TRAIN)
