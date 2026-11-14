"""Values the FIRMS client takes and returns."""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """A rectangle on the map in degrees: west, south, east, north.

    FIRMS does not take a box that crosses the 180th meridian; split such
    an area into two boxes.
    """

    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not -180 <= self.west < self.east <= 180:
            raise ValueError("need -180 <= west < east <= 180")
        if not -90 <= self.south < self.north <= 90:
            raise ValueError("need -90 <= south < north <= 90")

    @classmethod
    def parse(cls, text: str) -> BoundingBox:
        """Build a box from 'world' or 'west,south,east,north'."""
        if text.strip().lower() == "world":
            return WORLD
        parts = text.split(",")
        if len(parts) != 4:
            raise ValueError("area must be 'world' or west,south,east,north")
        west, south, east, north = (float(part) for part in parts)
        return cls(west, south, east, north)

    def to_path(self) -> str:
        """The AREA_COORDINATES segment of an API URL."""
        if self == WORLD:
            return "world"
        return ",".join(
            f"{value:g}" for value in (self.west, self.south, self.east, self.north)
        )


#: The whole globe; the API takes it as 'world'.
WORLD: Final[BoundingBox] = BoundingBox(-180.0, -90.0, 180.0, 90.0)


@dataclass(frozen=True, slots=True)
class KeyStatus:
    """How much of the MAP_KEY's rate limit is used.

    A key may spend transaction_limit transactions per
    transaction_interval. A large request costs more than one: a 5-day
    request for the whole world cost about 165.
    """

    transaction_limit: int
    current_transactions: int
    transaction_interval: str

    @property
    def remaining(self) -> int:
        """Transactions left in the current interval."""
        return max(self.transaction_limit - self.current_transactions, 0)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> KeyStatus:
        """Build the status from the mapkey_status JSON answer."""
        return cls(
            transaction_limit=int(data["transaction_limit"]),
            current_transactions=int(data["current_transactions"]),
            transaction_interval=str(data["transaction_interval"]),
        )


@dataclass(frozen=True, slots=True)
class DataAvailability:
    """The dates one data set covers.

    data_id is a plain string: besides the Source values FIRMS lists
    data sets the area API does not serve, such as BA_MODIS (burned area).
    """

    data_id: str
    min_date: dt.date
    max_date: dt.date


@dataclass(frozen=True, slots=True)
class AreaChunk:
    """The answer to one area request: CSV of the hotspots of day_count
    days starting at start (UTC dates)."""

    start: dt.date
    day_count: int
    csv_text: str

    @property
    def end(self) -> dt.date:
        """The last day of the chunk, inclusive."""
        return self.start + dt.timedelta(days=self.day_count - 1)

    @property
    def header(self) -> str:
        """The CSV header line."""
        return self.csv_text.split("\n", 1)[0].strip()

    @property
    def row_count(self) -> int:
        """Number of hotspots, the header not counted."""
        return max(len(self.csv_text.strip().splitlines()) - 1, 0)

    def rows(self) -> list[dict[str, str]]:
        """The hotspots as dicts keyed by the CSV column names."""
        return list(csv.DictReader(io.StringIO(self.csv_text)))
