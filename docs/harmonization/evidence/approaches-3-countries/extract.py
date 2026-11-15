#!/usr/bin/env python3
"""Cut the vegetation-fire rows (type = 0) of a few countries out of the FIRMS yearly world zips into numpy files.

Usage: python3 -I extract.py <archive dir> <out dir> <first year> <last year> <Country> [<Country> ...]

One file per country, sensor and year: <out>/<Country>_<sensor>_<year>.npz with the columns
lat, lon, frp, scan, track, t (minutes since 2000-01-01 UTC), day (1 for D), aqua (MODIS: 1 for Aqua, 0 for Terra).
"""
import csv
import io
import os
import sys
import zipfile
from datetime import date
from multiprocessing import Pool

import numpy as np

ARCHIVE, OUT, Y0, Y1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
COUNTRIES = sys.argv[5:]
D0 = date(2000, 1, 1).toordinal()


def job(args):
    sensor, year = args
    with zipfile.ZipFile(os.path.join(ARCHIVE, f"{sensor}_{year}_all_countries.zip")) as z:
        names = set(z.namelist())
        done = []
        for country in COUNTRIES:
            name = f"{sensor}/{year}/{sensor}_{year}_{country}.csv"
            if name not in names:
                done.append(f"{country} {sensor} {year}: missing")
                continue
            cols = {k: [] for k in ("lat", "lon", "frp", "scan", "track", "t", "day", "aqua")}
            with z.open(name) as fh:
                for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
                    if r.get("type") != "0":
                        continue
                    d = r["acq_date"]
                    hhmm = int(r["acq_time"])
                    cols["lat"].append(float(r["latitude"]))
                    cols["lon"].append(float(r["longitude"]))
                    cols["frp"].append(float(r["frp"] or 0))
                    cols["scan"].append(float(r["scan"]))
                    cols["track"].append(float(r["track"]))
                    day_no = date(int(d[:4]), int(d[5:7]), int(d[8:10])).toordinal() - D0
                    cols["t"].append(day_no * 1440 + (hhmm // 100) * 60 + hhmm % 100)
                    cols["day"].append(1 if r["daynight"] == "D" else 0)
                    cols["aqua"].append(1 if r["satellite"] == "Aqua" else 0)
            np.savez(os.path.join(OUT, f"{country}_{sensor}_{year}.npz"),
                     lat=np.array(cols["lat"], np.float32), lon=np.array(cols["lon"], np.float32),
                     frp=np.array(cols["frp"], np.float32), scan=np.array(cols["scan"], np.float32),
                     track=np.array(cols["track"], np.float32), t=np.array(cols["t"], np.int64),
                     day=np.array(cols["day"], np.int8), aqua=np.array(cols["aqua"], np.int8))
            done.append(f"{country} {sensor} {year}: {len(cols['lat'])}")
    return done


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    jobs = [(s, y) for y in range(Y0, Y1 + 1) for s in ("modis", "viirs-snpp")]
    with Pool(min(len(jobs), 24)) as pool:
        for lines in pool.imap_unordered(job, jobs):
            for line in lines:
                print(line, flush=True)
