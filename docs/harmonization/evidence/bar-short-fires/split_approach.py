#!/usr/bin/env python3
"""Two factors instead of one: MODIS points that pass the power bar and the rest of the MODIS points each get their
own factor per calendar month, and the sum predicts all VIIRS points of the month.

Usage: python3 -I split_approach.py <dir of npz files from extract.py> <out.json> <Country> [<Country> ...]

The bar is that of approach 5: a MODIS (Aqua) point passes it by day with FRP of 10 MW or more; a VIIRS point passes
it by day when its ~1 km cell sums 10 MW or more over the points of that pass. Variants, all predicting all VIIRS
points, learned on 2012-2016 and tested on 2017-2022 and back, scored as in evaluate.py:
  all     approach 2: k_m * M
  bar     bar MODIS only: k_m * M_bar (the rest of MODIS is thrown away)
  split   k1_m * M_bar + k2_m * M_rest, k1 = sum V_bar points / sum M_bar, k2 = sum V_rest points / sum M_rest
  daynight k1_m * M_day + k2_m * M_night, the same with day and night
Also printed: the shares of MODIS and VIIRS points by day with the bar, by day without it, and by night.
"""
import json
import math
import sys

import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
COUNTRIES = sys.argv[3:]
YEARS = list(range(2012, 2023))
NM = len(YEARS) * 12
CAL = np.tile(np.arange(12), len(YEARS))
D0 = np.datetime64("2000-01-01")
EDGES = [0.5, 0.8, 1.25, 2.0]
BAR = 10.0


def load(country, sensor):
    parts = [np.load(f"{SRC}/{country}_{sensor}_{y}.npz") for y in YEARS]
    d = {k: np.concatenate([p[k] for p in parts]) for k in parts[0].files}
    if sensor == "modis":
        keep = d["aqua"] == 1
        d = {k: v[keep] for k, v in d.items()}
    order = np.argsort(d["t"], kind="stable")
    d = {k: v[order] for k, v in d.items()}
    d["m"] = (D0 + (d["t"] // 1440).astype("timedelta64[D]")).astype("datetime64[M]").astype(int) - (2012 - 1970) * 12
    return d


def viirs_kept(d):
    pass_id = np.concatenate([[0], np.cumsum(np.diff(d["t"]) > 20)])
    iy = np.floor(d["lat"] / 0.01).astype(np.int64)
    ix = np.floor(d["lon"] * np.cos(np.radians(d["lat"])) / 0.01).astype(np.int64)
    day = d["day"] == 1
    key = pass_id * 10**10 + (iy + 20000) * 100000 + (ix + 50000)
    kept = np.zeros(len(key), bool)
    _, inv = np.unique(key[day], return_inverse=True)
    kept[np.flatnonzero(day)] = (np.bincount(inv, weights=d["frp"][day]) >= BAR)[inv]
    return kept


def monthly(m, sel):
    return np.bincount(m[sel], minlength=NM).astype(float)


def factor(num, den, tr):
    k = np.zeros(12)
    for c in range(12):
        s = tr & (CAL == c)
        k[c] = num[s].sum() / max(den[s].sum(), 1e-9)
    return k[CAL]


def predict(target, parts):
    """parts: list of (VIIRS part, MODIS part); the prediction sums factor * MODIS part over the parts."""
    pred = np.full(NM, np.nan)
    for train in (range(2012, 2017), range(2017, 2023)):
        tr = np.isin(np.repeat(YEARS, 12), list(train))
        p = sum(factor(v, m, tr) * m for v, m in parts)
        pred[~tr] = p[~tr]
    return pred


def scores(pred, vc):
    big = (vc >= 100) & (pred > 0)
    err = float(np.median(np.abs(pred[big] / vc[big] - 1)))
    bias = float(np.exp(np.mean(np.log(pred[big] / vc[big]))) - 1)
    stab = float(np.std([math.log(pred[i * 12:i * 12 + 12].sum() / vc[i * 12:i * 12 + 12].sum()) for i in range(len(YEARS))]))
    norm = np.array([vc[CAL == c].mean() for c in range(12)])[CAL]
    ok = norm >= 100
    cal = float(np.mean(np.digitize(pred / norm, EDGES)[ok] == np.digitize(vc / norm, EDGES)[ok]))
    return {"err": err, "bias": bias, "stab": stab, "cal": cal}


result = {}
for country in COUNTRIES:
    M, V = load(country, "modis"), load(country, "viirs-snpp")
    allm, allv = np.ones(len(M["m"]), bool), np.ones(len(V["m"]), bool)
    mday, vday = M["day"] == 1, V["day"] == 1
    mbar = mday & (M["frp"] >= BAR)
    vbar = viirs_kept(V)
    vc, mc = monthly(V["m"], allv), monthly(M["m"], allm)
    MB, MR = monthly(M["m"], mbar), monthly(M["m"], ~mbar)
    VB, VR = monthly(V["m"], vbar), monthly(V["m"], ~vbar)
    MD, MN = monthly(M["m"], mday), monthly(M["m"], ~mday)
    VD, VN = monthly(V["m"], vday), monthly(V["m"], ~vday)
    r = {
        "modis_shares": {"day_bar": float(mbar.mean()), "day_weak": float((mday & ~mbar).mean()), "night": float((~mday).mean())},
        "viirs_shares": {"day_bar": float(vbar.mean()), "day_weak": float((vday & ~vbar).mean()), "night": float((~vday).mean())},
        "all": scores(predict(vc, [(vc, mc)]), vc),
        "bar": scores(predict(vc, [(vc, MB)]), vc),
        "split": scores(predict(vc, [(VB, MB), (VR, MR)]), vc),
        "daynight": scores(predict(vc, [(VD, MD), (VN, MN)]), vc),
    }
    result[country] = r
    ms, vs = r["modis_shares"], r["viirs_shares"]
    print(f"{country}: MODIS points day+bar {ms['day_bar']:.1%}, day weak {ms['day_weak']:.1%}, night {ms['night']:.1%}; "
          f"VIIRS points day+bar {vs['day_bar']:.1%}, day weak {vs['day_weak']:.1%}, night {vs['night']:.1%}")
    for k in ("all", "bar", "split", "daynight"):
        s = r[k]
        print(f"  {k:9s} error {s['err']:6.1%}  bias {s['bias']:+6.1%}  stability {s['stab']:6.1%}  calendar {s['cal']:6.1%}")
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(result, fh)
