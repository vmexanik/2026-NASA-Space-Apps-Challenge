#!/usr/bin/env python3
"""Download the yearly world archives of FIRMS hotspots (no MAP_KEY).

A file already downloaded in full is skipped, so a broken run is
resumed by running the command again.
"""

import argparse
import datetime as dt
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from firms.archive import Sensor, archive_files, download

DEFAULT_DIR = Path(__file__).resolve().parent / "data" / "raw" / "archive"

log = logging.getLogger("fetch_archive")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--last-year", type=int, default=dt.date.today().year - 1)
    parser.add_argument("--sensor", type=Sensor, action="append",
                        choices=list(Sensor), help="default: all")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        stream=sys.stderr)

    args.dir.mkdir(parents=True, exist_ok=True)
    items = archive_files(args.last_year, args.sensor)
    failed = []
    with ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(download, item, args.dir): item for item in items}
        for future in as_completed(futures):
            try:
                future.result()
            except OSError as err:
                failed.append(futures[future].name)
                log.error("failed %s: %s", futures[future].name, err)
    log.info("done: %d of %d files", len(items) - len(failed), len(items))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
