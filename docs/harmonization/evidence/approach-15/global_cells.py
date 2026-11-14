#!/usr/bin/env python3
"""How many 2-degree cells of the globe have fires, and how many MODIS (Aqua) points each holds per calendar month.

Usage: python3 -I global_cells.py <archive dir> <first year> <last year> <out.json>

Reads every country file of the yearly MODIS world zips, keeps vegetation fires (type = 0) of Aqua, and counts the
points per 2-degree cell (row = floor((lat + 90) / 2), column = floor((lon + 180) / 2)) and calendar month.
"""
import csv
import io
import json
import os
import sys
import zipfile
from collections import Counter
from multiprocessing import Pool

ROOT, Y0, Y1, OUT = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]


def job(year):
    counts = Counter()
    with zipfile.ZipFile(os.path.join(ROOT, f"modis_{year}_all_countries.zip")) as z:
        for name in z.namelist():
            if not name.endswith(".csv"):
                continue
            with z.open(name) as fh:
                for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
                    if r["type"] != "0" or r["satellite"] != "Aqua":
                        continue
                    row = int((float(r["latitude"]) + 90) // 2)
                    col = int((float(r["longitude"]) + 180) // 2)
                    counts[(row, col, int(r["acq_date"][5:7]))] += 1
    return year, counts


if __name__ == "__main__":
    total = Counter()
    with Pool(Y1 - Y0 + 1) as pool:
        for year, counts in pool.imap_unordered(job, range(Y0, Y1 + 1)):
            total.update(counts)
            print(year, sum(counts.values()), flush=True)
    cells = Counter()
    for (row, col, month), n in total.items():
        cells[(row, col)] += n
    out = {"years": [Y0, Y1],
           "cell_month": [[row, col, month, n] for (row, col, month), n in total.items()],
           "cells": [[row, col, n] for (row, col), n in cells.items()]}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    pts = sum(cells.values())
    print(f"cells with fires: {len(cells)} of 16200; cell-months with fires: {len(total)}; points: {pts}")
    for lim in (10, 100, 1000):
        few = [n for n in total.values() if n < lim]
        print(f"  cell-months with fewer than {lim} points (11 years together): {len(few)} "
              f"({len(few) / len(total):.0%}), holding {sum(few) / pts:.1%} of points")
