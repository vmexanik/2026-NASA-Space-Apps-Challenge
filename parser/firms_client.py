#!/usr/bin/env python3
"""Command line for the firms package (NASA FIRMS active fire hotspots).

The MAP_KEY comes from the FIRMS_MAP_KEY environment variable or from the
.env file next to this script (a line FIRMS_MAP_KEY=...).

Commands:
  status        how many transactions the key has left
  availability  which dates each source has
  area          hotspots in an area for the latest N days or a date range;
                a long range is split into 5-day requests and joined
                into one CSV
"""

import argparse
import datetime as dt
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from firms import (
    DEFAULT_PAUSE,
    MAX_DAY_RANGE,
    MIN_DAY_RANGE,
    BoundingBox,
    FirmsClient,
    FirmsError,
    Source,
    merge_csv,
)

ENV_FILE = Path(__file__).resolve().parent / ".env"

log = logging.getLogger("firms_client")


def _area_arg(text: str) -> BoundingBox:
    try:
        return BoundingBox.parse(text)
    except ValueError as err:
        raise argparse.ArgumentTypeError(str(err)) from None


def _date_arg(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text}") from None


def build_parser() -> argparse.ArgumentParser:
    source_names = [s.value for s in Source]
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="transactions left on the MAP_KEY")

    p = sub.add_parser("availability", help="date range of each source")
    p.add_argument("--source", type=Source, choices=list(Source),
                   metavar="{" + ",".join(source_names) + "}",
                   help="one source; default: all")

    p = sub.add_parser("area", help="hotspots in an area")
    p.add_argument("--source", required=True, type=Source, choices=list(Source),
                   metavar="{" + ",".join(source_names) + "}")
    p.add_argument("--area", required=True, type=_area_arg,
                   help="'world' or west,south,east,north, e.g. 22,44,40.5,52.5")
    when = p.add_mutually_exclusive_group(required=True)
    when.add_argument("--days", type=int,
                      choices=range(MIN_DAY_RANGE, MAX_DAY_RANGE + 1),
                      help=f"the latest N days ({MIN_DAY_RANGE}..{MAX_DAY_RANGE})")
    when.add_argument("--start", type=_date_arg, help="YYYY-MM-DD")
    p.add_argument("--end", type=_date_arg,
                   help="YYYY-MM-DD, inclusive; default: same as --start")
    p.add_argument("-o", "--output", help="CSV file; default: stdout")
    p.add_argument("--pause", type=float, default=DEFAULT_PAUSE,
                   help=f"seconds between requests (default {DEFAULT_PAUSE:g})")
    return parser


def run_area(client: FirmsClient, args: argparse.Namespace) -> None:
    if args.days and args.end:
        raise ValueError("--end goes with --start, not with --days")
    if args.days:
        texts = [client.latest(args.source, args.area, args.days).csv_text]
    else:
        chunks = client.iter_range(args.source, args.area, args.start,
                                   args.end or args.start, pause=args.pause)
        texts = (chunk.csv_text for chunk in chunks)

    if args.output:
        with open(args.output, "w", newline="") as out:
            rows = merge_csv(texts, out)
        log.info("saved %d rows to %s", rows, args.output)
    else:
        rows = merge_csv(texts, sys.stdout)
        log.info("%d rows", rows)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    try:
        client = FirmsClient.from_env(ENV_FILE)
        if args.command == "status":
            status = client.key_status()
            print(json.dumps(asdict(status) | {"remaining": status.remaining}, indent=2))
        elif args.command == "availability":
            print("data_id,min_date,max_date")
            for item in client.availability(args.source):
                print(f"{item.data_id},{item.min_date},{item.max_date}")
        else:
            run_area(client, args)
        return 0
    except (FirmsError, ValueError) as err:
        log.error("error: %s", err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
