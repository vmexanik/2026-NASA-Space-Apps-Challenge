"""Fixed values of the FIRMS API: URLs, limits and data sources."""

from enum import StrEnum
from typing import Final

BASE_URL: Final[str] = "https://firms.modaps.eosdis.nasa.gov"

#: The area API returns 1..MAX_DAY_RANGE days per request.
MIN_DAY_RANGE: Final[int] = 1
MAX_DAY_RANGE: Final[int] = 5

#: Environment variable and .env entry that hold the MAP_KEY.
MAP_KEY_ENV: Final[str] = "FIRMS_MAP_KEY"

#: Socket timeout in seconds. A 5-day request for the whole world took
#: about five minutes to finish, so the server can be slow to answer.
DEFAULT_TIMEOUT: Final[float] = 300.0

#: Extra attempts after a failed request that may succeed on a retry.
DEFAULT_RETRIES: Final[int] = 3

#: Seconds to wait between the requests of a date range.
DEFAULT_PAUSE: Final[float] = 1.0

#: HTTP codes worth a retry: rate limit and server-side failures.
RETRY_STATUSES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})


class Source(StrEnum):
    """Data source of the area and data availability APIs.

    NRT (near real time) covers roughly the last few months and arrives
    within hours. SP (standard processing) is the science-quality archive;
    it replaces NRT with a lag of a few months. The exact dates of each
    source come from FirmsClient.availability().
    """

    #: Geostationary satellites (GOES; Meteosat over Europe and Africa).
    GOES_NRT = "GOES_NRT"
    #: Landsat 30 m; US and Canada only.
    LANDSAT_NRT = "LANDSAT_NRT"
    #: MODIS 1 km (Terra and Aqua).
    MODIS_NRT = "MODIS_NRT"
    MODIS_SP = "MODIS_SP"
    #: VIIRS 375 m on NOAA-20.
    VIIRS_NOAA20_NRT = "VIIRS_NOAA20_NRT"
    VIIRS_NOAA20_SP = "VIIRS_NOAA20_SP"
    #: VIIRS 375 m on NOAA-21.
    VIIRS_NOAA21_NRT = "VIIRS_NOAA21_NRT"
    VIIRS_NOAA21_SP = "VIIRS_NOAA21_SP"
    #: VIIRS 375 m on Suomi NPP; no new data after 2026-11-02.
    VIIRS_SNPP_NRT = "VIIRS_SNPP_NRT"
    VIIRS_SNPP_SP = "VIIRS_SNPP_SP"

    @property
    def is_near_real_time(self) -> bool:
        """True for an NRT source, False for a standard processing one."""
        return self.value.endswith("_NRT")
