#!/usr/bin/env python3
"""Which rows to leave out so that the MODIS -> VIIRS multiplier repeats from year to year?

Every variant keeps a subset of the Aqua rows and a subset of the Suomi NPP rows (vegetation fires,
Ukraine, 2012-2021), counts them per month, and reports how well the multiplier of a calendar month
holds from one year to the next.

Usage: python3 -I feature_study.py <folder with modis_*_Ukraine.csv and viirs-snpp_*_Ukraine.csv>
"""
import csv
import glob
import math
import os
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import date

DATA = sys.argv[1]
YEARS = list(range(2012, 2022))
D0 = date(2012, 1, 1).toordinal()
LAT0, LON0, DLAT, DLON, NLON = 43.0, 21.0, 0.01, 0.015, 2000  # ~1.1 km cells

# row fields
Y, MO, DN, FRP, SCAN, CONF, CONFN, LST, T4, DT, T11, LAT, LON, CDF, CPF, CFRP, CN = range(17)


def load(pattern: str, sat: str | None, viirs: bool) -> list[list]:
    raw = []
    dcache: dict[str, tuple[int, int, int]] = {}
    for path in sorted(glob.glob(os.path.join(DATA, pattern))):
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["type"] != "0" or (sat and r["satellite"] != sat):
                    continue
                ds = r["acq_date"]
                d = dcache.get(ds)
                if d is None:
                    yy, mm, dd = int(ds[:4]), int(ds[5:7]), int(ds[8:10])
                    d = dcache[ds] = (date(yy, mm, dd).toordinal() - D0, yy, mm)
                if d[1] not in YEARS:
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
                dn = 0 if r["daynight"] == "D" else 1
                cell = int((lat - LAT0) / DLAT) * NLON + int((lon - LON0) / DLON)
                raw.append((d[0], minute, cell, [d[1], d[2], dn, float(r["frp"] or 0), float(r["scan"]), conf, confn,
                                                 (minute / 60 + lon / 15) % 24, t4, t4 - t11, t11, lat, lon, 0, 0, 0.0, 0]))
    # overpasses: a new pass after a gap of more than 20 minutes
    at = sorted({day * 1440 + minute for day, minute, _, _ in raw})
    pid, n, last = {}, -1, -10**9
    for t in at:
        if t - last > 20:
            n += 1
        pid[t] = n
        last = t
    cellpass: dict[tuple[int, int], list] = defaultdict(list)
    seen_day: set[tuple[int, int, int]] = set()
    rows = []
    for day, minute, cell, row in raw:
        kd = (day, row[DN], cell)
        if kd not in seen_day:
            seen_day.add(kd)
            row[CDF] = 1
        cellpass[pid[day * 1440 + minute], cell].append(row)
        rows.append(row)
    for group in cellpass.values():
        total = sum(r[FRP] for r in group)
        group[0][CPF] = 1
        for r in group:
            r[CFRP] = total
            r[CN] = len(group)
    return rows


print("loading...", flush=True)
M = load("modis_*_Ukraine.csv", "Aqua", False)
V = load("viirs-snpp_*_Ukraine.csv", None, True)
print(f"vegetation fire rows 2012-2021: Aqua {len(M)}, Suomi NPP {len(V)}")
for name, rows in (("Aqua", M), ("Suomi NPP", V)):
    for f, label in ((LST, "local solar time, day rows"), (SCAN, "pixel width"), (FRP, "FRP, MW"), (DT, "T4 - T11, K"), (T11, "T11, K")):
        v = sorted(r[f] for r in rows if r[DN] == 0)
        print(f"  {name:9s} {label:27s} 5/25/50/75/95%: " + " ".join(f"{v[int(len(v) * q)]:7.2f}" for q in (.05, .25, .5, .75, .95)))


def monthly(rows, pred) -> Counter:
    c: Counter = Counter()
    for r in rows:
        if pred(r):
            c[r[Y], r[MO]] += 1
    return c


def metrics(cm: Counter, cv: Counter) -> dict:
    """How well the multiplier of a calendar month repeats between years."""
    tm = {m: sum(cm[y, m] for y in YEARS) for m in range(1, 13)}
    tv = {m: sum(cv[y, m] for y in YEARS) for m in range(1, 13)}
    k = {m: tv[m] / tm[m] for m in range(1, 13) if tm[m] > 0}
    devs, floor = [], []
    for y in YEARS:
        for m in range(1, 13):
            a, s = cm[y, m], cv[y, m]
            if a >= 50 and s > 0:
                devs.append(abs(math.log((s / a) / k[m])))
                floor.append(0.6745 * math.sqrt(1 / a + 1 / s))

    def test(train, test_years, per_month: bool) -> float:
        kg = sum(cv[y, m] for y in train for m in range(1, 13)) / max(sum(cm[y, m] for y in train for m in range(1, 13)), 1)
        km = {}
        for m in range(1, 13):
            sa = sum(cm[y, m] for y in train)
            km[m] = sum(cv[y, m] for y in train) / sa if (per_month and sa >= 10) else kg
        vals = sorted(cv[y, m] for y in test_years for m in range(1, 13))
        thr = vals[len(vals) // 4]
        errs = [abs(math.log(max(km[m] * cm[y, m], 0.5) / cv[y, m])) for y in test_years for m in range(1, 13) if cv[y, m] > thr]
        return math.exp(st.median(errs)) - 1

    main = [m for m in range(1, 13) if tm[m] >= 500]
    return {
        "m": sum(tm.values()), "v": sum(tv.values()),
        "ratio": sum(tv.values()) / max(sum(tm.values()), 1),
        "kmin": min(k[m] for m in main) if main else float("nan"),
        "kmax": max(k[m] for m in main) if main else float("nan"),
        "n": len(devs),
        "spread": math.exp(st.median(devs)) - 1 if devs else float("nan"),
        "floor": math.exp(st.median(floor)) - 1 if floor else float("nan"),
        "test": (test(YEARS[:5], YEARS[5:], True) + test(YEARS[5:], YEARS[:5], True)) / 2,
        "one": (test(YEARS[:5], YEARS[5:], False) + test(YEARS[5:], YEARS[:5], False)) / 2,
    }


day = lambda r: r[DN] == 0
VARIANTS: list[tuple[str, str, object, object]] = [
    # group, name, Aqua rows kept, Suomi NPP rows kept
    ("0 start", "all rows, day and night", lambda r: True, lambda r: True),
    ("0 start", "night only", lambda r: r[DN] == 1, lambda r: r[DN] == 1),
    ("0 start", "DAY ONLY (base for all below)", day, day),
]


def add(group: str, name: str, fm, fv) -> None:
    VARIANTS.append((group, name, (lambda r, f=fm: r[DN] == 0 and f(r)), (lambda r, f=fv: r[DN] == 0 and f(r))))


T = lambda r: True
# confidence
add("confidence", "drop low confidence, both", lambda r: r[CONF] >= 1, lambda r: r[CONF] >= 1)
add("confidence", "MODIS confidence >= 50, VIIRS not low", lambda r: r[CONFN] >= 50, lambda r: r[CONF] >= 1)
add("confidence", "MODIS confidence >= 80, VIIRS all", lambda r: r[CONFN] >= 80, T)
# fire power of the row
for t in (1, 2, 3, 5):
    add("power", f"VIIRS rows of {t}+ MW", T, lambda r, t=t: r[FRP] >= t)
for t in (8, 10, 15, 20):
    add("power", f"MODIS rows of {t}+ MW", lambda r, t=t: r[FRP] >= t, T)
# pixel size
for s in (1.3, 1.5, 2.0):
    add("pixel size", f"MODIS pixel width <= {s} km", lambda r, s=s: r[SCAN] <= s, T)
add("pixel size", "VIIRS pixel width <= 0.45 km", T, lambda r: r[SCAN] <= 0.45)
add("pixel size", "both near nadir: MODIS <= 1.5, VIIRS <= 0.45", lambda r: r[SCAN] <= 1.5, lambda r: r[SCAN] <= 0.45)
# hour of the pass
add("hour", "both 12:30-13:30 local solar time", lambda r: 12.5 <= r[LST] <= 13.5, lambda r: 12.5 <= r[LST] <= 13.5)
add("hour", "both 12:00-14:00 local solar time", lambda r: 12.0 <= r[LST] <= 14.0, lambda r: 12.0 <= r[LST] <= 14.0)
# brightness
for t in (15, 25, 40):
    add("brightness", f"VIIRS T4-T11 >= {t} K", T, lambda r, t=t: r[DT] >= t)
for t in (15, 25):
    add("brightness", f"MODIS T4-T11 >= {t} K", lambda r, t=t: r[DT] >= t, T)
add("brightness", "background T11 <= 300 K, both", lambda r: r[T11] <= 300, lambda r: r[T11] <= 300)
add("brightness", "background T11 > 300 K, both", lambda r: r[T11] > 300, lambda r: r[T11] > 300)
# repeats
add("repeats", "one count per ~1 km cell per day, both", lambda r: r[CDF] == 1, lambda r: r[CDF] == 1)
add("repeats", "one count per ~1 km cell per pass, both", lambda r: r[CPF] == 1, lambda r: r[CPF] == 1)
add("repeats", "VIIRS as ~1 km cells per pass, MODIS rows", T, lambda r: r[CPF] == 1)
# VIIRS seen through a MODIS-sized pixel: power of the whole ~1 km cell
for t in (3, 5, 8, 12, 20):
    add("cell power", f"VIIRS ~1 km cells of {t}+ MW", T, lambda r, t=t: r[CPF] == 1 and r[CFRP] >= t)
for t in (10, 15, 20, 30, 50):
    add("same bar", f"both {t}+ MW: MODIS row, VIIRS ~1 km cell", lambda r, t=t: r[FRP] >= t, lambda r, t=t: r[CPF] == 1 and r[CFRP] >= t)
for t in (5, 8):
    add("same bar", f"both {t}+ MW: MODIS row, VIIRS ~1 km cell", lambda r, t=t: r[FRP] >= t, lambda r, t=t: r[CPF] == 1 and r[CFRP] >= t)
# the same bar with the night left in, and for the night alone
for t in (10, 15, 20):
    VARIANTS.append(("same bar, night kept", f"day and night, both {t}+ MW", (lambda r, t=t: r[FRP] >= t), (lambda r, t=t: r[CPF] == 1 and r[CFRP] >= t)))
for t in (10, 20):
    VARIANTS.append(("same bar, night kept", f"night only, both {t}+ MW", (lambda r, t=t: r[DN] == 1 and r[FRP] >= t), (lambda r, t=t: r[DN] == 1 and r[CPF] == 1 and r[CFRP] >= t)))
# place
add("place", "north of 49N", lambda r: r[LAT] >= 49, lambda r: r[LAT] >= 49)
add("place", "south of 49N", lambda r: r[LAT] < 49, lambda r: r[LAT] < 49)
add("place", "west of 31E", lambda r: r[LON] < 31, lambda r: r[LON] < 31)
add("place", "east of 31E", lambda r: r[LON] >= 31, lambda r: r[LON] >= 31)
# combinations
add("combo", "no low confidence + VIIRS cells 5+ MW", lambda r: r[CONF] >= 1, lambda r: r[CPF] == 1 and r[CFRP] >= 5 and r[CONF] >= 1)
add("combo", "MODIS width <= 2.0 + VIIRS cells 5+ MW", lambda r: r[SCAN] <= 2.0, lambda r: r[CPF] == 1 and r[CFRP] >= 5)
add("combo", "both 20+ MW + MODIS width <= 2.0", lambda r: r[FRP] >= 20 and r[SCAN] <= 2.0, lambda r: r[CPF] == 1 and r[CFRP] >= 20)
add("combo", "both 20+ MW + one count per cell per day", lambda r: r[FRP] >= 20 and r[CDF] == 1, lambda r: r[CPF] == 1 and r[CDF] == 1 and r[CFRP] >= 20)
add("combo", "MODIS 10+ MW + VIIRS cells 8+ MW", lambda r: r[FRP] >= 10, lambda r: r[CPF] == 1 and r[CFRP] >= 8)

res = []
for group, name, fm, fv in VARIANTS:
    res.append((group, name, metrics(monthly(M, fm), monthly(V, fv))))
    print(".", end="", flush=True)
print()
base_m, base_v = len(M), len(V)

hdr = (f"{'what is kept':52s} {'MODIS':>7s} {'VIIRS':>7s} {'ratio':>6s} {'by month':>11s} | "
       f"{'year-to-year':>12s} {'count noise':>11s} {'months':>6s} | {'test: 12 factors':>16s} {'one factor':>10s}")


def show(rows) -> None:
    print(hdr)
    for group, name, r in rows:
        print(f"{name:52s} {r['m'] / base_m:7.0%} {r['v'] / base_v:7.0%} {r['ratio']:6.2f} {r['kmin']:5.1f}-{r['kmax']:<5.1f} | "
              f"{r['spread']:12.1%} {r['floor']:11.1%} {r['n']:6d} | {r['test']:16.1%} {r['one']:10.1%}")


print("\n== every variant, in groups (columns: share of rows kept; VIIRS per MODIS overall and by calendar month;")
print("   typical gap between a year's multiplier and the ten-year one; the gap pure counting noise would give; year-months used;")
print("   typical month error when the factors come from five other years)")
group = None
for g in dict.fromkeys(v[0] for v in VARIANTS):
    print(f"\n-- {g}")
    show([r for r in res if r[0] == g])

print("\n== the same, best first by year-to-year gap (only variants that keep 100+ year-months... or all)")
show(sorted(res, key=lambda r: r[2]["spread"]))
