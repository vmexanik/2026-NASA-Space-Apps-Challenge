#!/usr/bin/env python3
"""All features at once: what goes with a month whose MODIS -> VIIRS multiplier is off its usual value?

One line per year-month. The target is how far the month's multiplier sits from the ten-year multiplier
of that calendar month. Every feature is an average property of the month's rows, taken as a departure
from its own usual value for that calendar month, so the season is out of both sides.

Usage: python3 -I feature_corr.py <folder with modis_*_Ukraine.csv and viirs-snpp_*_Ukraine.csv> [out.json]
"""
import csv
import glob
import json
import math
import os
import statistics as st
import sys
from collections import defaultdict
from datetime import date

import numpy as np

DATA = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else None
YEARS = list(range(2012, 2022))
BAR = 10.0
LAT0, LON0, DLAT, DLON, NLON = 43.0, 21.0, 0.01, 0.015, 2000

Y, MO, DN, FRP, SCAN, CONF, CONFN, LST, DT, T11, LAT, LON, CPF, CFRP = range(14)


def load(pattern: str, sat: str | None, viirs: bool) -> list[list]:
    raw = []
    for path in sorted(glob.glob(os.path.join(DATA, pattern))):
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["type"] != "0" or (sat and r["satellite"] != sat):
                    continue
                y, m, d = int(r["acq_date"][:4]), int(r["acq_date"][5:7]), int(r["acq_date"][8:10])
                if y not in YEARS:
                    continue
                t = int(r["acq_time"])
                minute = (t // 100) * 60 + t % 100
                lat, lon = float(r["latitude"]), float(r["longitude"])
                if viirs:
                    conf = {"l": 0, "n": 1, "h": 2}[r["confidence"][:1].lower()]
                    confn = (10, 60, 95)[conf]
                    t4, t11 = float(r["bright_ti4"]), float(r["bright_ti5"])
                else:
                    confn = int(r["confidence"])
                    conf = 0 if confn < 30 else (1 if confn < 80 else 2)
                    t4, t11 = float(r["brightness"]), float(r["bright_t31"])
                cell = int((lat - LAT0) / DLAT) * NLON + int((lon - LON0) / DLON)
                raw.append((date(y, m, d).toordinal() * 1440 + minute, cell,
                            [y, m, 0 if r["daynight"] == "D" else 1, float(r["frp"] or 0), float(r["scan"]), conf, confn,
                             (minute / 60 + lon / 15) % 24, t4 - t11, t11, lat, lon, 0, 0.0]))
    pid, n, last = {}, -1, -10**12
    for t in sorted({r[0] for r in raw}):
        if t - last > 20:
            n += 1
        pid[t] = n
        last = t
    cellpass = defaultdict(list)
    for t, cell, row in raw:
        cellpass[pid[t], cell].append(row)
    for group in cellpass.values():
        total = sum(r[FRP] for r in group)
        group[0][CPF] = 1
        for r in group:
            r[CFRP] = total
    return [row for _, _, row in raw]


print("loading...", flush=True)
M = load("modis_*_Ukraine.csv", "Aqua", False)
V = load("viirs-snpp_*_Ukraine.csv", None, True)


def by_month(rows):
    g = defaultdict(list)
    for r in rows:
        g[r[Y], r[MO]].append(r)
    return g


GM, GV = by_month(M), by_month(V)
mean = lambda v: sum(v) / len(v) if v else float("nan")
share = lambda rows, f: sum(1 for r in rows if f(r)) / len(rows) if rows else float("nan")

# every feature: name -> f(rows of MODIS in the month, rows of VIIRS in the month)
FEATURES = {
    "VIIRS: частка нічних точок": lambda m, v: share(v, lambda r: r[DN] == 1),
    "VIIRS: частка слабких клітинок, до 10 МВт": lambda m, v: share([r for r in v if r[CPF]], lambda r: r[CFRP] < BAR),
    "VIIRS: медіана сили точки": lambda m, v: math.log(st.median(r[FRP] for r in v) + 0.1),
    "VIIRS: точок на клітинку 1 км": lambda m, v: len(v) / sum(1 for r in v if r[CPF]),
    "VIIRS: середня ширина пікселя": lambda m, v: mean([r[SCAN] for r in v]),
    "VIIRS: частка низької впевненості": lambda m, v: share(v, lambda r: r[CONF] == 0),
    "VIIRS: медіана T4−T11": lambda m, v: st.median(r[DT] for r in v),
    "VIIRS: медіана температури фону T11": lambda m, v: st.median(r[T11] for r in v),
    "VIIRS: середня година денного прольоту": lambda m, v: mean([r[LST] for r in v if r[DN] == 0]),
    "MODIS: частка нічних точок": lambda m, v: share(m, lambda r: r[DN] == 1),
    "MODIS: частка слабких точок, до 10 МВт": lambda m, v: share(m, lambda r: r[FRP] < BAR),
    "MODIS: медіана сили точки": lambda m, v: math.log(st.median(r[FRP] for r in m) + 0.1),
    "MODIS: точок на клітинку 1 км": lambda m, v: len(m) / sum(1 for r in m if r[CPF]),
    "MODIS: середня ширина пікселя": lambda m, v: mean([r[SCAN] for r in m]),
    "MODIS: частка низької впевненості": lambda m, v: share(m, lambda r: r[CONF] == 0),
    "MODIS: середня впевненість": lambda m, v: mean([r[CONFN] for r in m]),
    "MODIS: медіана T4−T11": lambda m, v: st.median(r[DT] for r in m),
    "MODIS: медіана температури фону T11": lambda m, v: st.median(r[T11] for r in m),
    "MODIS: середня година денного прольоту": lambda m, v: mean([r[LST] for r in m if r[DN] == 0]),
    "Різниця годин прольоту, VIIRS − MODIS": lambda m, v: mean([r[LST] for r in v if r[DN] == 0]) - mean([r[LST] for r in m if r[DN] == 0]),
    "Місце: середня широта вогнів": lambda m, v: mean([r[LAT] for r in v]),
    "Місце: середня довгота вогнів": lambda m, v: mean([r[LON] for r in v]),
    "Скільки точок MODIS у місяці": lambda m, v: math.log(len(m)),
    "Рік": lambda m, v: float(m[0][Y]),
}
NAMES = list(FEATURES)

# targets: three ways to count, the same year-months
TARGETS = {
    "усі точки": (lambda r: True, lambda r: True),
    "без ночі": (lambda r: r[DN] == 0, lambda r: r[DN] == 0),
    "без ночі, вогні від 10 МВт": (lambda r: r[DN] == 0 and r[FRP] >= BAR, lambda r: r[DN] == 0 and r[CPF] == 1 and r[CFRP] >= BAR),
}
months = [(y, m) for y in YEARS for m in range(1, 13) if len(GM.get((y, m), [])) >= 50 and GV.get((y, m))]
print(f"year-months with 50+ MODIS points: {len(months)}")


def counts(pred_m, pred_v):
    cm = {k: sum(1 for r in GM[k] if pred_m(r)) for k in months}
    cv = {k: sum(1 for r in GV[k] if pred_v(r)) for k in months}
    return cm, cv


def target(pred_m, pred_v):
    cm, cv = counts(pred_m, pred_v)
    d = {}
    for mo in range(1, 13):
        ks = [k for k in months if k[1] == mo and cm[k] >= 20 and cv[k] > 0]
        if len(ks) < 3:
            continue
        pooled = sum(cv[k] for k in ks) / sum(cm[k] for k in ks)
        for k in ks:
            d[k] = math.log(cv[k] / cm[k] / pooled)
    return d


def anomalies(values: dict) -> dict:
    """Departure of each year-month from the usual value of its calendar month."""
    out = {}
    for mo in range(1, 13):
        ks = [k for k in values if k[1] == mo and not math.isnan(values[k])]
        if len(ks) < 3:
            continue
        mu = mean([values[k] for k in ks])
        for k in ks:
            out[k] = values[k] - mu
    return out


def ranks(x):
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b) -> float:
    ra, rb = ranks(np.asarray(a, float)), ranks(np.asarray(b, float))
    return float(np.corrcoef(ra, rb)[0, 1])


feat = {name: anomalies({k: f(GM[k], GV[k]) for k in months}) for name, f in FEATURES.items()}
targ = {name: target(*preds) for name, preds in TARGETS.items()}

print("\n== correlation of each feature with the month's departure of the multiplier (Spearman), three ways of counting")
print(f"{'feature':44s} " + " ".join(f"{t:>28s}" for t in TARGETS))
table = {}
for name in NAMES:
    row = []
    for t in TARGETS:
        ks = [k for k in months if k in feat[name] and k in targ[t]]
        row.append((spearman([feat[name][k] for k in ks], [targ[t][k] for k in ks]), len(ks)))
    table[name] = row
order = sorted(NAMES, key=lambda n: -abs(table[n][0][0]))
for name in order:
    print(f"{name:44s} " + " ".join(f"{r:+20.2f} (n={n:3d})" for r, n in table[name]))
for t in TARGETS:
    v = list(targ[t].values())
    print(f"  spread of the target '{t}': typical departure {math.exp(st.median(abs(x) for x in v)) - 1:.1%}, n={len(v)}")

# ------------------------------------------------------------ does the multiplier drift with the years?
print("\n== drift: change of the multiplier per year (departures against the year), with and without 2012")
drift = {}
for t in TARGETS:
    out = []
    for skip in (None, 2012):
        ks = [k for k in targ[t] if k[0] != skip]
        slope = float(np.polyfit([k[0] for k in ks], [targ[t][k] for k in ks], 1)[0])
        out.append(slope)
    by_year = {y: st.mean(targ[t][k] for k in targ[t] if k[0] == y) for y in YEARS if any(k[0] == y for k in targ[t])}
    drift[t] = {"perYear": out[0], "perYearWithout2012": out[1]}
    print(f"  [{t}] {math.expm1(out[0]):+.1%} a year ({math.expm1(out[0] * 9):+.0%} over 2012-2021); without 2012: {math.expm1(out[1]):+.1%} a year")
    print("      mean departure by year: " + " ".join(f"{y}:{math.expm1(v):+.0%}" for y, v in by_year.items()))

# ------------------------------------------------------------ all features together
print("\n== all features together: ridge regression, left-out-year check")


def design(tname, names):
    ks = [k for k in months if k in targ[tname] and all(k in feat[n] for n in names)]
    X = np.array([[feat[n][k] for n in names] for k in ks])
    X = (X - X.mean(0)) / np.where(X.std(0) > 0, X.std(0), 1)
    y = np.array([targ[tname][k] for k in ks])
    return ks, X, y - y.mean()


def cv_r2(tname, names, lam):
    ks, X, y = design(tname, names)
    pred = np.zeros(len(y))
    for yr in YEARS:
        te = np.array([k[0] == yr for k in ks])
        if not te.any():
            continue
        Xt, yt = X[~te], y[~te]
        w = np.linalg.solve(Xt.T @ Xt + lam * np.eye(len(names)), Xt.T @ yt)
        pred[te] = X[te] @ w
    return 1 - float(((y - pred) ** 2).sum() / (y ** 2).sum())


summary = {}
for t in TARGETS:
    best = max(((cv_r2(t, NAMES, lam), lam) for lam in (1, 3, 10, 30, 100, 300)), key=lambda p: p[0])
    # greedy: add the feature that raises the left-out-year score most
    chosen, score = [], 0.0
    while len(chosen) < 6:
        cand = max(((cv_r2(t, chosen + [n], 3), n) for n in NAMES if n not in chosen), key=lambda p: p[0])
        if cand[0] <= score + 0.01:
            break
        score = cand[0]
        chosen.append(cand[1])
        print(f"  [{t}] + {cand[1]:44s} -> explains {score:5.1%} of the departures in left-out years")
    print(f"  [{t}] all {len(NAMES)} features together (ridge {best[1]}): explains {best[0]:5.1%}; chosen {len(chosen)}: {score:5.1%}\n")
    summary[t] = {"all": best[0], "chosen": chosen, "chosenScore": score}

# ------------------------------------------------------------ features against each other
top = order[:10]
print("== the ten strongest features against each other (Spearman)")
mat = []
for a in top:
    row = []
    for b in top:
        ks = [k for k in months if k in feat[a] and k in feat[b]]
        row.append(spearman([feat[a][k] for k in ks], [feat[b][k] for k in ks]))
    mat.append(row)
    print(f"{a:44s} " + " ".join(f"{x:+5.2f}" for x in row))

if OUT:
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"targets": list(TARGETS), "order": order, "table": {n: [[round(r, 3), k] for r, k in table[n]] for n in NAMES},
                   "top": top, "matrix": [[round(x, 3) for x in row] for row in mat], "summary": summary, "drift": drift,
                   "nMonths": len(months)}, fh, ensure_ascii=False)
    print("wrote", OUT)
