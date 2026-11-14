"""The FIRMS API client."""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import IO, Protocol

from .config import load_map_key
from .constants import (
    BASE_URL,
    DEFAULT_PAUSE,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    MAX_DAY_RANGE,
    MIN_DAY_RANGE,
    RETRY_STATUSES,
    Source,
)
from .errors import FirmsHTTPError, FirmsNetworkError, FirmsResponseError
from .models import WORLD, AreaChunk, BoundingBox, DataAvailability, KeyStatus

log = logging.getLogger(__name__)

#: First column of each CSV answer; anything else is an error message.
_AREA_FIRST_COLUMN = "latitude"
_AVAILABILITY_FIRST_COLUMN = "data_id"
_ALL_SOURCES = "ALL"


class Opener(Protocol):
    """Opens a URL; urllib.request.urlopen fits, tests pass a fake."""

    def __call__(
        self, url: str, *, timeout: float
    ) -> AbstractContextManager[IO[bytes]]: ...


def split_dates(
    start: dt.date, end: dt.date, step: int = MAX_DAY_RANGE
) -> list[tuple[dt.date, int]]:
    """Split [start, end] (inclusive) into (chunk_start, day_count) pieces
    of at most step days."""
    if end < start:
        raise ValueError("end date is before start date")
    if step < 1:
        raise ValueError("step must be at least 1")
    chunks: list[tuple[dt.date, int]] = []
    day = start
    while day <= end:
        count = min(step, (end - day).days + 1)
        chunks.append((day, count))
        day += dt.timedelta(days=count)
    return chunks


class FirmsClient:
    """Client of the NASA FIRMS API (active fire hotspots).

    Example:
        client = FirmsClient.from_env(Path(".env"))
        for chunk in client.iter_range(Source.VIIRS_NOAA20_SP,
                                       BoundingBox(22, 44, 40.5, 52.5),
                                       date(2024, 7, 1), date(2024, 7, 31)):
            print(chunk.start, chunk.row_count)
    """

    def __init__(
        self,
        map_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        opener: Opener | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Make a client for map_key.

        timeout is the socket timeout in seconds; retries is how many more
        times a request is tried after a 429, a 5xx or a network error.
        opener and sleep replace urllib and time.sleep in tests.
        """
        if not map_key:
            raise ValueError("map_key is empty")
        if retries < 0:
            raise ValueError("retries must be >= 0")
        self._map_key: str = map_key
        self._timeout: float = timeout
        self._retries: int = retries
        self._open: Opener = opener or urllib.request.urlopen
        self._sleep: Callable[[float], None] = sleep

    @classmethod
    def from_env(
        cls,
        env_file: Path | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ) -> FirmsClient:
        """Make a client with the key from FIRMS_MAP_KEY or env_file."""
        return cls(load_map_key(env_file), timeout=timeout, retries=retries)

    def __repr__(self) -> str:
        # Never show the key itself.
        return f"{type(self).__name__}(map_key='***', timeout={self._timeout})"

    # --- API calls ---------------------------------------------------------

    def key_status(self) -> KeyStatus:
        """How many transactions the key has spent in the current interval."""
        text = self._get(f"/mapserver/mapkey_status/?MAP_KEY={self._map_key}")
        try:
            return KeyStatus.from_json(json.loads(text))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            raise FirmsResponseError(text) from None

    def availability(self, source: Source | None = None) -> list[DataAvailability]:
        """The dates each data set covers; one source, or all when None."""
        sensor = source.value if source is not None else _ALL_SOURCES
        text = self._get(f"/api/data_availability/csv/{self._map_key}/{sensor}")
        lines = self._expect_csv(text, _AVAILABILITY_FIRST_COLUMN).splitlines()
        result: list[DataAvailability] = []
        for line in lines[1:]:
            if not line.strip():
                continue
            try:
                data_id, min_date, max_date = line.strip().split(",")
                result.append(
                    DataAvailability(
                        data_id=data_id,
                        min_date=dt.date.fromisoformat(min_date),
                        max_date=dt.date.fromisoformat(max_date),
                    )
                )
            except ValueError:
                raise FirmsResponseError(text) from None
        return result

    def latest(
        self, source: Source, area: BoundingBox = WORLD, days: int = 1
    ) -> AreaChunk:
        """Hotspots of the latest days (1..5): today and days-1 days back,
        by UTC."""
        self._check_day_range(days)
        text = self._get(self._area_path(source, area, days))
        start = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=days - 1)
        return AreaChunk(start, days, self._expect_csv(text, _AREA_FIRST_COLUMN))

    def chunk(
        self, source: Source, area: BoundingBox, start: dt.date, days: int
    ) -> AreaChunk:
        """Hotspots of days (1..5) days from start: one request."""
        self._check_day_range(days)
        path = self._area_path(source, area, days) + f"/{start.isoformat()}"
        return AreaChunk(start, days, self._expect_csv(self._get(path), _AREA_FIRST_COLUMN))

    def iter_range(
        self,
        source: Source,
        area: BoundingBox,
        start: dt.date,
        end: dt.date,
        *,
        pause: float = DEFAULT_PAUSE,
    ) -> Iterator[AreaChunk]:
        """Hotspots from start to end inclusive, one chunk per request of
        up to 5 days, with pause seconds between requests."""
        for i, (day, count) in enumerate(split_dates(start, end)):
            if i:
                self._sleep(pause)
            chunk = self.chunk(source, area, day, count)
            log.info("%s..%s: %d rows", chunk.start, chunk.end, chunk.row_count)
            yield chunk

    # --- internals ---------------------------------------------------------

    def _area_path(self, source: Source, area: BoundingBox, days: int) -> str:
        return f"/api/area/csv/{self._map_key}/{source.value}/{area.to_path()}/{days}"

    @staticmethod
    def _check_day_range(days: int) -> None:
        if not MIN_DAY_RANGE <= days <= MAX_DAY_RANGE:
            raise ValueError(f"days must be {MIN_DAY_RANGE}..{MAX_DAY_RANGE}")

    @staticmethod
    def _expect_csv(text: str, first_column: str) -> str:
        if not text.split("\n", 1)[0].strip().startswith(first_column):
            raise FirmsResponseError(text)
        return text

    def _get(self, path: str) -> str:
        """GET BASE_URL + path, retrying what may succeed on a retry."""
        url = BASE_URL + path
        for attempt in range(self._retries + 1):
            last = attempt == self._retries
            try:
                with self._open(url, timeout=self._timeout) as resp:
                    return resp.read().decode("utf-8")
            except urllib.error.HTTPError as err:
                with err:
                    body = err.read().decode("utf-8", "replace").strip()
                if err.code not in RETRY_STATUSES or last:
                    raise FirmsHTTPError(err.code, body) from None
                log.warning("HTTP %d, retrying", err.code)
            except (urllib.error.URLError, TimeoutError) as err:
                if last:
                    raise FirmsNetworkError(f"network error: {err}") from None
                log.warning("network error (%s), retrying", err)
            self._sleep(2 ** (attempt + 1))
        raise AssertionError("unreachable")
