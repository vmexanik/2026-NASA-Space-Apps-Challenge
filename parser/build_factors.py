#!/usr/bin/env python3
"""Compute the harmonization factors and write the files of a method version.

Reads the FIRMS yearly archives in data/raw/archive and the current-year files in data/raw/api. Learns the
factor of every 2-degree square and calendar month for Aqua (2012-2022) and Terra (2012-2021) against VIIRS
Suomi NPP, assembles the series of satellites with backups for the days a satellite was silent, checks itself
year by year, measures NOAA-20 against Suomi NPP for the error of NOAA-20, and writes
data/harmonization/<version>/ for the database dump.
"""

import argparse
import datetime as dt
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from firms.archive import archive_files
from harmonize.counts import COUNTRIES, NOAA20_YEARS, TRAIN_YEARS, build_counts
from harmonize.days import satellite_days
from harmonize.export import write_version
from harmonize.factors import LAMBDA, chain
from harmonize.series import PERIODS, backup_segments, weight_rows
from harmonize.sources import api_files, archive_members
from harmonize.validate import (compare_chains, error_rows, metrics, noaa20_sets, predictions, terra_aqua_agreement,
                                terra_aqua_gap)

ROOT = Path(__file__).resolve().parent
LEARNING_YEARS = {"aqua": TRAIN_YEARS, "terra": tuple(range(2012, 2022))}
SENSORS = ("modis", "viirs-snpp", "viirs-jpss1")
VIIRS_ROWS = [("viirs", "snpp", 1, 0.0)]
TERRA_NOTE = ("Only Terra carries the series from date_from to date_to. On the 2003-2011 days both Terra and Aqua"
              " flew, harmonized Terra differs from harmonized Aqua by terra_vs_aqua_2003_2011,"
              " so the days from date_from to date_to may be off by about as much.")
VERSION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

log = logging.getLogger("build_factors")


def _version_name(text: str) -> str:
    """The version name, which becomes one folder under --out and the key of firms.method: never a path."""
    if not VERSION_NAME.fullmatch(text):
        raise argparse.ArgumentTypeError(f"{text!r} is not a version name: use letters, digits, '.', '_' and '-'")
    return text


def _years_on_disk(archive: Path, sensor: str) -> list[int]:
    found = (re.fullmatch(rf"{re.escape(sensor)}_(\d{{4}})_all_countries\.zip", p.name) for p in archive.iterdir())
    return sorted(int(m.group(1)) for m in found if m)


def _code_version() -> str:
    try:
        done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "uncommitted"
    return done.stdout.strip()


def _factor_rows(levels: dict[str, tuple]) -> list[tuple]:
    rows = []
    for sat in ("terra", "aqua"):
        lv, modis, viirs = levels[sat]
        for cell in range(90 * 180):
            r, c = divmod(cell, 180)
            for month in range(12):
                rows.append((sat, cell, month + 1, float(lv.factor[r, c, month]), int(modis[r, c, month]),
                             int(viirs[r, c, month]), float(lv.own_share[r, c, month]),
                             float(lv.cross_factor[r, c, month]), int(lv.cross_modis[r, c, month]),
                             float(lv.square8_factor[r, c, month]), float(lv.world_factor[month])))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", required=True, type=_version_name,
                        help="name of the method version, e.g. v1-2026-11-14")
    parser.add_argument("--lambda", dest="lam", type=float, default=LAMBDA,
                        help=f"borrowing strength in MODIS points (default {LAMBDA:g})")
    parser.add_argument("--data", type=Path, default=ROOT / "data", help="folder with raw/archive and raw/api")
    parser.add_argument("--last-year", type=int, default=dt.date.today().year - 1,
                        help="last year of the yearly archives, as fetch_archive.py downloads them (default: last year)")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "harmonization")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--force", action="store_true", help="replace an existing version folder")
    parser.add_argument("--no-cache", action="store_true", help="read the archives even if counts are cached")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    out = args.out / args.version
    if out.exists() and not args.force:
        log.error("%s exists; pass --force to replace it", out)
        return 1
    archive, api = args.data / "raw" / "archive", args.data / "raw" / "api"
    if not api.is_dir() or not any(api.glob("*/*.csv")):
        log.warning("no current-year files in %s: the days after %d have no satellite", api, args.last_year)
    needed = {item.name for item in archive_files(args.last_year)}
    needed |= {f"{s}_{y}_all_countries.zip" for s in ("modis", "viirs-snpp") for y in TRAIN_YEARS}
    needed |= {f"{s}_{y}_all_countries.zip" for s in ("viirs-snpp", "viirs-jpss1") for y in NOAA20_YEARS}
    missing = sorted(name for name in needed if not (archive / name).exists())
    if missing:
        log.error("archives missing in %s: %s", archive, ", ".join(missing))
        return 2

    members = [m for s in SENSORS for m in archive_members(archive, s, _years_on_disk(archive, s))]
    members += api_files(api) if api.is_dir() else []
    log.info("days of the satellites from %d files", len(members))
    days = satellite_days(members, args.jobs)
    log.info("counting points")
    counts = build_counts(archive, days, args.jobs, None if args.no_cache else args.out / ".cache")

    levels = {}
    for sat, years in LEARNING_YEARS.items():
        idx = [counts.years.index(y) for y in years]
        modis = counts.modis[sat][:, :, idx, :].sum(axis=2)
        viirs = counts.snpp[sat][:, :, idx, :].sum(axis=2)
        levels[sat] = (chain(modis, viirs, args.lam), modis, viirs)
    factors = {sat: lv.factor for sat, (lv, _, _) in levels.items()}
    backups, gaps = backup_segments(days)
    weights = weight_rows(factors, backups)

    log.info("checking: every learning year without itself")
    validation, measured = {}, []
    for sat, years in LEARNING_YEARS.items():
        sets = predictions(counts, sat, years, args.lam)
        validation[sat] = {area: metrics(a) for area, a in sets.items()}
        measured += error_rows(sets, sat)
    noaa20 = noaa20_sets(counts)
    validation["noaa20"] = {area: metrics(a) for area, a in noaa20.items()}
    measured += error_rows(noaa20, "noaa20", source="viirs")
    terra = next(p for p in PERIODS if p.satellite == "terra")
    gap = terra_aqua_gap(counts, factors)
    countries = {c: dict(zip(("old", "new"), compare_chains(counts, c, args.lam))) for c in COUNTRIES}
    params = {"square_deg": 2, "lambda": args.lam, "neighbourhood": "cross", "fallback": ["square8", "world"],
              "train_years": {s: [y[0], y[-1]] for s, y in LEARNING_YEARS.items()}, "reference": "snpp",
              "common_days_only": True, "confidence_filter": None, "type": 0, "code_version": _code_version(),
              "noaa20_error_years": [NOAA20_YEARS[0], NOAA20_YEARS[-1]],
              "terra_only": {"date_from": terra.start.isoformat(), "date_to": terra.end.isoformat(),
                             "terra_vs_aqua_2003_2011": None if gap is None else round(gap, 4), "note": TERRA_NOTE}}
    method = {"version": args.version, "label": f"MODIS to VIIRS factors, 2-degree squares, lambda {args.lam:g}",
              "params": params}
    factor_rows = _factor_rows(levels)
    report = {"version": args.version, "built_at": dt.datetime.now().isoformat(timespec="seconds"), "params": params,
              "validation": validation, "countries": countries,
              "terra_aqua": terra_aqua_agreement(counts, factors), "error_table": [list(r) for r in measured],
              "backups": [[b.satellite, b.start.isoformat(), b.end.isoformat() if b.end else None] for b in backups],
              "gaps": [g.isoformat() for g in gaps],
              "rows": {"method_weight": len(weights), "method_factor": len(factor_rows),
                       "method_error": len(measured) + len(VIIRS_ROWS), "method_gap": len(gaps)}}
    if out.exists():
        shutil.rmtree(out)
    write_version(out, method, weights, factor_rows, [r[:4] for r in measured] + VIIRS_ROWS, gaps, report)
    log.info("wrote %s: %d weight rows, %d backup runs, %d gap days", out, len(weights), len(backups), len(gaps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
