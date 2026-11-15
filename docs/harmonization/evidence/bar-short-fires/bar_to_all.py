#!/usr/bin/env python3
"""The power bar as a signal for all fires: predict all VIIRS points of a month from the MODIS (Aqua) points of
that month that pass the bar (daytime, FRP of 10 MW or more), with one factor per calendar month.

Usage: python3 -I bar_to_all.py <dir of npz files from extract.py> <out.json> <Country> [<Country> ...]

Learned on 2012-2016 and tested on 2017-2022, then the other way round, as in evaluate.py. Printed beside it, on the
same months and the same criteria: approach 2 (all MODIS points).
"""
import json
import sys

import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
COUNTRIES = sys.argv[3:]
YEARS = list(range(2012, 2023))
NM = len(YEARS) * 12
CAL = np.tile(np.arange(12), len(YEARS))
D0 = np.datetime64("2000-01-01")
EDGES = [0.5, 0.8, 1.25, 2.0]


def months(t):
    return (D0 + (t // 1440).astype("timedelta64[D]")).astype("datetime64[M]").astype(int) - (2012 - 1970) * 12


def load(country, sensor):
    parts = [np.load(f"{SRC}/{country}_{sensor}_{y}.npz") for y in YEARS]
    d = {k: np.concatenate([p[k] for p in parts]) for k in parts[0].files}
    if sensor == "modis":
        keep = d["aqua"] == 1
        d = {k: v[keep] for k, v in d.items()}
    d["m"] = months(d["t"])
    return d


def monthly(m, sel=None):
    return np.bincount(m if sel is None else m[sel], minlength=NM).astype(float)


def month_factor(num, den, tr):
    k = np.zeros(12)
    for c in range(12):
        s = tr & (CAL == c)
        k[c] = num[s].sum() / max(den[s].sum(), 1e-9)
    return k[CAL]


def predict(target, signal):
    pred = np.full(NM, np.nan)
    for train in (range(2012, 2017), range(2017, 2023)):
        tr = np.isin(np.repeat(YEARS, 12), list(train))
        pred[~tr] = (month_factor(target, signal, tr) * signal)[~tr]
    return pred


def scores(pred, target, vc):
    big = (vc >= 100) & (target > 0) & (pred > 0)
    err = np.median(np.abs(pred[big] / target[big] - 1))
    norm = np.array([target[CAL == c].mean() for c in range(12)])[CAL]
    ok = np.array([vc[CAL == c].mean() for c in range(12)])[CAL] >= 100
    same = np.mean(np.digitize(pred / norm, EDGES)[ok] == np.digitize(target / norm, EDGES)[ok])
    return err, same


result = {}
for country in COUNTRIES:
    M, V = load(country, "modis"), load(country, "viirs-snpp")
    vc, mc = monthly(V["m"]), monthly(M["m"])
    mbar = monthly(M["m"], (M["day"] == 1) & (M["frp"] >= 10))
    rows = [("2: all MODIS -> all VIIRS", predict(vc, mc), vc),
            ("bar MODIS -> all VIIRS", predict(vc, mbar), vc)]
    print(country)
    result[country] = {}
    for key, (name, pred, target) in zip(("all", "bar"), rows):
        err, same = scores(pred, target, vc)
        result[country][key] = {"err": float(err), "cal": float(same)}
        print(f"  {name:28s} error {err:6.1%}  calendar same colour {same:6.1%}")
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(result, fh)
