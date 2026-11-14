#!/usr/bin/env python3
"""Download this year's world hotspots from the FIRMS area API.

The yearly archives end with last year, so this year comes from the API:
standard processing (SP) where it exists, near real time (NRT) after it.
Each 5-day request is saved as its own CSV; a file already there is
skipped, so a broken run is resumed by running the command again. The
key's transaction limit is watched and the script waits when it runs low.
"""

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

from firms import WORLD, FirmsClient, FirmsError, Source, split_dates

ROOT = Path(__file__).resolve().parent
DEFAULT_DIR = ROOT / "data" / "raw" / "api"

#: SP and NRT source of each sensor the yearly archives carry.
SENSORS: dict[str, tuple[Source, Source]] = {
    "modis": (Source.MODIS_SP, Source.MODIS_NRT),
    "viirs-snpp": (Source.VIIRS_SNPP_SP, Source.VIIRS_SNPP_NRT),
    "viirs-jpss1": (Source.VIIRS_NOAA20_SP, Source.VIIRS_NOAA20_NRT),
}

#: A world 5-day request cost about 185 transactions; keep this many free.
RESERVE = 600

log = logging.getLogger("fetch_current_year")


def plan(client: FirmsClient, year: int, today: dt.date) -> list[tuple[Source, dt.date, int]]:
    """Every (source, start, days) request that covers year up to today."""
    dates = {a.data_id: a for a in client.availability()}
    jobs = []
    for sp, nrt in SENSORS.values():
        first = dt.date(year, 1, 1)
        sp_end = min(dates[sp.value].max_date, today)
        if sp_end >= first:
            jobs += [(sp, d, n) for d, n in split_dates(first, sp_end)]
        nrt_start = max(first, sp_end + dt.timedelta(days=1))
        if dates[nrt.value].min_date > nrt_start:
            log.warning("%s: no data %s..%s", nrt.value, nrt_start,
                        dates[nrt.value].min_date - dt.timedelta(days=1))
            nrt_start = dates[nrt.value].min_date
        nrt_end = min(dates[nrt.value].max_date, today)
        if nrt_end >= nrt_start:
            jobs += [(nrt, d, n) for d, n in split_dates(nrt_start, nrt_end)]
    return jobs


def needs_fetch(target: Path, source: Source, start: dt.date, days: int, today: dt.date) -> bool:
    """True if the chunk of days from start must be downloaded into target."""
    # Passes of an NRT chunk's last day keep arriving for hours after the
    # day ends, so a chunk that ends yesterday or today is fetched again.
    last_day = start + dt.timedelta(days=days - 1)
    growing = source.is_near_real_time and last_day >= today - dt.timedelta(days=1)
    return not target.is_file() or growing


def wait_for_quota(client: FirmsClient) -> None:
    while (left := client.key_status().remaining) < RESERVE:
        log.info("key has %d transactions left, waiting", left)
        time.sleep(60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--year", type=int, default=dt.date.today().year)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        stream=sys.stderr)

    client = FirmsClient.from_env(ROOT / ".env", timeout=900)
    today = dt.datetime.now(dt.UTC).date()
    jobs = plan(client, args.year, today)
    failed = 0
    for i, (source, start, days) in enumerate(jobs, 1):
        target = args.dir / source.value / f"{start.isoformat()}_{days}d.csv"
        if not needs_fetch(target, source, start, days, today):
            continue
        wait_for_quota(client)
        try:
            chunk = client.chunk(source, WORLD, start, days)
        except FirmsError as err:
            failed += 1
            log.error("%s %s: %s", source.value, start, err)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        part.write_text(chunk.csv_text)
        part.rename(target)
        log.info("[%d/%d] %s %s..%s: %d rows", i, len(jobs), source.value,
                 chunk.start, chunk.end, chunk.row_count)
    log.info("done: %d requests, %d failed", len(jobs), failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
