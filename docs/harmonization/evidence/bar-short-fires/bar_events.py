#!/usr/bin/env python3
"""What does the same power bar (approach 5) lose: VIIRS points by night, weak by day, kept; and fire events that the
bar never sees.

Usage: python3 -I bar_events.py <dir of npz files from extract.py> <out.json> <gap days> <Country> [<Country> ...]

A point is kept by the bar when it is a daytime point and the ~1 km cell it falls in sums 10 MW or more over the
points of that pass (approach 5 of evaluate.py). A fire event is a set of VIIRS points linked step by step: two
points are linked when their ~1 km cells touch (the same cell or one of its eight neighbours) and their local solar
days differ by no more than <gap days>. An event is seen by the bar when at least one of its points is kept.
"""
import json
import sys

import numpy as np

SRC, OUT, GAP = sys.argv[1], sys.argv[2], int(sys.argv[3])
COUNTRIES = sys.argv[4:]
YEARS = range(2012, 2023)
BAR = 10.0
DUR_EDGES = [1, 2, 4, 8]  # durations: 1 day, 2-3, 4-7, 8+


def load(country):
    parts = [np.load(f"{SRC}/{country}_viirs-snpp_{y}.npz") for y in YEARS]
    d = {k: np.concatenate([p[k] for p in parts]) for k in ("lat", "lon", "frp", "t", "day")}
    order = np.argsort(d["t"], kind="stable")
    return {k: v[order] for k, v in d.items()}


def components(n, ei, ej):
    """Connected components of n nodes and the edges ei-ej: each node gets the smallest node id of its component."""
    parent = np.arange(n)
    while True:
        while True:
            jumped = parent[parent]
            if np.array_equal(jumped, parent):
                break
            parent = jumped
        ri, rj = parent[ei], parent[ej]
        open_ = ri != rj
        if not open_.any():
            return parent
        ei, ej, ri, rj = ei[open_], ej[open_], ri[open_], rj[open_]
        np.minimum.at(parent, np.maximum(ri, rj), np.minimum(ri, rj))


def study(country):
    d = load(country)
    n = len(d["t"])
    iy = np.floor(d["lat"] / 0.01).astype(np.int64)
    ix = np.floor(d["lon"] * np.cos(np.radians(d["lat"])) / 0.01).astype(np.int64)
    # the bar: daytime points of pass-cells that sum 10 MW or more
    pass_id = np.concatenate([[0], np.cumsum(np.diff(d["t"]) > 20)])
    day = d["day"] == 1
    cellkey = (iy + 20000) * 100000 + (ix + 50000)
    pk = pass_id * 10**10 + cellkey
    kept = np.zeros(n, bool)
    u, inv = np.unique(pk[day], return_inverse=True)
    strong = np.bincount(inv, weights=d["frp"][day]) >= BAR
    kept[np.flatnonzero(day)] = strong[inv]
    # fire events: cell-days linked across touching cells and close local days
    dl = np.floor((d["t"] + d["lon"] * 4.0) / 1440.0).astype(np.int64)
    key = cellkey * 100000 + dl
    ukeys, pinv = np.unique(key, return_inverse=True)
    m = len(ukeys)
    offsets = [(dy, dx, -dd) for dd in range(1, GAP + 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    offsets += [(-1, -1, 0), (-1, 0, 0), (-1, 1, 0), (0, -1, 0)]
    ei, ej = [], []
    for dy, dx, dd in offsets:
        target = ukeys + dy * 10**10 + dx * 10**5 + dd
        pos = np.searchsorted(ukeys, target)
        pos[pos == m] = m - 1
        hit = ukeys[pos] == target
        ei.append(np.flatnonzero(hit))
        ej.append(pos[hit])
    comp = components(m, np.concatenate(ei), np.concatenate(ej))
    _, ev = np.unique(comp[pinv], return_inverse=True)  # event id of each point
    ne = ev.max() + 1
    pts = np.bincount(ev, minlength=ne)
    seen = np.bincount(ev, weights=kept, minlength=ne) > 0
    day_pts = np.bincount(ev, weights=day, minlength=ne)
    dmin = np.full(ne, np.iinfo(np.int64).max)
    dmax = np.full(ne, np.iinfo(np.int64).min)
    np.minimum.at(dmin, ev, dl)
    np.maximum.at(dmax, ev, dl)
    dur = dmax - dmin + 1
    dcls = np.digitize(dur, DUR_EDGES[1:])  # 0: 1 day, 1: 2-3, 2: 4-7, 3: 8+

    lost = ~seen
    out = {
        "points": n,
        "night": float(np.mean(~day)),
        "day_weak": float(np.mean(day & ~kept)),
        "kept": float(np.mean(kept)),
        "events": int(ne),
        "seen_events": float(seen.mean()),
        "points_in_seen_events": float(pts[seen].sum() / n),
        "lost_events": int(lost.sum()),
        "lost_points": float(pts[lost].sum() / n),
        "lost_night_only": float(np.mean(day_pts[lost] == 0)) if lost.any() else 0.0,
        "lost_day_weak_only": float(np.mean(day_pts[lost] == pts[lost])) if lost.any() else 0.0,
        "lost_single_point": float(np.mean(pts[lost] == 1)) if lost.any() else 0.0,
        "lost_median_points": float(np.median(pts[lost])) if lost.any() else 0.0,
        "by_duration": [],
    }
    labels = ["1 день", "2–3 дні", "4–7 днів", "8+ днів"]
    for c, label in enumerate(labels):
        s = dcls == c
        out["by_duration"].append({
            "label": label, "events": int(s.sum()), "share_events": float(s.mean()),
            "share_points": float(pts[s].sum() / n), "seen": float(seen[s].mean()) if s.any() else None,
        })
    return out


if __name__ == "__main__":
    result = {"gap_days": GAP, "countries": {}}
    for c in COUNTRIES:
        r = study(c)
        result["countries"][c] = r
        print(f"{c} (gap {GAP} d): points {r['points']}; night {r['night']:.1%}, day weak {r['day_weak']:.1%}, "
              f"kept {r['kept']:.1%}", flush=True)
        print(f"  events {r['events']}; seen by the bar {r['seen_events']:.1%}; their points {r['points_in_seen_events']:.1%}"
              f" of all; lost {r['lost_events']} events with {r['lost_points']:.1%} of points "
              f"(night only {r['lost_night_only']:.0%}, day weak only {r['lost_day_weak_only']:.0%}, "
              f"single point {r['lost_single_point']:.0%}, median {r['lost_median_points']:.0f} points)", flush=True)
        for b in r["by_duration"]:
            print(f"    {b['label']:9s} events {b['share_events']:6.1%} points {b['share_points']:6.1%} "
                  f"seen {b['seen'] if b['seen'] is None else format(b['seen'], '.1%')}", flush=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
