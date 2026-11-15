"""NOAA-20 against Suomi NPP, roadmap stage 6: is a NOAA-20 point worth one Suomi NPP point (weight 1), or does
NOAA-20 need a factor of its own per 2-degree square and calendar month, as Aqua and Terra have?

Reads the FIRMS yearly world archives viirs-jpss1 (NOAA-20) and viirs-snpp (Suomi NPP) for 2018-2025 with the
readers of the harmonize package (folder parser/ of the app repository), keeps vegetation fires (type 0, no confidence filter) on the days both
satellites gave at least one point of any type, and guesses every year's Suomi NPP points from that year's
NOAA-20 points four ways, each factor learned on the other years only:

    w1      weight 1, NOAA-20 points as they are (version v1-2026-11-14)
    const   one world factor for all months
    month   one world factor per calendar month
    own     the approach-15 chain: 2-degree square and calendar month, cross, 8-degree square, world, lambda 300

The errors are measured the way harmonize/validate.py measures Aqua: median |guess / real - 1| over area-months
with 100+ real Suomi NPP points, on areas of 0.5, 2 and 8 degrees and on the 2-degree squares of Ukraine,
Brazil and Australia.

Run from a folder outside the data (the archives are read as data, never imported):
    python3 -I noaa20_probe.py <folder with harmonize/ and data/raw/archive/> results.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

YEARS = tuple(range(2018, 2026))
COUNTRIES = ("Ukraine", "Brazil", "Australia")
EPOCH64 = np.datetime64("2000-01-01")
SQ = (90, 180)
HALF = (360, 720)
MIN_ACTUAL = 100
SPARSE = 100
JOBS = 24

_COMMON: np.ndarray | None = None


def _init(common: np.ndarray) -> None:
    global _COMMON
    _COMMON = common


def _count(member):
    """Flat indices and counts of one file's type-0 points on the shared days of YEARS."""
    from harmonize.sources import SAT_IDS, country_of, read_member

    rows = read_member(member)
    months = (EPOCH64 + rows.day.astype("timedelta64[D]")).astype("datetime64[M]").astype(np.int64)
    year, month = months // 12 + 1970, months % 12
    inside = rows.day < len(_COMMON)
    shared = np.zeros(len(rows.day), dtype=bool)
    shared[inside] = _COMMON[rows.day[inside]]
    base = (rows.type == 0) & shared & (year >= YEARS[0]) & (year <= YEARS[-1])
    y = year - YEARS[0]
    r2, c2 = rows.cell2.astype(np.int64) // SQ[1], rows.cell2.astype(np.int64) % SQ[1]
    iy, ix = rows.cell.astype(np.int64) // 1440, rows.cell.astype(np.int64) % 1440
    country = country_of(member)
    out = []
    for name, sat in (("n20", SAT_IDS["noaa20"]), ("snpp", SAT_IDS["snpp"])):
        sel = base & (rows.sat == sat)
        if not sel.any():
            continue
        targets = [(("sq", name), SQ, r2, c2), (("half", name), HALF, iy // 2, ix // 2)]
        if country in COUNTRIES:
            targets.append((("country", country, name), SQ, r2, c2))
        for target, grid, r, c in targets:
            flat = np.ravel_multi_index((r[sel], c[sel], y[sel], month[sel]), grid + (len(YEARS), 12))
            keys, n = np.unique(flat, return_counts=True)
            out.append((target, keys, n))
    return out


def _flat(values: np.ndarray) -> np.ndarray:
    return values.reshape((-1,) + values.shape[2:])


def _blocks(values: np.ndarray, size: int) -> np.ndarray:
    rows = -(-values.shape[0] // size) * size
    padded = np.zeros((rows,) + values.shape[1:], dtype=values.dtype)
    padded[:values.shape[0]] = values
    return padded.reshape((rows // size, size, values.shape[1] // size, size) + values.shape[2:]).sum(axis=(1, 3))


def _median_error(pred: np.ndarray, actual: np.ndarray) -> float | None:
    sel = actual >= MIN_ACTUAL
    return float(np.median(np.abs(pred[sel] / actual[sel] - 1))) if sel.any() else None


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2])
    sys.path.insert(0, str(root))
    from harmonize.counts import common_days
    from harmonize.days import satellite_days
    from harmonize.factors import LAMBDA, chain_without_each_year
    from harmonize.sources import archive_members
    from harmonize.validate import AreaSet, error_rows, metrics

    started = time.time()
    archive = root / "data" / "raw" / "archive"
    members = archive_members(archive, "viirs-jpss1", YEARS) + archive_members(archive, "viirs-snpp", YEARS)
    days = satellite_days(members, JOBS)
    common = common_days(days, "noaa20", "snpp")
    print(f"days read in {time.time() - started:.0f} s", flush=True)

    day_stats = {}
    for year in YEARS:
        lo = (np.datetime64(f"{year}-01-01") - EPOCH64).astype(int)
        hi = (np.datetime64(f"{year + 1}-01-01") - EPOCH64).astype(int)
        n20 = np.zeros(hi - lo, dtype=bool)
        snpp = np.zeros(hi - lo, dtype=bool)
        part = days["noaa20"][lo:hi]
        n20[:len(part)] = part
        part = days["snpp"][lo:hi]
        snpp[:len(part)] = part
        day_stats[year] = {"common": int((n20 & snpp).sum()), "noaa20_only": int((n20 & ~snpp).sum()),
                           "snpp_only": int((snpp & ~n20).sum()), "neither": int((~n20 & ~snpp).sum())}

    shape = {"sq": SQ, "half": HALF}
    arrays: dict[tuple, np.ndarray] = {}
    for key in ("sq", "half"):
        for name in ("n20", "snpp"):
            arrays[(key, name)] = np.zeros(shape[key] + (len(YEARS), 12))
    for country in COUNTRIES:
        for name in ("n20", "snpp"):
            arrays[("country", country, name)] = np.zeros(SQ + (len(YEARS), 12))
    from multiprocessing import Pool
    with Pool(JOBS, initializer=_init, initargs=(common,)) as pool:
        for parts in pool.imap_unordered(_count, members, chunksize=2):
            for target, keys, n in parts:
                np.add.at(arrays[target].reshape(-1), keys, n)
    print(f"counts read in {time.time() - started:.0f} s", flush=True)

    N, S = arrays[("sq", "n20")], arrays[("sq", "snpp")]
    Nh, Sh = arrays[("half", "n20")], arrays[("half", "snpp")]
    rest_n = N.sum(axis=2, keepdims=True) - N
    rest_s = S.sum(axis=2, keepdims=True) - S
    k_const = rest_s.sum(axis=(0, 1, 3)) / rest_n.sum(axis=(0, 1, 3))            # (years,)
    k_month = rest_s.sum(axis=(0, 1)) / rest_n.sum(axis=(0, 1))                   # (years, 12)
    k_own = chain_without_each_year(N, S, LAMBDA)                                 # (90, 180, years, 12)
    factor2 = {"w1": np.ones_like(N), "const": np.broadcast_to(k_const[None, None, :, None], N.shape),
               "month": np.broadcast_to(k_month[None, None], N.shape), "own": k_own}
    sparse = _flat(rest_n < SPARSE)

    validation, error_table = {}, {}
    for way, k in factor2.items():
        pred2 = k * N
        k_half = np.repeat(np.repeat(np.asarray(k), 4, axis=0), 4, axis=1)
        sets = {"0.5": AreaSet(_flat(k_half * Nh), _flat(Sh), _flat(Nh), None),
                "2": AreaSet(_flat(pred2), _flat(S), _flat(N), sparse),
                "8": AreaSet(_flat(_blocks(pred2, 4)), _flat(_blocks(S, 4)), _flat(_blocks(N, 4)), None)}
        validation[way] = {area: metrics(a) for area, a in sets.items()}
        error_table[way] = [[n_min, rel, samples] for _, _, n_min, rel, samples in error_rows(sets, "noaa20")]
        for country in COUNTRIES:
            nc, sc = arrays[("country", country, "n20")], arrays[("country", country, "snpp")]
            pc = k * nc
            validation[way][country + " 2"] = {"error": _median_error(pc, sc)}
            validation[way][country + " total"] = {"error": _median_error(pc.sum(axis=(0, 1)), sc.sum(axis=(0, 1)))}

    ratio_year = {y: float(N[:, :, i].sum() / S[:, :, i].sum()) for i, y in enumerate(YEARS)}
    ratio_month = [float(N[:, :, :, m].sum() / S[:, :, :, m].sum()) for m in range(12)]
    ratio_country = {c: {y: float(arrays[("country", c, "n20")][:, :, i].sum()
                                  / arrays[("country", c, "snpp")][:, :, i].sum()) for i, y in enumerate(YEARS)}
                     for c in COUNTRIES}
    lat_rows = []
    for lo in range(-60, 80, 20):
        band = slice((lo + 90) // 2, (lo + 110) // 2)
        lat_rows.append([f"{lo}…{lo + 20}", float(N[band].sum()), float(S[band].sum()),
                         float(N[band].sum() / S[band].sum()) if S[band].sum() else None])
    k_all = k_own.mean(axis=2)
    weights = N.sum(axis=2)
    spread = {q: float(np.quantile(k_all[weights > 0], q, weights=weights[weights > 0], method="inverted_cdf"))
              for q in (0.1, 0.25, 0.5, 0.75, 0.9)}

    result = {
        "years": list(YEARS), "lambda": LAMBDA, "days": day_stats,
        "points": {"noaa20": float(N.sum()), "snpp": float(S.sum())},
        "ratio_year": ratio_year, "ratio_month": ratio_month, "ratio_country": ratio_country,
        "ratio_latitude": lat_rows, "own_factor_spread": spread,
        "validation": validation, "error_table": error_table,
        "seconds": round(time.time() - started),
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for way, areas in validation.items():
        print(way, {a: (round(m["error"], 4) if m.get("error") is not None else None) for a, m in areas.items()})
    print("ratio NOAA-20 / Suomi NPP by year:", {y: round(r, 4) for y, r in ratio_year.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
