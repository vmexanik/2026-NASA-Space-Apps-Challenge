"""Which country file holds the fire points of Crimea, for MODIS and VIIRS, per year.

Usage: python3 -I crimea.py <archive dir> <year> [<year> ...]
Crimea is taken as the box lat 44.38-45.95, lon 32.40-36.62 (the peninsula south of the Perekop isthmus).
"""
import csv, io, os, sys, zipfile
root = sys.argv[1]
for year in sys.argv[2:]:
    for sensor in ("modis", "viirs-snpp"):
        out = []
        with zipfile.ZipFile(os.path.join(root, f"{sensor}_{year}_all_countries.zip")) as z:
            for country in ("Ukraine", "Russian_Federation"):
                n_all = n_veg = 0
                with z.open(f"{sensor}/{year}/{sensor}_{year}_{country}.csv") as fh:
                    for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
                        lat, lon = float(r["latitude"]), float(r["longitude"])
                        if 44.38 <= lat <= 45.95 and 32.40 <= lon <= 36.62:
                            n_all += 1
                            n_veg += r["type"] == "0"
                out.append(f"{country}: {n_all} points ({n_veg} type 0)")
        print(year, sensor, " | ".join(out), flush=True)
