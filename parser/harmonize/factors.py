"""Factors that convert MODIS points of a 2-degree square and calendar month into VIIRS Suomi NPP points.

A square trusts its own ratio V / M in proportion to how many MODIS points it has, and borrows the rest from
the cross of its four neighbours, which borrows from the 8-degree block around it, which borrows from the
whole world:

    k = (V + lam * k_cross) / (M + lam)

M and V are the MODIS and Suomi NPP points of the learning years. Longitude wraps around: column 179 is the
neighbour of column 0. Rows do not wrap: a square at a pole has no neighbour beyond it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

LAMBDA: Final[float] = 300.0
ROWS: Final[int] = 90
COLS: Final[int] = 180
BLOCK: Final[int] = 4  # 2-degree squares per side of an 8-degree block


@dataclass
class Levels:
    """The factor of each square and the levels it borrows from. Arrays are (90, 180, *rest), except
    world_factor, which is (*rest)."""

    factor: np.ndarray
    own_share: np.ndarray
    cross_factor: np.ndarray
    cross_modis: np.ndarray
    square8_factor: np.ndarray
    world_factor: np.ndarray


def cross_sum(values: np.ndarray) -> np.ndarray:
    """The sum over the four neighbours of each square: longitude wraps, latitude does not."""
    total = np.roll(values, 1, axis=1) + np.roll(values, -1, axis=1)
    total[1:] += values[:-1]
    total[:-1] += values[1:]
    return total


def _block_sum(values: np.ndarray) -> np.ndarray:
    """The sum over the 8-degree block of each square, spread back over its squares."""
    rows = -(-ROWS // BLOCK) * BLOCK
    padded = np.zeros((rows,) + values.shape[1:])
    padded[:ROWS] = values
    blocks = padded.reshape((rows // BLOCK, BLOCK, COLS // BLOCK, BLOCK) + values.shape[2:]).sum(axis=(1, 3))
    return np.repeat(np.repeat(blocks, BLOCK, axis=0), BLOCK, axis=1)[:ROWS]


def chain(modis: np.ndarray, viirs: np.ndarray, lam: float = LAMBDA) -> Levels:
    """The factors of all squares from the MODIS and Suomi NPP points of the learning years, shaped
    (90, 180, *rest). A month with no MODIS point anywhere in the world has a world factor of 1.0."""
    modis = np.asarray(modis, dtype=float)
    viirs = np.asarray(viirs, dtype=float)
    world_modis, world_viirs = modis.sum(axis=(0, 1)), viirs.sum(axis=(0, 1))
    world = np.where(world_modis > 0, world_viirs / np.where(world_modis > 0, world_modis, 1.0), 1.0)
    square8 = (_block_sum(viirs) + lam * world) / (_block_sum(modis) + lam)
    cross_modis = cross_sum(modis)
    cross = (cross_sum(viirs) + lam * square8) / (cross_modis + lam)
    factor = (viirs + lam * cross) / (modis + lam)
    return Levels(factor=factor, own_share=modis / (modis + lam), cross_factor=cross, cross_modis=cross_modis,
                  square8_factor=square8, world_factor=world)


def chain_without_each_year(modis: np.ndarray, viirs: np.ndarray, lam: float = LAMBDA) -> np.ndarray:
    """For points shaped (90, 180, years, 12), the factors of each year learned on all the other years."""
    modis = np.asarray(modis, dtype=float)
    viirs = np.asarray(viirs, dtype=float)
    rest_modis = modis.sum(axis=2, keepdims=True) - modis
    rest_viirs = viirs.sum(axis=2, keepdims=True) - viirs
    return chain(rest_modis, rest_viirs, lam).factor
