#!/usr/bin/env python3
"""Is the MODIS -> VIIRS factor of a square and calendar month the same in every year? Checked for six square sizes.

Usage: python3 -I square_stability.py <dir of npz files from extract.py> <out.json> <Country> [<Country> ...]

Squares are cut from the whole globe: row = floor((lat + 90) / size), column = floor((lon + 180) / size), so the
squares of every size nest. For each square, calendar month m and year y of 2012-2022 (Aqua against Suomi NPP,
vegetation fires only):
  factor of the year   k_y = V_y / M_y
  factor of the rest   K_rest = sum of V over the other ten years / sum of M over them
  change               |k_y / K_rest - 1|
A square-month needs MODIS points in at least 3 years. Its typical change is the median over its years. It is
  same      typical change <= 10%
  chance    more than 10%, but not more than 1.5 times what counting alone gives: too few fires to tell
  real      more than 10% and more than 1.5 times the counting noise: the factor really moves between years
  few years MODIS saw its fires in fewer than 3 years
Counting noise of a year: sqrt(1/M_y + 1/V_y + 1/M_rest + 1/V_rest) (Poisson); the typical change that noise alone
gives is 0.674 times its median over the years. Shares are weighted by VIIRS points.

Also, per size: the error a person would see on fixed areas of 0.5 and 2 degrees, each year predicted with factors
learned on the other ten years (a square-month with no MODIS point in the other years takes the factor of the whole
country for that month), and the drift: the yearly ratio of VIIRS points to what the all-years factors expect, as a
trend in percent per year.
"""
import json
import math
import sys

import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
COUNTRIES = sys.argv[3:]
YEARS = list(range(2012, 2023))
NY = len(YEARS)
SIZES = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
BASE = 0.25
QUERIES = [0.5, 2.0]
LIMIT = 0.10
NOISE_FACTOR = 1.5
MIN_YEARS = 3
D0 = np.datetime64("2000-01-01")


def load(country, sensor):
    parts = [np.load(f"{SRC}/{country}_{sensor}_{y}.npz") for y in YEARS]
    d = {k: np.concatenate([p[k] for p in parts]) for k in ("lat", "lon", "t", "aqua")}
    if sensor == "modis":
        keep = d["aqua"] == 1
        d = {k: v[keep] for k, v in d.items()}
    ym = (D0 + (d["t"] // 1440).astype("timedelta64[D]")).astype("datetime64[M]").astype(int) - (2012 - 1970) * 12
    d["yi"], d["cm"] = ym // 12, ym % 12
    return d


def grid(d, size, frame):
    r0, c0, R, C = frame
    r = np.floor((d["lat"] + 90) / size).astype(np.int64) - r0
    c = np.floor((d["lon"] + 180) / size).astype(np.int64) - c0
    key = ((r * C + c) * NY + d["yi"]) * 12 + d["cm"]
    return np.bincount(key, minlength=R * C * NY * 12).reshape(R, C, NY, 12).astype(float)


def frame_of(size, M, V):
    lat = np.concatenate([M["lat"], V["lat"]])
    lon = np.concatenate([M["lon"], V["lon"]])
    r0 = int(math.floor((lat.min() + 90) / size))
    c0 = int(math.floor((lon.min() + 180) / size))
    R = int(math.floor((lat.max() + 90) / size)) - r0 + 1
    C = int(math.floor((lon.max() + 180) / size)) - c0 + 1
    return r0, c0, R, C


def stability(Mg, Vg):
    SM, SV = Mg.sum(2, keepdims=True), Vg.sum(2, keepdims=True)
    Mo, Vo = SM - Mg, SV - Vg
    valid = (Mg >= 1) & (Mo >= 1) & (Vo >= 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        k_year = Vg / Mg
        k_rest = Vo / Mo
        change = np.where(valid, np.abs(k_year / k_rest - 1), np.nan)
        noise = np.where(valid, np.sqrt(1 / Mg + 1 / np.maximum(Vg, 1) + 1 / Mo + 1 / Vo), np.nan)
    years = valid.sum(2)
    ok = years >= MIN_YEARS
    typical = np.full(years.shape, np.nan)
    chance = np.full(years.shape, np.nan)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            typical[ok] = np.nanmedian(change, axis=2)[ok]
            chance[ok] = 0.674 * np.nanmedian(noise, axis=2)[ok]
    fires = SV[:, :, 0, :]
    has = fires > 0
    same = ok & (typical <= LIMIT)
    by_chance = ok & (typical > LIMIT) & (typical <= NOISE_FACTOR * chance)
    real = ok & (typical > LIMIT) & (typical > NOISE_FACTOR * chance)
    few = has & ~ok
    total = fires.sum()
    w = fires[ok]
    order = np.argsort(typical[ok])
    cum = np.cumsum(w[order])
    wmedian = float(typical[ok][order][np.searchsorted(cum, cum[-1] / 2)]) if len(w) else None
    return {
        "square_months": int(has.sum()),
        "share_same": float(fires[same].sum() / total),
        "share_chance": float(fires[by_chance].sum() / total),
        "share_real": float(fires[real].sum() / total),
        "share_few": float(fires[few].sum() / total),
        "count_same": int(same.sum()), "count_chance": int(by_chance.sum()), "count_real": int(real.sum()),
        "count_few": int(few.sum()),
        "typical_change": wmedian,
        "median_fires_per_square_month": float(np.median(fires[has])),
    }, k_rest


def area_error(size, frame, k_rest, Mb, Vb, base_frame, area_k_rest):
    """Each year of each 0.25-degree cell predicted with the factor its square learned on the other years."""
    r0, c0, R, C = frame
    br0, bc0, BR, BC = base_frame
    f = int(round(size / BASE))
    rows = (br0 + np.arange(BR)) // f - r0
    cols = (bc0 + np.arange(BC)) // f - c0
    K = k_rest[rows[:, None], cols[None, :]]  # BR, BC, NY, 12
    K = np.where(np.isfinite(K), K, area_k_rest[None, None, :, :])
    pred = K * Mb
    out = {}
    for q in QUERIES:
        g = int(round(q / BASE))
        qr = (br0 + np.arange(BR)) // g
        qc = (bc0 + np.arange(BC)) // g
        qr -= qr.min()
        qc -= qc.min()
        QC = qc.max() + 1
        key = (qr[:, None] * QC + qc[None, :]).ravel()
        nq = key.max() + 1
        P = np.zeros((nq, NY * 12))
        A = np.zeros((nq, NY * 12))
        np.add.at(P, key, pred.reshape(BR * BC, NY * 12))
        np.add.at(A, key, Vb.reshape(BR * BC, NY * 12))
        sel = A >= 100
        out[str(q)] = {"error": float(np.median(np.abs(P[sel] / A[sel] - 1))), "n": int(sel.sum())}
    return out


def drift(size, frame, Mg, Vg):
    SM, SV = Mg.sum(2, keepdims=True), Vg.sum(2, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        K = np.where(SM > 0, SV / SM, 0)
    expected = (K * Mg).sum(axis=(0, 1, 3))
    actual = Vg.sum(axis=(0, 1, 3))
    ratio = actual / expected
    x = np.arange(NY) - (NY - 1) / 2
    slope = float(np.polyfit(x, np.log(ratio), 1)[0])
    return {"per_year": math.exp(slope) - 1, "ratio_by_year": ratio.tolist()}


def study(country):
    M, V = load(country, "modis"), load(country, "viirs-snpp")
    base_frame = frame_of(BASE, M, V)
    Mb, Vb = grid(M, BASE, base_frame), grid(V, BASE, base_frame)
    tm, tv = Mb.sum(axis=(0, 1)), Vb.sum(axis=(0, 1))  # NY, 12
    area_k_rest = (tv.sum(0, keepdims=True) - tv) / np.maximum(tm.sum(0, keepdims=True) - tm, 1)
    res = {}
    for size in SIZES:
        frame = frame_of(size, M, V)
        Mg, Vg = grid(M, size, frame), grid(V, size, frame)
        st, k_rest = stability(Mg, Vg)
        st["squares"] = int((Vg.sum(axis=(2, 3)) > 0).sum())
        st["area_error"] = area_error(size, frame, k_rest, Mb, Vb, base_frame, area_k_rest)
        st["drift"] = drift(size, frame, Mg, Vg)
        res[str(size)] = st
    return res


if __name__ == "__main__":
    result = {"sizes": SIZES, "queries": QUERIES, "limit": LIMIT, "countries": {}}
    for c in COUNTRIES:
        r = study(c)
        result["countries"][c] = r
        print(c)
        for size in SIZES:
            s = r[str(size)]
            ae = s["area_error"]
            print(f"  {size:5.2f} deg: squares {s['squares']:5d}, square-months {s['square_months']:6d} "
                  f"(median {s['median_fires_per_square_month']:7.0f} VIIRS points); fires in same {s['share_same']:6.1%}, "
                  f"chance {s['share_chance']:6.1%}, real {s['share_real']:6.1%}, few years {s['share_few']:6.1%}; "
                  f"typical change {s['typical_change']:6.1%}; error 0.5deg {ae['0.5']['error']:6.1%}, "
                  f"2deg {ae['2.0']['error']:6.1%}; drift {s['drift']['per_year']:+.1%}/yr", flush=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
