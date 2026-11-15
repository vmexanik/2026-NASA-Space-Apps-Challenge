import csv, io, sys, zipfile, json, os
root = sys.argv[1]
out = {}
for sensor, years in (("modis", range(2001, 2026)), ("viirs-snpp", range(2012, 2026))):
    for y in years:
        p = os.path.join(root, f"{sensor}_{y}_all_countries.zip")
        with zipfile.ZipFile(p) as z:
            name = f"{sensor}/{y}/{sensor}_{y}_Ukraine.csv"
            if name not in z.namelist():
                continue
            with z.open(name) as fh:
                n = {}
                for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
                    if r.get("type") != "0":
                        continue
                    k = r["satellite"]
                    n[k] = n.get(k, 0) + 1
        out[f"{sensor} {y}"] = n
        print(sensor, y, n, flush=True)
json.dump(out, open(sys.argv[2], "w"))
