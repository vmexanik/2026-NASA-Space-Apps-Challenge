"""Yearly world archives of FIRMS hotspots.

FIRMS publishes one zip of standard-processing hotspots per sensor and
year for all countries. They need no MAP_KEY and cost no transactions,
so the history 2000..last year comes from them; the current year comes
from the area API.
"""

from __future__ import annotations

import logging
import time
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from .constants import BASE_URL

ARCHIVE_URL: Final[str] = f"{BASE_URL}/data/country/zips"
CHUNK_SIZE: Final[int] = 1 << 20

log = logging.getLogger(__name__)


class Sensor(StrEnum):
    """File prefix of a yearly archive."""

    MODIS = "modis"
    VIIRS_SNPP = "viirs-snpp"
    VIIRS_NOAA20 = "viirs-jpss1"

    @property
    def first_year(self) -> int:
        """The first year FIRMS has an archive for."""
        return {Sensor.MODIS: 2000, Sensor.VIIRS_SNPP: 2012,
                Sensor.VIIRS_NOAA20: 2018}[self]


@dataclass(frozen=True, slots=True)
class ArchiveFile:
    """One yearly zip of one sensor."""

    sensor: Sensor
    year: int

    @property
    def name(self) -> str:
        return f"{self.sensor.value}_{self.year}_all_countries.zip"

    @property
    def url(self) -> str:
        return f"{ARCHIVE_URL}/{self.name}"


def archive_files(last_year: int, sensors: list[Sensor] | None = None) -> list[ArchiveFile]:
    """Every yearly zip from each sensor's first year to last_year."""
    return [ArchiveFile(sensor, year)
            for sensor in (sensors or list(Sensor))
            for year in range(sensor.first_year, last_year + 1)]


def _remote_size(url: str, timeout: float) -> int:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return int(resp.headers["Content-Length"])


def _fetch_rest(url: str, part: Path, timeout: float) -> None:
    """Append to part the bytes it does not have yet."""
    have = part.stat().st_size if part.is_file() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        mode = "ab" if resp.status == 206 else "wb"
        with open(part, mode) as out:
            while block := resp.read(CHUNK_SIZE):
                out.write(block)


def download(item: ArchiveFile, folder: Path, timeout: float = 120.0,
             attempts: int = 10, pause: float = 10.0) -> Path:
    """Download item into folder; skip it when the full file is there.

    The file grows as <name>.part, is resumed from where a broken
    request or run stopped, and is renamed once its size matches the
    server's, so a short zip never carries the final name.
    """
    target = folder / item.name
    part = target.with_name(target.name + ".part")
    size = _remote_size(item.url, timeout)
    if target.is_file() and target.stat().st_size == size:
        log.info("have %s", item.name)
        return target
    for attempt in range(1, attempts + 1):
        try:
            _fetch_rest(item.url, part, timeout)
        except OSError as err:
            log.warning("%s: attempt %d: %s", item.name, attempt, err)
        got = part.stat().st_size if part.is_file() else 0
        if got == size:
            part.rename(target)
            log.info("saved %s (%.0f MB)", item.name, got / 1e6)
            return target
        if got > size:
            part.unlink()
        time.sleep(pause)
    raise OSError(f"{item.name}: still short after {attempts} attempts")
