#!/usr/bin/env python3
"""Compare harmonization approaches MODIS (Aqua) -> VIIRS (Suomi NPP) on monthly series of a few countries.

Usage: python3 -I evaluate.py <dir of npz files from extract.py> <out.json> <Country> [<Country> ...]

Each approach predicts, from the MODIS rows of a month, the VIIRS value of that month in the approach's own unit
(points for most, cells of 10+ MW for the same bar, FRP sum, cell-days). It learns on 2012-2016 and is tested on
2017-2022, then the other way round; the test months of both halves are pooled. Only vegetation fires (type = 0)
are in the input. Criteria, per approach and country:
  err     median |pred / actual - 1| over test months whose VIIRS point count is 100 or more
  bias    exp(mean log(pred / actual)) - 1 over the same months: the step a join would show
  stab    standard deviation over the test years of log(year sum of pred / year sum of actual)
  cal     share of months where pred and actual fall in the same calendar class (and within one class);
          a class is the month divided by the mean of that calendar month over 2012-2022 of the actual series,
          cut at 0.5, 0.8, 1.25, 2; only calendar months whose mean VIIRS count is 100 or more
  kept    share of VIIRS points the approach's target keeps
  cell    median |pred / actual - 1| on 2-degree cells, cell-months with 100 or more VIIRS points
"""
import json
import math
import os
import sys
from datetime import date

import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
COUNTRIES = sys.argv[3:]
YEARS = list(range(2012, 2023))
NM = len(YEARS) * 12
HALVES = [(range(2012, 2017), range(2017, 2023)), (range(2017, 2023), range(2012, 2017))]
D0 = np.datetime64("2000-01-01")
FRP_EDGES = [float(x) for x in os.environ.get("FRP_EDGES", "10").split(",")]
SCAN_EDGES = [float(x) for x in os.environ.get("SCAN_EDGES", "1.5").split(",")]
EDGES = [0.5, 0.8, 1.25, 2.0]
MIN_V = 100
BAR = 10.0
LAMBDA = 100.0
NAMES = {
    1: "Один множник", 2: "Множник на місяць", 3: "Місяць + місце (клітинка 2°)", 4: "Місяць + вага за силою вогню",
    5: "Однакова планка (день, від 10 МВт)", 6: "Множник з одночасних прольотів", 7: "Кожен датчик проти своєї норми",
    8: "Машинне навчання (гребенева регресія)", 10: "Регресія log V = місяць + β·log M", 11: "Квантильне зіставлення",
    12: "Сума FRP", 13: "Клітинко-дні (1 км × день)", 14: "Місяць + поправка на розмір пікселя",
    15: "Стягування до множника країни (клітинка 2°)",
}


def load(country, sensor):
    parts = [np.load(f"{SRC}/{country}_{sensor}_{y}.npz") for y in YEARS]
    d = {k: np.concatenate([p[k] for p in parts]) for k in parts[0].files}
    if sensor == "modis":
        keep = d["aqua"] == 1
        d = {k: v[keep] for k, v in d.items()}
    day_no = d["t"] // 1440
    months = (D0 + day_no.astype("timedelta64[D]")).astype("datetime64[M]").astype(int)  # months since 1970-01
    d["m"] = months - (2012 - 1970) * 12
    d["dayno"] = day_no
    d["cell2"] = (np.floor((d["lat"] + 90) / 2).astype(np.int64) * 180 + np.floor((d["lon"] + 180) / 2).astype(np.int64))
    lonk = d["lon"] * np.cos(np.radians(d["lat"]))
    d["cell1"] = np.floor(d["lat"] / 0.01).astype(np.int64) * 100000 + np.floor(lonk / 0.01).astype(np.int64)
    order = np.argsort(d["t"], kind="stable")
    d = {k: v[order] for k, v in d.items()}
    d["pass"] = np.concatenate([[0], np.cumsum(np.diff(d["t"]) > 20)])
    return d


def per_month(m, w=None):
    return np.bincount(m, weights=w, minlength=NM).astype(float)


def classes(x, edges):
    return np.digitize(x, edges)


def cell_days(d):
    """One row index per (day, ~1 km cell) with a fire."""
    _, first = np.unique(d["dayno"] * 10**12 + d["cell1"] + 5 * 10**10, return_index=True)
    return first


def same_bar_viirs(d):
    """Day VIIRS rows glued into ~1 km cells per pass; cells of 10+ MW. Returns cells per month, points kept."""
    day = d["day"] == 1
    key = d["pass"][day] * 10**12 + d["cell1"][day] + 5 * 10**10
    uniq, inv = np.unique(key, return_inverse=True)
    frp = np.bincount(inv, weights=d["frp"][day])
    strong = frp >= BAR
    first = np.zeros(len(uniq), np.int64)
    first[inv[::-1]] = np.arange(len(inv))[::-1]
    months = d["m"][day][first]
    kept_points = strong[inv].sum()
    return np.flatnonzero(day)[first[strong]], kept_points


def coincident_factor(M, V):
    """Per calendar month, VIIRS points / MODIS points over near-simultaneous passes (within 10 minutes),
    both restricted to the inner half of their pixel sizes (MODIS scan <= 1.3, VIIRS scan <= 0.45)."""
    def passes(d):
        p = d["pass"]
        n = p.max() + 1
        mid = np.bincount(p, weights=d["t"]) / np.maximum(np.bincount(p), 1)
        return mid, n
    mm, _ = passes(M)
    vm, _ = passes(V)
    j = np.searchsorted(vm, mm)
    pair = np.full(len(mm), -1)
    for k in range(len(mm)):
        best, bd = -1, 11
        for c in (j[k] - 1, j[k]):
            if 0 <= c < len(vm) and abs(vm[c] - mm[k]) < bd:
                best, bd = c, abs(vm[c] - mm[k])
        pair[k] = best
    good_m = pair[M["pass"]] >= 0
    v_paired = np.zeros(len(vm), bool)
    v_paired[pair[pair >= 0]] = True
    good_v = v_paired[V["pass"]]
    mi = good_m & (M["scan"] <= 1.3)
    vi = good_v & (V["scan"] <= 0.45)
    return per_month(M["m"][mi]), per_month(V["m"][vi])


def month_masks(half):
    tr = np.zeros(NM, bool)
    te = np.zeros(NM, bool)
    for y in half[0]:
        tr[(y - 2012) * 12:(y - 2012) * 12 + 12] = True
    for y in half[1]:
        te[(y - 2012) * 12:(y - 2012) * 12 + 12] = True
    return tr, te


CAL = np.tile(np.arange(12), len(YEARS))


def month_factor(num, den, tr):
    k = np.zeros(12)
    for c in range(12):
        s = tr & (CAL == c)
        k[c] = num[s].sum() / max(den[s].sum(), 1e-9)
    return k[CAL]


def weighted_month_factor(V, X, tr, iters=20):
    """pred = k_month * sum_c w_c X_c, with w fitted on relative error; returns per-month factor on each class."""
    w = np.ones(X.shape[1])
    for _ in range(iters):
        k = month_factor(V, X @ w, tr)
        A = (k[:, None] * X)[tr]
        y = V[tr]
        ok = y > 0
        A, y = A[ok] / y[ok, None], np.ones(ok.sum())
        w = np.clip(np.linalg.lstsq(A, y, rcond=None)[0], 0.05, None)
        w = w * X[tr].sum() / max((X[tr] @ w).sum(), 1e-9)
    k = month_factor(V, X @ w, tr)
    return k, w


def evaluate(country):
    M = load(country, "modis")
    V = load(country, "viirs-snpp")
    vc = per_month(V["m"])
    mc = per_month(M["m"])
    fcls = np.digitize(M["frp"], FRP_EDGES)
    scls = np.digitize(M["scan"], SCAN_EDGES)
    MF = np.stack([per_month(M["m"][fcls == c]) for c in range(len(FRP_EDGES) + 1)], 1)
    MS = np.stack([per_month(M["m"][scls == c]) for c in range(len(SCAN_EDGES) + 1)], 1)
    vfrp, mfrp = per_month(V["m"], V["frp"]), per_month(M["m"], M["frp"])
    vcd_rows, mcd_rows = cell_days(V), cell_days(M)
    vcd, mcd = per_month(V["m"][vcd_rows]), per_month(M["m"][mcd_rows])
    vbar_rows, kept_points = same_bar_viirs(V)
    vbar = per_month(V["m"][vbar_rows])
    mbar_rows = np.flatnonzero((M["day"] == 1) & (M["frp"] >= BAR))
    mbar = per_month(M["m"][mbar_rows])
    mco, vco = coincident_factor(M, V)

    cells = np.union1d(np.unique(V["cell2"]), np.unique(M["cell2"]))
    ci_v, ci_m = np.searchsorted(cells, V["cell2"]), np.searchsorted(cells, M["cell2"])
    NC = len(cells)
    Vc = np.bincount(ci_v * NM + V["m"], minlength=NC * NM).reshape(NC, NM).astype(float)
    Mc = np.bincount(ci_m * NM + M["m"], minlength=NC * NM).reshape(NC, NM).astype(float)
    McF = np.stack([np.bincount(ci_m[fcls == c] * NM + M["m"][fcls == c], minlength=NC * NM).reshape(NC, NM)
                    for c in range(len(FRP_EDGES) + 1)], 2).astype(float)
    def grid(ci, rows, d, w=None):
        return np.bincount(ci[rows] * NM + d["m"][rows], weights=None if w is None else w[rows],
                           minlength=NC * NM).reshape(NC, NM).astype(float)
    allv, allm = np.arange(len(V["m"])), np.arange(len(M["m"]))
    cell_target = {5: grid(ci_v, vbar_rows, V), 12: grid(ci_v, allv, V, V["frp"]), 13: grid(ci_v, vcd_rows, V)}
    cell_modis = {5: grid(ci_m, mbar_rows, M), 12: grid(ci_m, allm, M, M["frp"]), 13: grid(ci_m, mcd_rows, M)}
    McS = np.stack([np.bincount(ci_m[scls == c] * NM + M["m"][scls == c], minlength=NC * NM).reshape(NC, NM)
                    for c in range(len(SCAN_EDGES) + 1)], 2).astype(float)

    # features for approach 8, one row per month
    night = per_month(M["m"][M["day"] == 0]) / np.maximum(mc, 1)
    scan_mean = per_month(M["m"], M["scan"]) / np.maximum(mc, 1)
    shares = MF / np.maximum(mc, 1)[:, None]
    yr = np.repeat(np.arange(len(YEARS)), 12) - 5
    feats = np.column_stack([np.log1p(mc), shares[:, 1:], night, scan_mean, np.sin(2 * np.pi * CAL / 12),
                             np.cos(2 * np.pi * CAL / 12), yr])

    targets = {a: vc for a in (1, 2, 3, 4, 6, 7, 8, 10, 11, 14, 15)}
    targets.update({5: vbar, 12: vfrp, 13: vcd})
    preds = {a: np.full(NM, np.nan) for a in NAMES}
    cell_preds = {a: np.full((NC, NM), np.nan) for a in (1, 2, 3, 4, 5, 6, 8, 10, 11, 12, 13, 14, 15)}
    info = {}

    for half in HALVES:
        tr, te = month_masks(half)
        # 1
        k1 = vc[tr].sum() / mc[tr].sum()
        preds[1][te] = k1 * mc[te]
        cell_preds[1][:, te] = k1 * Mc[:, te]
        # 2
        k2 = month_factor(vc, mc, tr)
        preds[2][te] = (k2 * mc)[te]
        cell_preds[2][:, te] = (k2 * Mc)[:, te]
        # 3 and 15
        k3 = np.zeros((NC, NM))
        k15 = np.zeros((NC, NM))
        for c in range(12):
            s = tr & (CAL == c)
            vt, mt = Vc[:, s].sum(1), Mc[:, s].sum(1)
            kc = k2[c]
            k3[:, CAL == c] = np.where(mt >= 30, vt / np.maximum(mt, 1e-9), kc)[:, None]
            k15[:, CAL == c] = ((vt + LAMBDA * kc) / (mt + LAMBDA))[:, None]
        cell_preds[3][:, te] = (k3 * Mc)[:, te]
        cell_preds[15][:, te] = (k15 * Mc)[:, te]
        preds[3][te] = cell_preds[3][:, te].sum(0)
        preds[15][te] = cell_preds[15][:, te].sum(0)
        # 4 and 14
        k4, w4 = weighted_month_factor(vc, MF, tr)
        preds[4][te] = (k4 * (MF @ w4))[te]
        cell_preds[4][:, te] = (k4[None, :] * (McF @ w4))[:, te]
        k14, w14 = weighted_month_factor(vc, MS, tr)
        preds[14][te] = (k14 * (MS @ w14))[te]
        cell_preds[14][:, te] = (k14[None, :] * (McS @ w14))[:, te]
        info.setdefault("w_frp", []).append([round(x, 2) for x in w4])
        info.setdefault("w_scan", []).append([round(x, 2) for x in w14])
        # 5, 12, 13
        for a, (vv, mm) in {5: (vbar, mbar), 12: (vfrp, mfrp), 13: (vcd, mcd)}.items():
            k = month_factor(vv, mm, tr)
            preds[a][te] = (k * mm)[te]
            cell_preds[a][:, te] = (k * cell_modis[a])[:, te]
        # 6
        k6 = month_factor(vco, mco, tr)
        preds[6][te] = (k6 * mc)[te]
        cell_preds[6][:, te] = (k6 * Mc)[:, te]
        # 8: ridge on log(V/M)
        ok = tr & (mc > 0) & (vc > 0)
        mu, sd = feats[ok].mean(0), feats[ok].std(0) + 1e-9
        Xtr = np.column_stack([np.ones(ok.sum()), (feats[ok] - mu) / sd])
        ytr = np.log(vc[ok] / mc[ok])
        lam = 1.0 * np.eye(Xtr.shape[1])
        lam[0, 0] = 0
        beta = np.linalg.solve(Xtr.T @ Xtr + lam, Xtr.T @ ytr)
        smear = np.mean(np.exp(ytr - Xtr @ beta))
        Xall = np.column_stack([np.ones(NM), (feats - mu) / sd])
        f8 = np.exp(Xall @ beta) * smear
        preds[8][te] = (f8 * mc)[te]
        cell_preds[8][:, te] = (f8 * Mc)[:, te]
        # 10: log V = c_month + beta log M
        ok = tr & (mc > 0) & (vc > 0)
        D = np.zeros((ok.sum(), 13))
        D[np.arange(ok.sum()), CAL[ok]] = 1
        D[:, 12] = np.log(mc[ok])
        coef = np.linalg.lstsq(D, np.log(vc[ok]), rcond=None)[0]
        smear10 = np.mean(np.exp(np.log(vc[ok]) - D @ coef))
        info.setdefault("beta10", []).append(round(float(coef[12]), 3))
        p10 = np.exp(coef[CAL] + coef[12] * np.log(np.maximum(mc, 1))) * smear10
        preds[10][te] = p10[te]
        f10 = np.where(mc > 0, p10 / np.maximum(mc, 1), 0)
        cell_preds[10][:, te] = (f10 * Mc)[:, te]
        # 11: quantile mapping of monthly counts, all calendar months pooled
        sm, sv = np.sort(mc[tr]), np.sort(vc[tr])
        q = np.linspace(0, 1, len(sm))
        def qmap(x):
            out = np.interp(np.interp(x, sm, q), q, sv)
            hi, lo = x > sm[-1], x < sm[0]
            out[hi] = x[hi] * sv[-1] / max(sm[-1], 1)
            out[lo] = x[lo] * sv[0] / max(sm[0], 1)
            return out
        p11 = qmap(mc)
        preds[11][te] = p11[te]
        f11 = np.where(mc > 0, p11 / np.maximum(mc, 1), 0)
        cell_preds[11][:, te] = (f11 * Mc)[:, te]

    # 7: classes from each sensor's own norm
    results = {}
    big = vc >= MIN_V
    norm_v = np.array([vc[CAL == c].mean() for c in range(12)])
    cal_ok = norm_v[CAL] >= MIN_V
    for a in NAMES:
        y = targets.get(a, vc)
        norm = np.array([y[CAL == c].mean() for c in range(12)])[CAL]
        cls_true = classes(y / np.maximum(norm, 1e-9), EDGES)
        if a == 7:
            norm_m = np.array([mc[CAL == c].mean() for c in range(12)])[CAL]
            cls_pred = classes(mc / np.maximum(norm_m, 1e-9), EDGES)
            r = {"err": None, "bias": None, "stab": None}
        else:
            p = preds[a]
            sel = big & np.isfinite(p) & (y > 0) & (p > 0)
            lr = np.log(p[sel] / y[sel])
            ys = []
            for yi in range(len(YEARS)):
                s = slice(yi * 12, yi * 12 + 12)
                ys.append(math.log(np.nansum(p[s]) / max(y[s].sum(), 1e-9)))
            r = {"err": float(np.median(np.abs(p[sel] / y[sel] - 1))), "bias": float(np.exp(lr.mean()) - 1),
                 "stab": float(np.std(ys))}
            cls_pred = classes(p / np.maximum(norm, 1e-9), EDGES)
        r["cal"] = float(np.mean(cls_pred[cal_ok] == cls_true[cal_ok]))
        r["cal1"] = float(np.mean(np.abs(cls_pred[cal_ok] - cls_true[cal_ok]) <= 1))
        r["kept"] = float(kept_points / len(V["m"])) if a == 5 else 1.0
        if a in cell_preds:
            cp = cell_preds[a]
            ct = cell_target.get(a, Vc)
            sel = (Vc >= MIN_V) & np.isfinite(cp) & (cp > 0) & (ct > 0)
            r["cell"] = float(np.median(np.abs(cp[sel] / ct[sel] - 1)))
            r["cell_n"] = int(sel.sum())
        else:
            r["cell"] = None
        results[a] = r

    norm_m = np.array([mc[CAL == c].mean() for c in range(12)])[CAL]
    series = {"vc": vc.tolist(), "mc": mc.tolist(),
              "target": {a: targets.get(a, vc).tolist() for a in NAMES if a != 7},
              "pred": {a: preds[a].tolist() for a in NAMES if a != 7},
              "rel7": {"modis": (mc / np.maximum(norm_m, 1e-9)).tolist(),
                       "viirs": (vc / np.maximum(norm_v[CAL], 1e-9)).tolist()}}
    info.update({"modis_points": int(len(M["m"])), "viirs_points": int(len(V["m"])), "cells2": NC,
                 "same_bar_kept": round(kept_points / len(V["m"]), 3),
                 "coincident_modis_points": int(mco.sum()), "coincident_viirs_points": int(vco.sum())})
    return {"results": results, "info": info, "series": series}


if __name__ == "__main__":
    out = {"names": NAMES, "countries": {}}
    for c in COUNTRIES:
        out["countries"][c] = evaluate(c)
        print(c, json.dumps(out["countries"][c]["info"], ensure_ascii=False), flush=True)
        for a, r in out["countries"][c]["results"].items():
            f = lambda x: "  —  " if x is None else f"{x * 100:5.1f}"
            print(f"  {a:2d} {NAMES[a][:38]:38s} err {f(r['err'])} bias {f(r['bias'])} stab {f(r['stab'])} "
                  f"cal {f(r['cal'])} cal±1 {f(r['cal1'])} kept {f(r['kept'])} cell {f(r['cell'])}", flush=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
