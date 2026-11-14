"""The 0.25-degree grid of the web database, and the 2- and 8-degree squares made of its cells.

Coordinates are whole 1e-5 degrees (lat_e5 = degrees x 100 000), the precision of the FIRMS files, so
that a point on a cell border falls in the same cell here and in SQL. Every function takes (lat, lon) in
this order, as FIRMS writes its columns.

- A cell is 0.25 x 0.25 degrees: column ix 0..1439 eastwards from -180, row iy 0..719 northwards from -90,
  cell_id = iy * 1440 + ix. A point on lon = 180 or lat = 90 belongs to the last column or row.
- A 2-degree square, the square of a harmonization factor, is 8 x 8 cells: 180 columns, 90 rows.
- An 8-degree square is 4 x 4 two-degree squares: 45 columns, 23 rows; the northern row is 4 degrees high.

The SQL functions of the firms schema use the same formulas. tests/data/grid_points.json holds reference
points with their ids.
"""

from __future__ import annotations

from typing import Final

_STEP_E5: Final[int] = 25_000  # 0.25 degree in 1e-5 degrees
_STEP: Final[float] = 0.25
_COLUMNS: Final[int] = 1440
_ROWS: Final[int] = 720
_CELLS_PER_SQUARE2: Final[int] = 8  # cells along a side of a 2-degree square
_COLUMNS2: Final[int] = 180
_SQUARES2_PER_SQUARE8: Final[int] = 4  # 2-degree squares along a side of an 8-degree square
_COLUMNS8: Final[int] = 45


def cell_id_e5(lat_e5: int, lon_e5: int) -> int:
    """The cell of a point given in whole 1e-5 degrees.

    Raises ValueError outside latitude -90..90 and longitude -180..180, where any number would be another
    cell's.
    """
    if not (-9_000_000 <= lat_e5 <= 9_000_000 and -18_000_000 <= lon_e5 <= 18_000_000):
        raise ValueError(f"lat_e5 {lat_e5}, lon_e5 {lon_e5} is off the globe")
    ix = min((lon_e5 + 18_000_000) // _STEP_E5, _COLUMNS - 1)
    iy = min((lat_e5 + 9_000_000) // _STEP_E5, _ROWS - 1)
    return iy * _COLUMNS + ix


def cell_id(lat: float, lon: float) -> int:
    """The cell of a point given in degrees.

    The degrees are rounded to whole 1e-5 degrees first, so a value read from a FIRMS file, which has at
    most five decimals, gets the same cell as its exact text does in cell_id_e5.
    """
    return cell_id_e5(round(lat * 100_000), round(lon * 100_000))


def cell2_id(cell_id: int) -> int:
    """The 2-degree square of a cell: row * 180 + column, from the south-west corner."""
    iy, ix = divmod(cell_id, _COLUMNS)
    return (iy // _CELLS_PER_SQUARE2) * _COLUMNS2 + ix // _CELLS_PER_SQUARE2


def cell8_id(cell2_id: int) -> int:
    """The 8-degree square of a 2-degree square: row * 45 + column, from the south-west corner."""
    row, column = divmod(cell2_id, _COLUMNS2)
    return (row // _SQUARES2_PER_SQUARE8) * _COLUMNS8 + column // _SQUARES2_PER_SQUARE8


def cell_bounds(cell_id: int) -> tuple[float, float, float, float]:
    """The west, south, east and north edges of a cell in degrees, exact in binary floating point."""
    iy, ix = divmod(cell_id, _COLUMNS)
    west, south = ix * _STEP - 180.0, iy * _STEP - 90.0
    return west, south, west + _STEP, south + _STEP
