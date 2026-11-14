"""Helpers for the CSV the area API returns."""

from collections.abc import Iterable
from typing import TextIO

from .errors import FirmsResponseError


def merge_csv(csv_texts: Iterable[str], out: TextIO) -> int:
    """Write CSV texts to out as one table and return the number of rows.

    Only the first header is kept. Every text must have the same header:
    NRT and SP data differ (SP has an extra 'type' column), so they cannot
    be merged as they are.
    """
    header: str | None = None
    rows = 0
    for text in csv_texts:
        lines = text.strip().splitlines()
        if not lines:
            continue
        if header is None:
            header = lines[0]
            out.write(header + "\n")
        elif lines[0] != header:
            raise FirmsResponseError(f"header changed between chunks: {lines[0]}")
        for line in lines[1:]:
            out.write(line + "\n")
            rows += 1
    return rows
