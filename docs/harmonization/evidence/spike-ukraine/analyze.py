#!/usr/bin/env python3
"""Spike: how MODIS and VIIRS hotspot counts differ over Ukraine,
and how well a few harmonization ideas work on that data.

Usage: python3 -I analyze.py <folder with *_Ukraine.csv> [<first year> <first test year> <last year>]

The years of the analysis are first..last; the idea is learned on first..(first test year - 1)
and tested on the rest, then the other way round. Default: 2012 2017 2021.
"""

import bisect
import csv
import glob
import math
import os
import statistics as st
import sys
from array import array
from collections import Counter, defaultdict
from datetime import date

DATA = sys.argv[1]
D0 = date(2012, 1, 1).toordinal()
LAT0, LON0, DLAT, DLON, NLON = 43.0, 21.0, 0.01, 0.015, 2000  # ~1.1 km cells
# optional: analyze.py <dir> <first year> <split year> <last year>
_Y0, _YS, _Y1 = (int(v) for v in sys.argv[2:5]) if len(sys.argv) >= 5 else (2012, 2017, 2021)
TRAIN = range(_Y0, _YS)
TEST = range(_YS, _Y1 + 1)
YEARS = range(_Y0, _Y1 + 1)
BINS = [2, 5, 10, 20, 50, 100]
LABELS = ["<2", "2-5", "5-10", "10-20", "20-50", "50-100", ">100"]


class Plat:
    """Columns of one platform's hotspots."""

    def __init__(self) -> None:
        self.day = array("H")    # days since 2012-01-01 (UTC)
        self.tmin = array("H")   # minutes since midnight (UTC)
        self.dn = array("B")     # 0 day, 1 night
        self.typ = array("b")    # FIRMS type, -1 when the column is missing
        self.low = array("B")    # 1 = low confidence
        self.frp = array("f")
        self.scan = array("f")
        self.cell = array("I")   # ~1.1 km cell id
        self.lat = array("f")
        self.lon = array("f")
        self.year = array("H")
        self.month = array("B")

    def __len__(self) -> int:
        return len(self.day)


def cell_of(lat: float, lon: float) -> int:
    return int((lat - LAT0) / DLAT) * NLON + int((lon - LON0) / DLON)


def neighbours(cell: int, r: int = 1):
    la, lo = divmod(cell, NLON)
    for i in range(-r, r + 1):
        for j in range(-r, r + 1):
            yield (la + i) * NLON + lo + j


def load() -> dict[str, Plat]:
    plats: dict[str, Plat] = defaultdict(Plat)
    dcache: dict[str, tuple[int, int, int]] = {}
    for path in sorted(glob.glob(os.path.join(DATA, "*_Ukraine.csv"))):
        fam = os.path.basename(path).split("_")[0]
        with open(path, newline="") as fh:
            rd = csv.reader(fh)
            ix = {n: i for i, n in enumerate(next(rd))}
            i_lat, i_lon, i_scan = ix["latitude"], ix["longitude"], ix["scan"]
            i_date, i_time, i_sat = ix["acq_date"], ix["acq_time"], ix["satellite"]
            i_conf, i_frp, i_dn = ix["confidence"], ix["frp"], ix["daynight"]
            i_typ = ix.get("type", -1)
            n = 0
            for row in rd:
                if not row:
                    continue
                if fam == "modis":
                    name = row[i_sat]
                    low = 1 if int(row[i_conf]) < 30 else 0
                else:
                    name = "SNPP" if fam == "viirs-snpp" else "N20"
                    low = 1 if row[i_conf][:1].lower() == "l" else 0
                p = plats[name]
                ds = row[i_date]
                d = dcache.get(ds)
                if d is None:
                    y, m, dd = int(ds[:4]), int(ds[5:7]), int(ds[8:10])
                    d = dcache[ds] = (date(y, m, dd).toordinal() - D0, y, m)
                t = int(row[i_time])
                lat, lon = float(row[i_lat]), float(row[i_lon])
                p.day.append(d[0]); p.year.append(d[1]); p.month.append(d[2])
                p.tmin.append((t // 100) * 60 + t % 100)
                p.dn.append(0 if row[i_dn] == "D" else 1)
                p.typ.append(int(row[i_typ]) if i_typ >= 0 and row[i_typ] != "" else -1)
                p.low.append(low)
                p.frp.append(float(row[i_frp] or 0))
                p.scan.append(float(row[i_scan]))
                p.cell.append(cell_of(lat, lon))
                p.lat.append(lat); p.lon.append(lon)
                n += 1
        print(f"  {os.path.basename(path):34s} {n:8d} rows  cols={len(ix)} type={'yes' if i_typ >= 0 else 'NO'}")
    return plats


def fmt(x: float, nd: int = 2) -> str:
    return "  n/a" if x is None or math.isnan(x) else f"{x:.{nd}f}"


def ratio(a: float, b: float) -> float:
    return a / b if b else float("nan")


def passes(p: Plat):
    """Split a platform's rows into overpasses: (pass mid times in absolute minutes, {pass: row indexes})."""
    at = [p.day[i] * 1440 + p.tmin[i] for i in range(len(p))]
    starts: list[int] = []
    pid: dict[int, int] = {}
    last = -10**9
    for t in sorted(set(at)):
        if t - last > 20:
            starts.append(t)
        pid[t] = len(starts) - 1
        last = t
    rows: dict[int, list[int]] = defaultdict(list)
    for i, t in enumerate(at):
        rows[pid[t]].append(i)
    mid = [st.median(at[i] for i in rows[k]) for k in range(len(starts))]
    return mid, rows


def pair_passes(mid_a: list, mid_b: list) -> list[tuple[int, int, float]]:
    """For each pass of a, the nearest pass of b: (index a, index b, time of b minus time of a)."""
    out = []
    for ia, t in enumerate(mid_a):
        j = bisect.bisect_left(mid_b, t)
        best = None
        for jj in (j - 1, j):
            if 0 <= jj < len(mid_b) and (best is None or abs(mid_b[jj] - t) < abs(mid_b[best] - t)):
                best = jj
        if best is not None:
            out.append((ia, best, mid_b[best] - t))
    return out


def main() -> None:
    print("== load")
    P = load()
    order = [n for n in ("Terra", "Aqua", "SNPP", "N20") if n in P]
    for n in order:
        p = P[n]
        print(f"  {n:5s} rows={len(p):8d}  {date.fromordinal(D0 + min(p.day))}..{date.fromordinal(D0 + max(p.day))}")

    # ---------------------------------------------------------------- A, B
    print("\n== A. raw hotspots per year and platform (all types)")
    cy = Counter()
    for n in order:
        for y in P[n].year:
            cy[n, y] += 1
    print("  year " + "".join(f"{n:>9s}" for n in order) + "   all VIIRS/all MODIS  SNPP/Aqua")
    for y in YEARS:
        mod = cy["Terra", y] + cy["Aqua", y]
        vi = cy["SNPP", y] + cy["N20", y]
        print(f"  {y} " + "".join(f"{cy[n, y]:9d}" for n in order)
              + f"   {fmt(ratio(vi, mod)):>12s}   {fmt(ratio(cy['SNPP', y], cy['Aqua', y])):>12s}")

    print("\n== B. what is not a vegetation fire (FIRMS 'type'), share of rows, and low confidence")
    for n in order:
        p = P[n]
        ct = Counter(p.typ)
        tot_n = len(p)
        cdn = Counter(zip(p.dn, (1 if t != 0 else 0 for t in p.typ)))
        print(f"  {n:5s} type0={ct[0] / tot_n:6.1%} type1={ct[1] / tot_n:6.2%} type2={ct[2] / tot_n:6.1%} "
              f"type3={ct[3] / tot_n:6.2%} missing={ct[-1] / tot_n:6.2%} | not-vegetation share by day "
              f"{ratio(cdn[0, 1], cdn[0, 0] + cdn[0, 1]):5.1%}, by night {ratio(cdn[1, 1], cdn[1, 0] + cdn[1, 1]):5.1%}"
              f" | night share of all {sum(p.dn) / tot_n:5.1%} | low-conf {sum(p.low) / tot_n:5.1%}")

    # monthly aggregates, vegetation fires only (type 0) -----------------
    # units: n = raw hotspots, c = distinct (day, dn, 1 km cell), g = distinct (day, dn, ~11 km cell), f = FRP sum
    M = {u: Counter() for u in "ncgf"}       # key (plat, y, m, dn)
    R = Counter()                              # raw per 1-degree region: (plat, y, m, region)
    DAILY = {n: Counter() for n in order}      # type-0 rows per day
    for n in order:
        p = P[n]
        seen_c: set[int] = set()
        seen_g: set[int] = set()
        for i in range(len(p)):
            if p.typ[i] != 0:
                continue
            y, m, dn = p.year[i], p.month[i], p.dn[i]
            k = (n, y, m, dn)
            M["n"][k] += 1
            M["f"][k] += p.frp[i]
            DAILY[n][p.day[i]] += 1
            dd = p.day[i] * 2 + dn
            c = p.cell[i]
            kc = dd * 4_000_000 + c
            if kc not in seen_c:
                seen_c.add(kc)
                M["c"][k] += 1
            la, lo = divmod(c, NLON)
            kg = dd * 4_000_000 + (la // 10) * NLON + lo // 10
            if kg not in seen_g:
                seen_g.add(kg)
                M["g"][k] += 1
            R[n, y, m, (int(p.lat[i]), int(p.lon[i]))] += 1

    def tot(u: str, n: str, years, months=range(1, 13), dns=(0, 1)) -> float:
        return sum(M[u][n, y, m, d] for y in years for m in months for d in dns)

    print(f"\n== C. SNPP / Aqua for vegetation fires (type 0), {YEARS[0]}-{YEARS[-1]}, by calendar month")
    print("  month   Aqua_n  SNPP_n | raw: all   day  night | 1km cell-days | 11km cell-days | FRP sum | Terra/Aqua day | N20/SNPP 2018-21")
    for m in range(1, 13):
        a, s = tot("n", "Aqua", YEARS, [m]), tot("n", "SNPP", YEARS, [m])
        print(f"  {m:5d} {int(a):8d} {int(s):7d} | {fmt(ratio(s, a)):>8s} "
              f"{fmt(ratio(tot('n', 'SNPP', YEARS, [m], [0]), tot('n', 'Aqua', YEARS, [m], [0]))):>5s} "
              f"{fmt(ratio(tot('n', 'SNPP', YEARS, [m], [1]), tot('n', 'Aqua', YEARS, [m], [1]))):>6s} | "
              f"{fmt(ratio(tot('c', 'SNPP', YEARS, [m]), tot('c', 'Aqua', YEARS, [m]))):>13s} | "
              f"{fmt(ratio(tot('g', 'SNPP', YEARS, [m]), tot('g', 'Aqua', YEARS, [m]))):>14s} | "
              f"{fmt(ratio(tot('f', 'SNPP', YEARS, [m]), tot('f', 'Aqua', YEARS, [m]))):>7s} | "
              f"{fmt(ratio(tot('n', 'Terra', YEARS, [m], [0]), tot('n', 'Aqua', YEARS, [m], [0]))):>14s} | "
              f"{fmt(ratio(tot('n', 'N20', range(2018, 2022), [m]), tot('n', 'SNPP', range(2018, 2022), [m]))):>8s}")
    print("  by year: SNPP/Aqua raw | 1km cell-days | 11km cell-days | FRP ;  N20/SNPP raw day, night ;  Terra/Aqua raw day")
    for y in YEARS:
        print(f"  {y}  {fmt(ratio(tot('n', 'SNPP', [y]), tot('n', 'Aqua', [y]))):>6s} | "
              f"{fmt(ratio(tot('c', 'SNPP', [y]), tot('c', 'Aqua', [y]))):>6s} | "
              f"{fmt(ratio(tot('g', 'SNPP', [y]), tot('g', 'Aqua', [y]))):>6s} | "
              f"{fmt(ratio(tot('f', 'SNPP', [y]), tot('f', 'Aqua', [y]))):>6s} ;  "
              f"{fmt(ratio(tot('n', 'N20', [y], dns=[0]), tot('n', 'SNPP', [y], dns=[0]))):>6s} "
              f"{fmt(ratio(tot('n', 'N20', [y], dns=[1]), tot('n', 'SNPP', [y], dns=[1]))):>6s} ;  "
              f"{fmt(ratio(tot('n', 'Terra', [y], dns=[0]), tot('n', 'Aqua', [y], dns=[0]))):>6s}")
    tall = {n: tot("n", n, YEARS) for n in order}
    print("  totals of these years, type 0: " + ", ".join(f"{n}={int(v)}" for n, v in tall.items())
          + f" | SNPP/Aqua raw={ratio(tall['SNPP'], tall['Aqua']):.2f}"
          + f", 1km cell-days={ratio(tot('c', 'SNPP', YEARS), tot('c', 'Aqua', YEARS)):.2f}"
          + f", FRP={ratio(tot('f', 'SNPP', YEARS), tot('f', 'Aqua', YEARS)):.2f}")

    # ------------------------------------------------------------------ E
    print("\n== E. calibration test: learn on some years, predict the others (monthly, whole Ukraine)")

    def score(pred, actual, test) -> tuple:
        """pred, actual: f(y, m). Skip the quietest quarter of months."""
        vals = sorted(actual(y, m) for y in test for m in range(1, 13))
        thr = vals[len(vals) // 4]
        errs = [abs(math.log(max(pred(y, m), 0.5) / actual(y, m))) for y in test for m in range(1, 13) if actual(y, m) > thr]
        yerr = [abs(ratio(sum(pred(y, m) for m in range(1, 13)), sum(actual(y, m) for m in range(1, 13))) - 1) for y in test]
        return (math.exp(st.median(errs)) - 1, sum(e <= math.log(1.25) for e in errs) / len(errs),
                sum(e <= math.log(1.5) for e in errs) / len(errs), st.mean(yerr), max(yerr), len(errs))

    def show(name: str, v: tuple) -> None:
        print(f"      {name:24s} typical month error {v[0]:6.1%} | months within 25% {v[1]:5.0%} | within 50% {v[2]:5.0%}"
              f" | year totals: mean error {v[3]:5.1%}, worst {v[4]:5.1%}  (n={v[5]})")

    def evaluate(u: str, train, test, src: str = "Aqua", dst: str = "SNPP", dns=(0, 1)) -> dict[str, tuple]:
        A = lambda y, m, d=None: sum(M[u][src, y, m, x] for x in dns) if d is None else M[u][src, y, m, d]
        S = lambda y, m, d=None: sum(M[u][dst, y, m, x] for x in dns) if d is None else M[u][dst, y, m, d]
        kg = ratio(sum(S(y, m) for y in train for m in range(1, 13)),
                   sum(A(y, m) for y in train for m in range(1, 13)))
        km, kmd = {}, {}
        for m in range(1, 13):
            sa = sum(A(y, m) for y in train)
            km[m] = ratio(sum(S(y, m) for y in train), sa) if sa >= 10 else kg
            for d in (0, 1):
                sad = sum(A(y, m, d) for y in train)
                kmd[m, d] = ratio(sum(S(y, m, d) for y in train), sad) if sad >= 10 else kg
        xs = [math.log(A(y, m) + 1) for y in train for m in range(1, 13)]
        ys = [math.log(S(y, m) + 1) for y in train for m in range(1, 13)]
        b, a = st.linear_regression(xs, ys)
        preds = {
            "one factor": lambda y, m: kg * A(y, m),
            "factor per month": lambda y, m: km[m] * A(y, m),
            "per month x day/night": lambda y, m: sum(kmd[m, d] * A(y, m, d) for d in dns),
            "power law": lambda y, m: math.exp(a + b * math.log(A(y, m) + 1)) - 1,
        }
        out = {name: score(f, S, test) for name, f in preds.items()}
        out["_k"] = (kg, b)
        return out

    names = {"n": "raw hotspots", "c": "1 km cell-days", "g": "11 km cell-days", "f": "FRP sum"}
    span = lambda r: f"{r[0]}-{r[-1]}"
    for u in "ncgf":
        for train, test in ((TRAIN, TEST), (TEST, TRAIN)):
            res = evaluate(u, train, test)
            print(f"  Aqua -> SNPP, unit: {names[u]:16s} [learn {span(train)}, test {span(test)}]  one factor k={res['_k'][0]:.2f}")
            for name, v in res.items():
                if name != "_k":
                    show(name, v)
    print("  -- Aqua -> SNPP, daytime rows only, raw hotspots")
    for train, test in ((TRAIN, TEST), (TEST, TRAIN)):
        res = evaluate("n", train, test, dns=(0,))
        show(f"one factor [{span(train)}]", res["one factor"])
        show(f"per month  [{span(train)}]", res["factor per month"])
    print("  -- Terra -> Aqua (ten years of MODIS: 2012-16 <-> 2017-21), raw hotspots")
    for train, test in ((range(2012, 2017), range(2017, 2022)), (range(2017, 2022), range(2012, 2017))):
        for dns_, tag in (((0, 1), "all"), ((0,), "day")):
            res = evaluate("n", train, test, src="Terra", dst="Aqua", dns=dns_)
            show(f"{tag} one factor [{span(train)}]", res["one factor"])
            show(f"{tag} per month  [{span(train)}]", res["factor per month"])

    print("\n== E2. do the calendar colours agree? each sensor against its own normal month (leave-one-year-out)")
    for u in "ncf":
        ra, rs = [], []
        for y in YEARS:
            others = [yy for yy in YEARS if yy != y]
            for m in range(1, 13):
                ca = sum(M[u]["Aqua", yy, m, 0] + M[u]["Aqua", yy, m, 1] for yy in others) / len(others)
                cs = sum(M[u]["SNPP", yy, m, 0] + M[u]["SNPP", yy, m, 1] for yy in others) / len(others)
                if sum(M["n"]["SNPP", yy, m, 0] + M["n"]["SNPP", yy, m, 1] for yy in others) / len(others) < 100:
                    continue
                ra.append((M[u]["Aqua", y, m, 0] + M[u]["Aqua", y, m, 1]) / ca)
                rs.append((M[u]["SNPP", y, m, 0] + M[u]["SNPP", y, m, 1]) / cs)
        edges = [0.5, 0.8, 1.25, 2.0]
        ka = [bisect.bisect(edges, x) for x in ra]
        ks = [bisect.bisect(edges, x) for x in rs]
        same = sum(i == j for i, j in zip(ka, ks)) / len(ka)
        near = sum(abs(i - j) <= 1 for i, j in zip(ka, ks)) / len(ka)
        print(f"  unit: {names[u]:16s} months={len(ra):3d}  rank correlation={st.correlation(ra, rs, method='ranked'):.3f}  "
              f"same colour class={same:.0%}  same or neighbour class={near:.0%}")

    print(f"\n== E3. small areas: 1x1 degree boxes, monthly, learn {TRAIN[0]}-{TRAIN[-1]} -> test {TEST[0]}-{TEST[-1]} (raw hotspots)")
    regs = sorted({k[3] for k in R})
    kmN, kgN = {}, ratio(tot("n", "SNPP", TRAIN), tot("n", "Aqua", TRAIN))
    for m in range(1, 13):
        sa = tot("n", "Aqua", TRAIN, [m])
        kmN[m] = ratio(tot("n", "SNPP", TRAIN, [m]), sa) if sa >= 10 else kgN
    for lo, hi in ((20, 100), (100, 500), (500, 10**9)):
        e_nat, e_loc, e_shr = [], [], []
        for r in regs:
            for m in range(1, 13):
                sa = sum(R["Aqua", y, m, r] for y in TRAIN)
                ss = sum(R["SNPP", y, m, r] for y in TRAIN)
                k_loc = ss / sa if sa >= 5 else kmN[m]
                k_shr = (ss + 30 * kmN[m]) / (sa + 30)
                for y in TEST:
                    s, a = R["SNPP", y, m, r], R["Aqua", y, m, r]
                    if not lo <= s < hi:
                        continue
                    for k, e in ((kmN[m], e_nat), (k_loc, e_loc), (k_shr, e_shr)):
                        e.append(abs(math.log(max(k * a, 0.5) / s)))
        if e_nat:
            print(f"  box-months with {lo}..{hi if hi < 10**8 else 'inf'} SNPP hotspots (n={len(e_nat)}): typical error "
                  f"national factor {math.exp(st.median(e_nat)) - 1:6.1%} | own factor {math.exp(st.median(e_loc)) - 1:6.1%} "
                  f"| own, pulled to national {math.exp(st.median(e_shr)) - 1:6.1%}")

    # ------------------------------------------------------------------ G
    print("\n== G. at which time scale do two satellites agree? rank correlation of type-0 counts")
    def series_corr(a: str, b: str, y0: int, y1: int) -> tuple:
        d_lo, d_hi = date(y0, 1, 1).toordinal() - D0, date(y1, 12, 31).toordinal() - D0
        days = [d for d in range(d_lo, d_hi + 1) if DAILY[a][d] + DAILY[b][d] >= 20]
        cd = st.correlation([DAILY[a][d] for d in days], [DAILY[b][d] for d in days], method="ranked")
        ld = [math.log((DAILY[b][d] + 1) / (DAILY[a][d] + 1)) for d in days]
        ms = [(y, m) for y in range(y0, y1 + 1) for m in range(1, 13)
              if M["n"][a, y, m, 0] + M["n"][a, y, m, 1] + M["n"][b, y, m, 0] + M["n"][b, y, m, 1] >= 20]
        va = [M["n"][a, y, m, 0] + M["n"][a, y, m, 1] for y, m in ms]
        vb = [M["n"][b, y, m, 0] + M["n"][b, y, m, 1] for y, m in ms]
        cm = st.correlation(va, vb, method="ranked")
        lm = [math.log((y + 1) / (x + 1)) for x, y in zip(va, vb)]
        return cd, math.exp(st.pstdev(ld)), len(days), cm, math.exp(st.pstdev(lm)), len(ms)
    for a, b, y0, y1 in (("Aqua", "SNPP", YEARS[0], YEARS[-1]), ("Terra", "Aqua", YEARS[0], YEARS[-1]),
                         ("Terra", "SNPP", YEARS[0], YEARS[-1]), ("SNPP", "N20", 2018, 2021), ("Aqua", "N20", 2018, 2021)):
        if a in P and b in P:
            cd, sd, nd_, cm, sm, nm = series_corr(a, b, y0, y1)
            print(f"  {a:5s} vs {b:5s}: by day corr={cd:.2f}, ratio wobble x/÷{sd:.2f} (n={nd_}) | by month corr={cm:.2f}, ratio wobble x/÷{sm:.2f} (n={nm})")

    # ------------------------------------------------------------------ F
    print("\n== F. passes at nearly the same minute")
    aq, sn = P["Aqua"], P["SNPP"]
    PASS = {n: passes(P[n]) for n in order}
    amid, arows = PASS["Aqua"]
    smid, srows = PASS["SNPP"]
    print("  passes with a hotspot: " + ", ".join(f"{n}={len(PASS[n][0])}" for n in order))
    qs = sorted(sn.scan)
    print("  SNPP 'scan' quantiles 5/25/50/75/95%: " + ", ".join(f"{qs[int(len(qs) * q)]:.2f}" for q in (.05, .25, .5, .75, .95)))
    qa = sorted(aq.scan)
    print("  Aqua 'scan' quantiles 5/25/50/75/95%: " + ", ".join(f"{qa[int(len(qa) * q)]:.2f}" for q in (.05, .25, .5, .75, .95)))
    scan_mid = qs[len(qs) // 2]

    pairs_as = pair_passes(amid, smid)
    for other in ("SNPP", "N20", "Terra"):
        if other not in P:
            continue
        prs = pair_passes(amid, PASS[other][0]) if other != "N20" else pair_passes(smid, PASS["N20"][0])
        who = "Aqua" if other != "N20" else "SNPP"
        hist = Counter(min(int(abs(d) // 10), 6) for _, _, d in prs)
        print(f"  {who} pass -> nearest {other} pass, minutes apart: "
              + ", ".join(f"{b * 10}-{b * 10 + 10}: {hist[b]}" for b in range(6)) + f", 60+: {hist[6]}")
    simdays = defaultdict(set)
    for ia, js, d in pairs_as:
        if abs(d) <= 10:
            i0 = arows[ia][0]
            simdays[aq.year[i0], aq.dn[i0]].add(aq.day[i0])
    print("  days per year with an Aqua and a SNPP pass <=10 min apart (day / night): "
          + ", ".join(f"{y}: {len(simdays[y, 0])}/{len(simdays[y, 1])}" for y in YEARS))

    def curve(ref: str, oth: str, prs, lo: float, hi: float, years=YEARS, radius: int = 1, ref_scan_max: float = 9.0, season_of=None):
        """P(oth has a hotspot next to a ~1 km cell where ref has one), by the cell's summed ref FRP.

        prs pairs passes of oth (first) with passes of ref (second)."""
        pr, po = P[ref], P[oth]
        rrows, orows = PASS[ref][1], PASS[oth][1]
        hit, n = Counter(), Counter()
        for io, jr, d in prs:
            if not lo <= abs(d) <= hi:
                continue
            i0 = orows[io][0]
            if po.year[i0] not in years:
                continue
            ocells = {po.cell[i] for i in orows[io]}
            agg, nadir = defaultdict(float), {}
            for i in rrows[jr]:
                c = pr.cell[i]
                agg[c] += pr.frp[i]
                nadir[c] = min(nadir.get(c, 9.0), pr.scan[i])
            dn = po.dn[i0]
            key = ((season_of(po.month[i0]),) if season_of else ()) + (dn,)
            for c, f in agg.items():
                if nadir[c] > ref_scan_max:
                    continue
                b = bisect.bisect(BINS, f)
                n[key + (b,)] += 1
                if any(x in ocells for x in neighbours(c, radius)):
                    hit[key + (b,)] += 1
        return hit, n

    def show_curve(tag: str, hit, n) -> None:
        for dn, dname in ((0, "day"), (1, "night")):
            cells = sum(n[dn, b] for b in range(7))
            if not cells:
                continue
            print(f"  {tag:34s} {dname:5s} cells={cells:6d}  by FRP(MW) "
                  + "  ".join(f"{LABELS[b]}: {ratio(hit[dn, b], n[dn, b]):4.0%}" for b in range(7))
                  + f" | all: {ratio(sum(hit[dn, b] for b in range(7)), cells):4.0%}")

    print("  -- share of SNPP fire cells (near SNPP nadir) that Aqua also reports")
    for lo, hi in ((0, 5), (0, 10), (10, 30), (40, 60)):
        show_curve(f"Aqua sees SNPP's, {lo}-{hi} min apart", *curve("SNPP", "Aqua", pairs_as, lo, hi, ref_scan_max=scan_mid))
    print("  -- share of Aqua fire cells (Aqua scan <= 1.5) that SNPP also reports")
    pairs_sa = pair_passes(smid, amid)
    for lo, hi in ((0, 5), (0, 10), (40, 60)):
        show_curve(f"SNPP sees Aqua's, {lo}-{hi} min apart", *curve("Aqua", "SNPP", pairs_sa, lo, hi, ref_scan_max=1.5))
    if "N20" in P:
        print("  -- same eyes, ~50 min apart: share of SNPP fire cells (near nadir) that NOAA-20 also reports, and back")
        nmid = PASS["N20"][0]
        show_curve("N20 sees SNPP's, 40-60 min apart", *curve("SNPP", "N20", pair_passes(nmid, smid), 40, 60, ref_scan_max=scan_mid))
        show_curve("SNPP sees N20's, 40-60 min apart", *curve("N20", "SNPP", pair_passes(smid, nmid), 40, 60, ref_scan_max=scan_mid))

    for lo, hi in ((0, 10), (10, 30), (40, 60)):
        la, ls = [], []
        for ia, js, d in pairs_as:
            if lo <= abs(d) <= hi and len(arows[ia]) >= 5 and len(srows[js]) >= 5:
                la.append(math.log(len(arows[ia])))
                ls.append(math.log(len(srows[js])))
        if len(la) > 5:
            diff = [y - x for x, y in zip(la, ls)]
            print(f"  per-pass counts Aqua vs SNPP, {lo}-{hi} min apart: pairs={len(la)}  corr of log counts={st.correlation(la, ls):.2f}  "
                  f"median SNPP/Aqua={math.exp(st.median(diff)):.2f}  wobble x/÷{math.exp(st.pstdev(diff)):.2f}")

    # ----------------------------------------------------------------- F2
    print("\n== F2. 'make VIIRS look like MODIS': detection curve from same-minute passes of the learning years, then predict Aqua")
    warm = lambda m: 1 if 5 <= m <= 9 else 0
    srow_pass = {}
    for k, rows in srows.items():
        for i in rows:
            srow_pass[i] = k
    cellfrp: dict[tuple, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    ym_of_day = {}
    for i in range(len(sn)):
        ym_of_day[sn.day[i]] = (sn.year[i], sn.month[i])
        if sn.typ[i] == 0:
            cellfrp[sn.day[i], sn.dn[i], sn.cell[i]][srow_pass[i]] += sn.frp[i]
    actual = lambda y, m: M["c"]["Aqua", y, m, 0] + M["c"]["Aqua", y, m, 1]
    for train, test in ((TRAIN, TEST), (TEST, TRAIN)):
        print(f"  [learn {span(train)}, test {span(test)}]")
        hit, n = curve("SNPP", "Aqua", pairs_as, 0, 10, years=train, ref_scan_max=scan_mid)
        hit2, n2 = curve("SNPP", "Aqua", pairs_as, 0, 10, years=train, ref_scan_max=scan_mid, season_of=warm)
        prob = {k: (hit[k] + 1) / (n[k] + 2) for k in ((dn, b) for dn in (0, 1) for b in range(7))}
        prob2 = {k: (hit2[k] + 1) / (n2[k] + 2) for k in ((s_, dn, b) for s_ in (0, 1) for dn in (0, 1) for b in range(7))}
        print("    curve, day, all year : " + "  ".join(f"{LABELS[b]}: {prob[0, b]:4.0%}" for b in range(7)))
        print("    curve, day, Oct-Apr  : " + "  ".join(f"{LABELS[b]}: {prob2[0, 0, b]:4.0%}" for b in range(7))
              + f"   (cells={sum(n2[0, 0, b] for b in range(7))})")
        print("    curve, day, May-Sep  : " + "  ".join(f"{LABELS[b]}: {prob2[1, 0, b]:4.0%}" for b in range(7))
              + f"   (cells={sum(n2[1, 0, b] for b in range(7))})")
        exp1, exp2 = Counter(), Counter()
        thr_month = {t: Counter() for t in (5, 8)}
        for (d, dn, c), per_pass in cellfrp.items():
            f = max(per_pass.values())
            y, m = ym_of_day[d]
            b = bisect.bisect(BINS, f)
            exp1[y, m] += prob[dn, b]
            exp2[y, m] += prob2[warm(m), dn, b]
            for t in thr_month:
                if f >= t:
                    thr_month[t][y, m] += 1
        tr_sum = lambda cnt: sum(cnt[y, m] for y in train for m in range(1, 13))
        act_tr = sum(actual(y, m) for y in train for m in range(1, 13))
        g1, g2 = act_tr / tr_sum(exp1), act_tr / tr_sum(exp2)
        show(f"curve x one number ({g1:.2f})", score(lambda y, m: g1 * exp1[y, m], actual, test))
        show(f"2 season curves ({g2:.2f})", score(lambda y, m: g2 * exp2[y, m], actual, test))
        for t, cnt in thr_month.items():
            gt = act_tr / tr_sum(cnt)
            show(f"SNPP cells >= {t} MW (x{gt:.2f})", score(lambda y, m, cnt=cnt, gt=gt: gt * cnt[y, m], actual, test))
        res = evaluate("c", train, test, src="SNPP", dst="Aqua")
        for name in ("one factor", "factor per month"):
            show("SNPP->Aqua " + name, res[name])

    # ------------------------------------------------------------------ H
    print("\n== H. spots that 'burn' too often to be vegetation (SNPP, ~1 km cells, all SNPP years loaded)")
    days = defaultdict(set)
    months = defaultdict(set)
    tcnt = defaultdict(Counter)
    for i in range(len(sn)):
        c = sn.cell[i]
        days[c].add(sn.day[i])
        months[c].add(sn.month[i])
        tcnt[c][sn.typ[i]] += 1
    nd = sorted((len(v) for v in days.values()), reverse=True)
    print(f"  cells with any hotspot: {len(nd)}; distinct fire days per cell: median {nd[len(nd) // 2]}, "
          f"99th pct {nd[len(nd) // 100]}, max {nd[0]}")
    for thr in (10, 20, 40, 80):
        cs = [c for c, v in days.items() if len(v) >= thr]
        rows = sum(sum(tcnt[c].values()) for c in cs)
        t0 = sum(tcnt[c][0] for c in cs)
        print(f"  cells with >= {thr} fire days: {len(cs)} cells ({len(cs) / len(nd):.2%}), hold {rows / len(sn):.1%} of all SNPP rows; "
              f"{t0 / max(rows, 1):.0%} of those rows are labelled type 0 (vegetation) by FIRMS = {t0} rows")
    top = sorted(days, key=lambda c: -len(days[c]))[:8]
    for c in top:
        la, lo = divmod(c, NLON)
        tc = tcnt[c]
        print(f"    {LAT0 + (la + .5) * DLAT:7.3f}N {LON0 + (lo + .5) * DLON:7.3f}E  days={len(days[c]):4d} "
              f"months={len(months[c]):2d}  rows={sum(tc.values()):5d}  type0={tc[0]:5d} type2={tc[2]:5d} type3={tc[3]:5d}")
    static_cells = {c for c, tc in tcnt.items() if tc[2] + tc[3] > 0}
    near = sum(1 for i in range(len(sn)) if sn.typ[i] == 0 and any(x in static_cells for x in neighbours(sn.cell[i], 1)))
    t0_all = sum(1 for t in sn.typ if t == 0)
    print(f"  type-0 SNPP rows within ~1 km of a cell that FIRMS itself marks static: {near} ({near / t0_all:.1%} of type-0 rows)")
    nt = Counter((sn.dn[i], sn.typ[i] == 0) for i in range(len(sn)))
    print(f"  SNPP rows: day veg={nt[0, True]}, day other={nt[0, False]}, night veg={nt[1, True]}, night other={nt[1, False]}")

    # ------------------------------------------------------------------ K
    print("\n== K. holes: 3+ days in a row with no rows at all for one platform, April-October")
    for n in order:
        p = P[n]
        have = set(p.day)
        d_lo, d_hi = min(p.day), max(p.day)
        runs, start = [], None
        for d in range(d_lo, d_hi + 2):
            dt_ = date.fromordinal(D0 + d)
            empty = d <= d_hi and d not in have and 4 <= dt_.month <= 10 and dt_.year in YEARS
            if empty and start is None:
                start = d
            if not empty and start is not None:
                if d - start >= 3:
                    runs.append((start, d - start))
                start = None
        print(f"  {n:5s} " + (", ".join(f"{date.fromordinal(D0 + a)} x{k}d" for a, k in runs) or "none"))


if __name__ == "__main__":
    main()
