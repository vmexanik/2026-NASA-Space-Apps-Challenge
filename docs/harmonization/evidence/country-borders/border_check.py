#!/usr/bin/env python3
"""Do the MODIS and the VIIRS country files of FIRMS draw a country's border the same way?

Usage: python3 -I border_check.py <archive dir> <first year> <last year> <Target> <lat0,lat1,lon0,lon1> [<Neighbour> ...]

The box is cut into cells of 0.05 degrees. For each sensor and cell it counts the points of the target and of its
neighbours (all types, both MODIS satellites: the border does not depend on them), and the points the comparison of
approaches uses (target, type 0, Aqua for MODIS). Then:
  border cells  cells that hold points of the target and of a neighbour in either sensor
  share test    border cells with 5+ points in both sensors: the share of the cell's points given to the target,
                MODIS against VIIRS; a gap of 0.5 or more means the two files put the border in different places
  one-sided     cells with 3+ target points (type 0) in MODIS and no target point at all in VIIRS over all years,
                although VIIRS sees several times more fires: a sign that the VIIRS file leaves the place out
"""
import csv
import io
import os
import sys
import zipfile
from collections import defaultdict
from multiprocessing import Pool

ROOT, Y0, Y1, TARGET = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
LAT0, LAT1, LON0, LON1 = (float(x) for x in sys.argv[5].split(","))
NEIGHBOURS = sys.argv[6:]
CELL = 0.05


def job(args):
    sensor, year, country = args
    counts = defaultdict(lambda: [0, 0, 0])  # all points, target points, target points the comparison uses
    name = f"{sensor}/{year}/{sensor}_{year}_{country}.csv"
    with zipfile.ZipFile(os.path.join(ROOT, f"{sensor}_{year}_all_countries.zip")) as z:
        if name not in z.namelist():
            return sensor, {}, f"missing {name}"
        with z.open(name) as fh:
            for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
                lat, lon = float(r["latitude"]), float(r["longitude"])
                if not (LAT0 <= lat <= LAT1 and LON0 <= lon <= LON1):
                    continue
                c = counts[(int(lat // CELL), int(lon // CELL))]
                c[0] += 1
                if country == TARGET:
                    c[1] += 1
                    if r["type"] == "0" and (sensor != "modis" or r["satellite"] == "Aqua"):
                        c[2] += 1
    return sensor, dict(counts), None


if __name__ == "__main__":
    jobs = [(s, y, c) for s in ("modis", "viirs-snpp") for y in range(Y0, Y1 + 1) for c in [TARGET] + NEIGHBOURS]
    grid = {"modis": defaultdict(lambda: [0, 0, 0]), "viirs-snpp": defaultdict(lambda: [0, 0, 0])}
    with Pool(24) as pool:
        for sensor, counts, err in pool.imap_unordered(job, jobs):
            if err:
                print(err)
            for k, v in counts.items():
                g = grid[sensor][k]
                for i in range(3):
                    g[i] += v[i]
    M, V = grid["modis"], grid["viirs-snpp"]
    used_m = sum(v[2] for v in M.values())
    used_v = sum(v[2] for v in V.values())
    cells = set(M) | set(V)

    def mixed(g, k):
        v = g.get(k)
        return v is not None and 0 < v[1] < v[0]

    border = {k for k in cells if mixed(M, k) or mixed(V, k)}
    tested = [k for k in border if M.get(k, [0])[0] >= 5 and V.get(k, [0])[0] >= 5]
    gaps = [k for k in tested if abs(M[k][1] / M[k][0] - V[k][1] / V[k][0]) >= 0.5]
    mean_gap = sum(M[k][1] / M[k][0] - V[k][1] / V[k][0] for k in tested) / max(len(tested), 1)
    border_m = sum(M[k][2] for k in border if k in M)
    border_v = sum(V[k][2] for k in border if k in V)
    gap_m = sum(M[k][2] for k in gaps)
    gap_v = sum(V[k][2] for k in gaps)
    one_sided = [k for k in cells if M.get(k, [0, 0, 0])[2] >= 3 and V.get(k, [0, 0, 0])[1] == 0]
    one_m = sum(M[k][2] for k in one_sided)
    ratio_all = used_v / used_m
    ratio_inner = (used_v - border_v) / (used_m - border_m)

    print(f"{TARGET} {Y0}-{Y1}, neighbours: {' '.join(NEIGHBOURS) or 'none'}")
    print(f"  points the comparison uses: MODIS Aqua {used_m}, VIIRS {used_v}, ratio {ratio_all:.3f}")
    print(f"  border cells (0.05 deg): {len(border)}; they hold {border_m / used_m:.2%} of MODIS and "
          f"{border_v / used_v:.2%} of VIIRS points; ratio without them {ratio_inner:.3f} "
          f"({ratio_inner / ratio_all - 1:+.2%})")
    print(f"  share test: {len(tested)} border cells with 5+ points in both; mean share gap MODIS-VIIRS {mean_gap:+.3f}; "
          f"{len(gaps)} cells with a gap of 0.5+, holding {gap_m} MODIS and {gap_v} VIIRS points")
    print(f"  one-sided: {len(one_sided)} cells with 3+ MODIS points and no VIIRS point, holding {one_m} MODIS points "
          f"({one_m / used_m:.2%})")
    for k in sorted(one_sided, key=lambda k: -M[k][2])[:8]:
        print(f"    cell lat {k[0] * CELL:.2f} lon {k[1] * CELL:.2f}: MODIS {M[k][2]}, VIIRS (any country) {V.get(k, [0])[0]}")
    for k in sorted(gaps, key=lambda k: -(M[k][2] + V[k][2]))[:8]:
        print(f"    gap cell lat {k[0] * CELL:.2f} lon {k[1] * CELL:.2f}: target share MODIS {M[k][1] / M[k][0]:.2f} "
              f"VIIRS {V[k][1] / V[k][0]:.2f}")
