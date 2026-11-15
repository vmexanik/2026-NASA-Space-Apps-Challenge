"""Client of the NASA FIRMS API (active fire hotspots).

    from datetime import date
    from pathlib import Path
    from firms import BoundingBox, FirmsClient, Source

    client = FirmsClient.from_env(Path(".env"))
    chunk = client.latest(Source.VIIRS_NOAA20_NRT, BoundingBox(22, 44, 40.5, 52.5))
    print(chunk.row_count, chunk.rows()[:1])
"""

from .client import FirmsClient, Opener, split_dates
from .config import load_map_key
from .constants import (
    BASE_URL,
    DEFAULT_PAUSE,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    MAP_KEY_ENV,
    MAX_DAY_RANGE,
    MIN_DAY_RANGE,
    Source,
)
from .csv_utils import merge_csv
from .errors import (
    FirmsConfigError,
    FirmsError,
    FirmsHTTPError,
    FirmsNetworkError,
    FirmsResponseError,
)
from .models import WORLD, AreaChunk, BoundingBox, DataAvailability, KeyStatus

__all__ = [
    "BASE_URL",
    "DEFAULT_PAUSE",
    "DEFAULT_RETRIES",
    "DEFAULT_TIMEOUT",
    "MAP_KEY_ENV",
    "MAX_DAY_RANGE",
    "MIN_DAY_RANGE",
    "WORLD",
    "AreaChunk",
    "BoundingBox",
    "DataAvailability",
    "FirmsClient",
    "FirmsConfigError",
    "FirmsError",
    "FirmsHTTPError",
    "FirmsNetworkError",
    "FirmsResponseError",
    "KeyStatus",
    "Opener",
    "Source",
    "load_map_key",
    "merge_csv",
    "split_dates",
]
