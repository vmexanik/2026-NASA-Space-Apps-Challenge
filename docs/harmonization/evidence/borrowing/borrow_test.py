#!/usr/bin/env python3
"""Borrowing for the factor of a 2-degree square and calendar month: from neighbouring squares, neighbouring months,
both, a bigger square, or the whole region; and how strongly.

Usage: python3 -I borrow_test.py <dir of npz files from extract.py> <out.json> <Country> [<Country> ...]

Each year of 2012-2022 is predicted with factors learned on the other ten years (Aqua against Suomi NPP, vegetation
fires only). With M and V the MODIS and VIIRS points of the square and month in the other years, a variant's factor is
  own        V / M; with no MODIS point, the factor of the whole region for the month
  borrowing  (V + lam * k_n) / (M + lam), where k_n = (V_n + lam * k_region) / (M_n + lam) is the factor of the
             neighbourhood n, itself drawn toward the region's
Neighbourhoods: cross (4 squares around, same month), ring (8 squares), months (the same square, months m-1 and
m+1), cross+months (both pooled), big square (the 8-degree square it lies in, same month), region (the whole region of
the country loaded, as approach 15). lam runs over 10, 30, 100, 300, 1000 MODIS points.
Scored on fixed areas of 0.5 and 2 degrees, area-months with 100 or more VIIRS points: error (median
|predicted / actual - 1|) and calendar colour match; the error also apart for square-months whose own data in the
other years hold fewer than 100 MODIS points (sparse) and the rest (rich).
"""
import json
import math
import sys

import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
COUNTRIES = sys.argv[3:]
YEARS = list(range(2012, 2023))
NY = len(YEARS)
SIZE, BASE, PARENT = 2.0, 0.25, 8.0
QUERIES = [0.5, 2.0]
EDGES = [0.5, 0.8, 1.25, 2.0]
LAMBDAS = [10, 30, 100, 300, 1000]
SPARSE = 100
D0 = np.datetime64("2000-01-01")
VARIANTS = ["own", "cross", "ring", "months", "cross+months", "big square", "region"]


def load(country, sensor):
    parts = [np.load(f"{SRC}/{country}_{sensor}_{y}.npz") for y in YEARS]
    d = {k: np.concatenate([p[k] for p in parts]) for k in ("lat", "lon", "t", "aqua")}
    if sensor == "modis":
        keep = d["aqua"] == 1
        d = {k: v[keep] for k, v in d.items()}
    ym = (D0 + (d["t"] // 1440).astype("timedelta64[D]")).astype("datetime64[M]").astype(int) - (2012 - 1970) * 12
    d["yi"], d["cm"] = ym // 12, ym % 12
    return d


def frame_of(size, M, V, pad=0):
    lat = np.concatenate([M["lat"], V["lat"]])
    lon = np.concatenate([M["lon"], V["lon"]])
    r0 = int(math.floor((lat.min() + 90) / size)) - pad
    c0 = int(math.floor((lon.min() + 180) / size)) - pad
    R = int(math.floor((lat.max() + 90) / size)) - r0 + 1 + pad
    C = int(math.floor((lon.max() + 180) / size)) - c0 + 1 + pad
    return r0, c0, R, C


def grid(d, size, frame):
    r0, c0, R, C = frame
    r = np.floor((d["lat"] + 90) / size).astype(np.int64) - r0
    c = np.floor((d["lon"] + 180) / size).astype(np.int64) - c0
    key = ((r * C + c) * NY + d["yi"]) * 12 + d["cm"]
    return np.bincount(key, minlength=R * C * NY * 12).reshape(R, C, NY, 12).astype(float)


def shift(a, dr, dc):
    """a moved by dr rows and dc columns, zeros where nothing moves in."""
    out = np.zeros_like(a)
    R, C = a.shape[:2]
    rs, rd = (slice(0, R - dr), slice(dr, R)) if dr >= 0 else (slice(-dr, R), slice(0, R + dr))
    cs, cd = (slice(0, C - dc), slice(dc, C)) if dc >= 0 else (slice(-dc, C), slice(0, C + dc))
    out[rd, cd] = a[rs, cs]
    return out


def neighbourhood(name, Mo, Vo, frame):
    if name == "cross":
        offs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    elif name == "ring":
        offs = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0)]
    else:
        offs = []
    Mn = sum((shift(Mo, dr, dc) for dr, dc in offs), np.zeros_like(Mo))
    Vn = sum((shift(Vo, dr, dc) for dr, dc in offs), np.zeros_like(Vo))
    if name in ("months", "cross+months"):
        Mt = np.roll(Mo, 1, axis=3) + np.roll(Mo, -1, axis=3)
        Vt = np.roll(Vo, 1, axis=3) + np.roll(Vo, -1, axis=3)
        if name == "months":
            Mn, Vn = Mt, Vt
        else:
            Mc = sum(shift(Mo, dr, dc) for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)])
            Vc = sum(shift(Vo, dr, dc) for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)])
            Mn, Vn = Mc + Mt, Vc + Vt
    if name == "big square":
        r0, c0, R, C = frame
        f = int(round(PARENT / SIZE))
        pr = (r0 + np.arange(R)) // f
        pc = (c0 + np.arange(C)) // f
        pr, pc = pr - pr.min(), pc - pc.min()
        key = (pr[:, None] * (pc.max() + 1) + pc[None, :]).ravel()
        n = key.max() + 1
        Mp = np.zeros((n,) + Mo.shape[2:])
        Vp = np.zeros((n,) + Vo.shape[2:])
        np.add.at(Mp, key, Mo.reshape((-1,) + Mo.shape[2:]))
        np.add.at(Vp, key, Vo.reshape((-1,) + Vo.shape[2:]))
        Mn = Mp[key].reshape(Mo.shape) - Mo
        Vn = Vp[key].reshape(Vo.shape) - Vo
    return Mn, Vn


def study(country):
    M, V = load(country, "modis"), load(country, "viirs-snpp")
    bf = frame_of(BASE, M, V)
    Mb, Vb = grid(M, BASE, bf), grid(V, BASE, bf)
    sf = frame_of(SIZE, M, V, pad=1)
    Ms, Vs = grid(M, SIZE, sf), grid(V, SIZE, sf)
    Mo = Ms.sum(2, keepdims=True) - Ms
    Vo = Vs.sum(2, keepdims=True) - Vs
    tm, tv = Mb.sum(axis=(0, 1)), Vb.sum(axis=(0, 1))
    k_region = (tv.sum(0, keepdims=True) - tv) / np.maximum(tm.sum(0, keepdims=True) - tm, 1)  # NY, 12
    kr = np.broadcast_to(k_region, Mo.shape)
    f = int(round(SIZE / BASE))
    rows = (bf[0] + np.arange(bf[2])) // f - sf[0]
    cols = (bf[1] + np.arange(bf[3])) // f - sf[1]
    sparse_sq = Mo < SPARSE
    areas = {}
    for q in QUERIES:
        g = int(round(q / BASE))
        qr = (bf[0] + np.arange(bf[2])) // g
        qc = (bf[1] + np.arange(bf[3])) // g
        qr, qc = qr - qr.min(), qc - qc.min()
        key = (qr[:, None] * (qc.max() + 1) + qc[None, :]).ravel()
        A = np.zeros((key.max() + 1, NY, 12))
        np.add.at(A, key, Vb.reshape(-1, NY, 12))
        # each area lies inside one 2-degree square: its sparse flag
        sp_b = sparse_sq[rows[:, None], cols[None, :]].reshape(-1, NY, 12).astype(float)
        S = np.zeros_like(A)
        Nb = np.zeros_like(A)
        np.add.at(S, key, sp_b)
        np.add.at(Nb, key, np.ones_like(sp_b))
        areas[q] = (key, A, S / np.maximum(Nb, 1) > 0.5)
    hoods = {n: neighbourhood(n, Mo, Vo, sf) for n in VARIANTS if n not in ("own", "region")}
    out = {"sparse_share": {}, "variants": {}}
    for q, (key, A, sp) in areas.items():
        sel = A >= 100
        out["sparse_share"][str(q)] = float(A[sel & sp].sum() / A[sel].sum())

    def score(K):
        Kb = K[rows[:, None], cols[None, :]]
        pred = Kb * Mb
        res = {}
        for q, (key, A, sp) in areas.items():
            P = np.zeros_like(A)
            np.add.at(P, key, pred.reshape(-1, NY, 12))
            sel = A >= 100
            rel = np.abs(P / np.where(sel, A, 1) - 1)
            norm = A.mean(1, keepdims=True)
            ok = np.broadcast_to(norm >= 100, A.shape)
            with np.errstate(divide="ignore", invalid="ignore"):
                cal = float(np.mean(np.digitize(P / norm, EDGES)[ok] == np.digitize(A / norm, EDGES)[ok]))
            res[str(q)] = {"error": float(np.median(rel[sel])), "calendar": cal,
                           "error_sparse": float(np.median(rel[sel & sp])) if (sel & sp).any() else None,
                           "error_rich": float(np.median(rel[sel & ~sp])) if (sel & ~sp).any() else None}
        return res

    with np.errstate(divide="ignore", invalid="ignore"):
        K_own = np.where(Mo > 0, Vo / Mo, kr)
    out["variants"]["own"] = {"-": score(K_own)}
    for name in VARIANTS[1:]:
        out["variants"][name] = {}
        for lam in LAMBDAS:
            if name == "region":
                k_n = kr
            else:
                Mn, Vn = hoods[name]
                k_n = (Vn + lam * kr) / (Mn + lam)
            K = (Vo + lam * k_n) / (Mo + lam)
            out["variants"][name][str(lam)] = score(K)
    return out


if __name__ == "__main__":
    result = {"lambdas": LAMBDAS, "variants": VARIANTS, "countries": {}}
    for c in COUNTRIES:
        r = study(c)
        result["countries"][c] = r
        print(c, "sparse share of fires (0.5deg / 2deg areas):",
              " / ".join(f"{v:.1%}" for v in r["sparse_share"].values()))
        o = r["variants"]["own"]["-"]
        print(f"  {'own':13s}            0.5deg {o['0.5']['error']:6.2%} (sparse {o['0.5']['error_sparse'] or 0:6.1%})  "
              f"2deg {o['2.0']['error']:6.2%} cal {o['2.0']['calendar']:6.1%}")
        for name in VARIANTS[1:]:
            for lam in LAMBDAS:
                s = r["variants"][name][str(lam)]
                print(f"  {name:13s} lam {lam:5d}  0.5deg {s['0.5']['error']:6.2%} (sparse {s['0.5']['error_sparse'] or 0:6.1%})  "
                      f"2deg {s['2.0']['error']:6.2%} cal {s['2.0']['calendar']:6.1%}", flush=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
