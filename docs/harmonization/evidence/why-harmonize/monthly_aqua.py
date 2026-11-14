import csv, io, sys, zipfile, json, os
root = sys.argv[1]
out = {}
for y in range(2002, 2026):
    with zipfile.ZipFile(os.path.join(root, f"modis_{y}_all_countries.zip")) as z:
        with z.open(f"modis/{y}/modis_{y}_Ukraine.csv") as fh:
            for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
                if r.get("type") == "0" and r["satellite"] == "Aqua":
                    k = r["acq_date"][:7]
                    out[k] = out.get(k, 0) + 1
json.dump(out, open(sys.argv[2], "w"), sort_keys=True)
