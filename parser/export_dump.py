#!/usr/bin/env python3
"""Build the dump package of the web database from the raw FIRMS files.

The package goes into --out: manifest.json, schema/*.sql, the gzip COPY files under data/, restore.sh and README.md.
restore.sh, run in the package folder, loads it into the firms schema of PostgreSQL 17+ with PostGIS 3. The same raw
files give the same data files. Each job holds the rows of one yearly zip in memory: up to about 2 GB for a VIIRS
zip of the world, much less for a slice of countries.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from firmsdb.export import build_package

ROOT = Path(__file__).resolve().parent

log = logging.getLogger("export_dump")


def _years(text: str) -> tuple[int, int]:
    first, _, last = text.partition("-")
    try:
        years = int(first), int(last or first)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not YYYY or YYYY-YYYY") from None
    if years[0] > years[1]:
        raise argparse.ArgumentTypeError(f"{text!r}: the first year is after the last")
    return years


def _countries(text: str) -> list[str]:
    names = [name.strip() for name in text.split(",")]
    if not all(names):
        raise argparse.ArgumentTypeError(f"{text!r} has an empty country name")
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="the package folder, such as data/dump/world")
    parser.add_argument("--name", help="the name of the package in manifest.json; default: the name of --out")
    parser.add_argument("--countries", type=_countries,
                        help="comma-separated names of the archive members <prefix>_<year>_<Country>.csv, such as "
                             "Ukraine,Russian_Federation; default: the world")
    parser.add_argument("--years", type=_years, help="YYYY-YYYY or YYYY: only the points of these years")
    parser.add_argument("--method", action="append", dest="methods", metavar="VERSION",
                        help="a method version: v0-raw or a folder of --harmonization; repeat for more; "
                             "default: v0-raw")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1), help="processes (default %(default)s)")
    parser.add_argument("--archive", type=Path, default=ROOT / "data" / "raw" / "archive",
                        help="the yearly zips of fetch_archive.py")
    parser.add_argument("--api", type=Path, default=ROOT / "data" / "raw" / "api",
                        help="the API files of fetch_current_year.py")
    parser.add_argument("--harmonization", type=Path, default=ROOT / "data" / "harmonization",
                        help="the method versions of build_factors.py")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)

    started = time.monotonic()
    try:
        manifest = build_package(args.out, archive_dir=args.archive, api_dir=args.api,
                                 harmonization_dir=args.harmonization, methods=args.methods or ["v0-raw"],
                                 countries=args.countries, years=args.years, jobs=args.jobs,
                                 name=args.name or args.out.resolve().name)
    except (ValueError, OSError) as err:
        log.error("export_dump.py: %s", err)
        return 1
    rows: dict[str, int] = {}
    for entry in manifest["files"]:
        rows[entry["table"]] = rows.get(entry["table"], 0) + entry["rows"]
    log.info("package %s in %s: %s; %.0f s", manifest["name"], args.out,
             ", ".join(f"{table} {count}" for table, count in rows.items()), time.monotonic() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
