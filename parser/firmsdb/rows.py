"""One row of a FIRMS CSV file as a row of the firms.hotspot table.

parse_row reads every form of the FIRMS files: the yearly archive, the SP and NRT files of the area API,
MODIS and VIIRS. docs/data-standard.md is its specification. A value it does not know raises ValueError,
so that a change in the FIRMS files stops the export instead of slipping into the database.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Final, NamedTuple

from firms.grid import cell_id_e5

#: The firms.satellite id of each FIRMS `satellite` value and of each code.
SATELLITES: Final[dict[str, int]] = {
    "Terra": 1, "T": 1, "terra": 1,
    "Aqua": 2, "A": 2, "aqua": 2,
    "N": 3, "snpp": 3,
    "N20": 4, "noaa20": 4,
    "N21": 5, "noaa21": 5,
}

#: The code of each satellite id.
CODES: Final[dict[int, str]] = {1: "terra", 2: "aqua", 3: "snpp", 4: "noaa20", 5: "noaa21"}

# The values of the FIRMS `satellite` column: SATELLITES without the codes, which no FIRMS file holds.
_FIRMS_SATELLITES: Final[dict[str, int]] = {
    value: sid for value, sid in SATELLITES.items() if value not in CODES.values()}
_MODIS: Final[frozenset[int]] = frozenset({1, 2})  # Terra and Aqua carry MODIS, the others VIIRS
# Degrees as FIRMS writes them: 48.74919, -0.5, 30, and 4e-05 for a value nearer 0 than 0.0001.
_DEGREES: Final[re.Pattern[str]] = re.compile(r"(-?)([0-9]+)(?:\.([0-9]+))?(?:e([-+]?[0-9]{1,3}))?")
# A number as FIRMS writes it in frp, brightness, scan and track: 288, 28.4, and 5e-05 near zero.
_NUMBER: Final[re.Pattern[str]] = re.compile(r"-?[0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)?")
_DAYNIGHT: Final[dict[str, bool]] = {"D": True, "N": False}
_VIIRS_CLASSES: Final[frozenset[str]] = frozenset({"l", "n", "h"})
_TYPES: Final[dict[str, int]] = {"0": 0, "1": 1, "2": 2, "3": 3}
_OFFSHORE: Final[int] = 3  # the FIRMS type of a detection over water


class Detection(NamedTuple):
    """One detection as a row of firms.hotspot, in the order of its columns, then the FIRMS type."""

    acq_date: dt.date  # UTC
    acq_time: int  # HHMM UTC: 49 is 00:49
    satellite: int  # firms.satellite id
    cell_id: int  # the 0.25-degree cell of firms.grid
    lat_e5: int  # degrees x 100 000
    lon_e5: int
    frp: float  # MW
    brightness: float  # K: brightness of MODIS, bright_ti4 of VIIRS
    brightness_2: float  # K: bright_t31 of MODIS, bright_ti5 of VIIRS
    scan: float  # km
    track: float  # km
    conf_class: str  # l, n or h
    conf_pct: int | None  # the MODIS confidence 0..100; None for VIIRS, which gives a class only
    is_day: bool
    is_nrt: bool
    batch_id: int  # firms.load_batch id of the file
    type: int | None  # FIRMS type 0..3; None for an NRT row, which has none


def to_e5(text: str) -> int:
    """Degrees written as text, read exactly into whole 1e-5 degrees: "48.74919" gives 4874919.

    Takes an optional minus, digits and up to five decimals, or the exponent form FIRMS writes for a value
    nearer zero than 0.0001 ("4e-05" gives 4). Raises ValueError for any other text and for more than five
    decimal places in either form.
    """
    match = _DEGREES.fullmatch(text)
    if match is None:
        raise ValueError(f"{text!r} is not degrees")
    minus, whole, fraction, exponent = match.groups()
    fraction = fraction or ""
    places = len(fraction) - int(exponent or "0")
    if places > 5:
        raise ValueError(f"{text!r} has more than 5 decimals")
    value = int(whole + fraction) * 10 ** (5 - places)
    return -value if minus else value


def parse_row(row: dict[str, str], *, is_nrt: bool, batch_id: int) -> Detection:
    """The detection of one FIRMS CSV row, keyed by the column names of the file's header.

    is_nrt says whether the file is NRT; batch_id is the file's firms.load_batch id. The satellite gives
    the instrument and so the columns: brightness and bright_t31 for MODIS, bright_ti4 and bright_ti5 for
    VIIRS. A row of an archive or SP file must have a type; an NRT row may lack it.

    Raises ValueError for a value it does not know, for a missing column and for a row with fewer fields
    than the header, whose missing fields csv.DictReader fills with None.
    """
    if None in row.values():
        raise ValueError("the row has fewer fields than the header")
    try:
        satellite = _FIRMS_SATELLITES.get(row["satellite"])
        if satellite is None:
            raise ValueError(f"satellite {row['satellite']!r} is not a FIRMS satellite value")
        if satellite in _MODIS:
            brightness, brightness_2 = "brightness", "bright_t31"
            conf_class, conf_pct = _modis_confidence(row["confidence"])
        else:
            brightness, brightness_2 = "bright_ti4", "bright_ti5"
            conf_class, conf_pct = _viirs_confidence(row["confidence"]), None
        is_day = _DAYNIGHT.get(row["daynight"])
        if is_day is None:
            raise ValueError(f"daynight {row['daynight']!r} is not D or N")
        type_text = row.get("type") if is_nrt else row["type"]
        hotspot_type = None if type_text is None else _TYPES.get(type_text)
        if type_text is not None and hotspot_type is None:
            raise ValueError(f"type {type_text!r} is not 0..3")
        lat_e5, lon_e5 = to_e5(row["latitude"]), to_e5(row["longitude"])
        return Detection(
            acq_date=dt.date.fromisoformat(row["acq_date"]),
            acq_time=_acq_time(row["acq_time"]),
            satellite=satellite,
            cell_id=cell_id_e5(lat_e5, lon_e5),
            lat_e5=lat_e5,
            lon_e5=lon_e5,
            frp=_number(row, "frp"),
            brightness=_number(row, brightness),
            brightness_2=_number(row, brightness_2),
            scan=_number(row, "scan"),
            track=_number(row, "track"),
            conf_class=conf_class,
            conf_pct=conf_pct,
            is_day=is_day,
            is_nrt=is_nrt,
            batch_id=batch_id,
            type=hotspot_type,
        )
    except KeyError as err:
        raise ValueError(f"the row has no {err.args[0]} column") from None


def static_type(d: Detection, in_footprint: bool) -> int | None:
    """The type a detection is set aside with in firms.hotspot_static, or None for a fire.

    in_footprint says whether the detection's cell is in firms.archive_cell, the cells where the archive
    has a point of any type; it is true for every archive row, since those rows make the footprint.
    FIRMS's own type 1, 2 or 3 is kept. A fire, of type 0 or an NRT row without type, outside the
    footprint becomes type 3: the archive's country files hold no open-sea points and the API files do.
    """
    if d.type:  # 1, 2 or 3; type 0 and None are fires
        return d.type
    return None if in_footprint else _OFFSHORE


def _acq_time(text: str) -> int:
    """HHMM UTC as a number. The API files drop the leading zeros ("28" is 00:28), so the text is padded
    to four digits before the hours and minutes are read."""
    if not (len(text) <= 4 and text.isascii() and text.isdigit()):
        raise ValueError(f"acq_time {text!r} is not HHMM")
    hhmm = text.zfill(4)
    hour, minute = int(hhmm[:2]), int(hhmm[2:])
    if hour > 23 or minute > 59:
        raise ValueError(f"acq_time {text!r} is not HHMM")
    return hour * 100 + minute


def _modis_confidence(text: str) -> tuple[str, int]:
    """The class and percent of a MODIS confidence: l below 30, n below 80, h from 80 (Table 11 of the
    MODIS user's guide)."""
    if not (text.isascii() and text.isdigit()) or int(text) > 100:
        raise ValueError(f"MODIS confidence {text!r} is not 0..100")
    pct = int(text)
    return ("l" if pct < 30 else "n" if pct < 80 else "h"), pct


def _viirs_confidence(text: str) -> str:
    """The class of a VIIRS confidence, which the files write as l, n or h."""
    if text not in _VIIRS_CLASSES:
        raise ValueError(f"VIIRS confidence {text!r} is not l, n or h")
    return text


def _number(row: dict[str, str], column: str) -> float:
    text = row[column]
    if _NUMBER.fullmatch(text) is None:  # float() alone takes nan, inf, spaces and 2_8.4
        raise ValueError(f"{column} {text!r} is not a number")
    return float(text)
