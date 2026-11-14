#!/usr/bin/env python3
"""Does the factor of a square need the calendar month? One factor per square for the whole year, per season, per
calendar month, and per calendar month pooled with the months on either side.

Usage: python3 -I time_bins.py <dir of npz files from extract.py> <out.json> <size in degrees> <Country> [<Country> ...]

Each year of 2012-2022 is predicted with factors learned on the other ten years (Aqua against Suomi NPP, vegetation
fires only). Every 0.25-degree cell takes the factor of its square for the month's time bin; a square with no MODIS
point in that bin in the other years takes the factor of the whole country for the bin. Scored on fixed areas of
0.5 and 2 degrees, over area-months with 100 or more VIIRS points:
  error     median |predicted / actual - 1|
  calendar  share of area-months whose calendar colour (month / mean of that calendar month over 2012-2022 of the
            actual series, cut at 0.5, 0.8, 1.25, 2) matches; calendar months whose mean is 100 or more points
Also the shape of the year for each country: the share of the year's VIIRS points in each calendar month, actual
and as each variant predicts it.
"""
import json
import math
import sys

import numpy as np

SRC, OUT, SIZE = sys.argv[1], sys.argv[2], float(sys.argv[3])
COUNTRIES = sys.argv[4:]
YEARS = list(range(2012, 2023))
NY = len(YEARS)
BASE = 0.25
QUERIES = [0.5, 2.0]
EDGES = [0.5, 0.8, 1.25, 2.0]
D0 = np.datetime64("2000-01-01")
SEASON = np.array([0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 0])  # Dec-Feb, Mar-May, Jun-Aug, Sep-Nov
VARIANTS = {
    "year": [list(range(12))] * 12,
    "season": [[m2 for m2 in range(12) if SEASON[m2] == SEASON[m]] for m in range(12)],
    "month": [[m] for m in range(12)],
    "month3": [[(m - 1) % 12, m, (m + 1) % 12] for m in range(12)],
}


def load(country, sensor):
    parts = [np.load(f"{SRC}/{country}_{sensor}_{y}.npz") for y in YEARS]
    d = {k: np.concatenate([p[k] for p in parts]) for k in ("lat", "lon", "t", "aqua")}
    if sensor == "modis":
        keep = d["aqua"] == 1
        d = {k: v[keep] for k, v in d.items()}
    ym = (D0 + (d["t"] // 1440).astype("timedelta64[D]")).astype("datetime64[M]").astype(int) - (2012 - 1970) * 12
    d["yi"], d["cm"] = ym // 12, ym % 12
    return d


def frame_of(size, M, V):
    lat = np.concatenate([M["lat"], V["lat"]])
    lon = np.concatenate([M["lon"], V["lon"]])
    r0 = int(math.floor((lat.min() + 90) / size))
    c0 = int(math.floor((lon.min() + 180) / size))
    return r0, c0, int(math.floor((lat.max() + 90) / size)) - r0 + 1, int(math.floor((lon.max() + 180) / size)) - c0 + 1


def grid(d, size, frame):
    r0, c0, R, C = frame
    r = np.floor((d["lat"] + 90) / size).astype(np.int64) - r0
    c = np.floor((d["lon"] + 180) / size).astype(np.int64) - c0
    key = ((r * C + c) * NY + d["yi"]) * 12 + d["cm"]
    return np.bincount(key, minlength=R * C * NY * 12).reshape(R, C, NY, 12).astype(float)


def binned(a, sets):
    """For each calendar month, the sum of a over the months of its time bin."""
    return np.stack([a[..., s].sum(-1) for s in sets], -1)


def study(country):
    M, V = load(country, "modis"), load(country, "viirs-snpp")
    bf = frame_of(BASE, M, V)
    Mb, Vb = grid(M, BASE, bf), grid(V, BASE, bf)
    sf = frame_of(SIZE, M, V)
    Ms, Vs = grid(M, SIZE, sf), grid(V, SIZE, sf)
    f = int(round(SIZE / BASE))
    rows = (bf[0] + np.arange(bf[2])) // f - sf[0]
    cols = (bf[1] + np.arange(bf[3])) // f - sf[1]
    out = {"variants": {}, "shape": {}}
    actual_by_month = Vb.sum(axis=(0, 1, 2))
    out["shape"]["actual"] = (actual_by_month / actual_by_month.sum()).tolist()
    for name, sets in VARIANTS.items():
        Mbin, Vbin = binned(Ms, sets), binned(Vs, sets)  # R, C, NY, 12
        Mo = Mbin.sum(2, keepdims=True) - Mbin
        Vo = Vbin.sum(2, keepdims=True) - Vbin
        cm_, cv_ = binned(Mb.sum(axis=(0, 1)), sets), binned(Vb.sum(axis=(0, 1)), sets)  # NY, 12
        area_k = (cv_.sum(0, keepdims=True) - cv_) / np.maximum(cm_.sum(0, keepdims=True) - cm_, 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            K = np.where(Mo > 0, Vo / Mo, np.nan)
        Kb = K[rows[:, None], cols[None, :]]
        Kb = np.where(np.isfinite(Kb), Kb, area_k[None, None])
        pred = Kb * Mb
        pm = pred.sum(axis=(0, 1, 2))
        out["shape"][name] = (pm / pm.sum()).tolist()
        res = {"factors_per_square": len({tuple(s) for s in sets})}
        for q in QUERIES:
            g = int(round(q / BASE))
            qr = (bf[0] + np.arange(bf[2])) // g
            qc = (bf[1] + np.arange(bf[3])) // g
            qr, qc = qr - qr.min(), qc - qc.min()
            key = (qr[:, None] * (qc.max() + 1) + qc[None, :]).ravel()
            nq = key.max() + 1
            P = np.zeros((nq, NY, 12))
            A = np.zeros((nq, NY, 12))
            np.add.at(P, key, pred.reshape(-1, NY, 12))
            np.add.at(A, key, Vb.reshape(-1, NY, 12))
            sel = A >= 100
            err = float(np.median(np.abs(P[sel] / A[sel] - 1)))
            norm = A.mean(1, keepdims=True)
            ok = np.broadcast_to(norm >= 100, A.shape)
            with np.errstate(divide="ignore", invalid="ignore"):
                cal = float(np.mean(np.digitize(P / norm, EDGES)[ok] == np.digitize(A / norm, EDGES)[ok]))
            res[str(q)] = {"error": err, "calendar": cal}
        out["variants"][name] = res
    return out


if __name__ == "__main__":
    result = {"size": SIZE, "countries": {}}
    for c in COUNTRIES:
        r = study(c)
        result["countries"][c] = r
        print(c, f"(squares {SIZE} deg)")
        for name, v in r["variants"].items():
            print(f"  {name:7s} factors/square {v['factors_per_square']:2d}  "
                  f"0.5deg: error {v['0.5']['error']:6.1%} calendar {v['0.5']['calendar']:6.1%}   "
                  f"2deg: error {v['2.0']['error']:6.1%} calendar {v['2.0']['calendar']:6.1%}", flush=True)
        sh = r["shape"]
        print("  shape of the year (Jan..Dec):")
        for k in ("actual", "year", "month"):
            print(f"    {k:7s} " + " ".join(f"{x * 100:4.1f}" for x in sh[k]))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
