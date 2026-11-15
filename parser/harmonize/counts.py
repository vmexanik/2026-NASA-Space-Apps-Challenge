"""Fire points per satellite, 2-degree square, year and calendar month, read from the FIRMS yearly archives.

MODIS and Suomi NPP are counted only on the days when both satellites of the pair gave points, so a day on
which one of them was silent does not shift the factor. The same holds for NOAA-20 and Suomi NPP, whose counts
give the error of NOAA-20, and for Terra and Aqua in the MODIS-only years. Only vegetation fires (type 0) are
counted, with no confidence filter. The counts are cached, keyed by the archives they come from and the shared
days.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path
from typing import Final

import numpy as np

from .sources import Member, archive_members, country_of, read_member

TRAIN_YEARS: Final[tuple[int, ...]] = tuple(range(2012, 2023))
HIST_YEARS: Final[tuple[int, ...]] = tuple(range(2003, 2012))
NOAA20_YEARS: Final[tuple[int, ...]] = tuple(range(2018, 2026))
COUNTRIES: Final[tuple[str, ...]] = ("Ukraine", "Brazil", "Australia")
COUNTS_FORMAT: Final[int] = 2
PAIRS: Final[tuple[str, ...]] = ("aqua", "terra")
SAT_OF: Final[dict[str, int]] = {"terra": 1, "aqua": 2, "snpp": 3, "noaa20": 4}
EPOCH64: Final[np.datetime64] = np.datetime64("2000-01-01")
SQUARE: Final[tuple[int, int]] = (90, 180)
HALF: Final[tuple[int, int]] = (360, 720)

log = logging.getLogger(__name__)


@dataclass
class Counts:
    """Points of the learning years, of the MODIS-only years and of NOAA-20 against Suomi NPP. Year axes follow
    `years` (learning), HIST_YEARS (hist) or NOAA20_YEARS (viirs); the month axis is 0..11.

    modis      'aqua'/'terra' -> (90, 180, years, 12), days shared with Suomi NPP only
    snpp       pair 'aqua'/'terra' -> (90, 180, years, 12), Suomi NPP on the days shared with that satellite
    modis_half, snpp_half   the same on 0.5-degree cells, (360, 720, years, 12)
    hist       'aqua'/'terra' -> (90, 180, len(HIST_YEARS), 12), days of 2003-2011 shared by Terra and Aqua
    country    country -> {'aqua', 'terra', 'snpp_aqua', 'snpp_terra'} -> (90, 180, years, 12)
    viirs      'noaa20'/'snpp' -> (90, 180, len(NOAA20_YEARS), 12), days shared by NOAA-20 and Suomi NPP
    viirs_half the same on 0.5-degree cells, (360, 720, len(NOAA20_YEARS), 12)
    """

    years: tuple[int, ...]
    modis: dict[str, np.ndarray]
    snpp: dict[str, np.ndarray]
    modis_half: dict[str, np.ndarray]
    snpp_half: dict[str, np.ndarray]
    hist: dict[str, np.ndarray]
    country: dict[str, dict[str, np.ndarray]]
    viirs: dict[str, np.ndarray]
    viirs_half: dict[str, np.ndarray]


def common_days(days: dict[str, np.ndarray], a: str, b: str) -> np.ndarray:
    """The days on which both satellites gave points."""
    length = max(len(days.get(a, ())), len(days.get(b, ())))
    first, second = np.zeros(length, dtype=bool), np.zeros(length, dtype=bool)
    first[:len(days.get(a, ()))] = days.get(a, np.zeros(0, dtype=bool))
    second[:len(days.get(b, ()))] = days.get(b, np.zeros(0, dtype=bool))
    return first & second


_COMMON: dict[str, np.ndarray] = {}


def _init_worker(common: dict[str, np.ndarray]) -> None:
    global _COMMON
    _COMMON = common


def _on(mask: np.ndarray, day: np.ndarray) -> np.ndarray:
    """mask[day], False beyond the end of the mask."""
    inside = day < len(mask)
    out = np.zeros(len(day), dtype=bool)
    out[inside] = mask[day[inside]]
    return out


def _count_member(task: tuple[Member, str]) -> list[tuple[tuple[str, ...], np.ndarray, np.ndarray]]:
    """Flat indices and counts of one file's points in every array of Counts they belong to."""
    member, sensor = task
    rows = read_member(member)
    months = (EPOCH64 + rows.day.astype("timedelta64[D]")).astype("datetime64[M]").astype(np.int64)
    year, month = months // 12 + 1970, months % 12
    row2, col2 = rows.cell2.astype(np.int64) // SQUARE[1], rows.cell2.astype(np.int64) % SQUARE[1]
    iy, ix = rows.cell.astype(np.int64) // 1440, rows.cell.astype(np.int64) % 1440
    country = country_of(member)
    fire = rows.type == 0
    train = (year >= TRAIN_YEARS[0]) & (year <= TRAIN_YEARS[-1])
    pair_years = (year >= NOAA20_YEARS[0]) & (year <= NOAA20_YEARS[-1])
    out = []

    def add(target: tuple[str, ...], sel: np.ndarray, grid: tuple[int, int], r: np.ndarray, c: np.ndarray,
            y: np.ndarray, years: int) -> None:
        if sel.any():
            flat = np.ravel_multi_index((r[sel], c[sel], y[sel], month[sel]), grid + (years, 12))
            keys, n = np.unique(flat, return_counts=True)
            out.append((target, keys, n))

    if sensor == "modis":
        for sat in PAIRS:
            own = fire & (rows.sat == SAT_OF[sat])
            shared = own & train & _on(_COMMON[sat], rows.day)
            add(("modis", sat), shared, SQUARE, row2, col2, year - TRAIN_YEARS[0], len(TRAIN_YEARS))
            add(("modis_half", sat), shared, HALF, iy // 2, ix // 2, year - TRAIN_YEARS[0], len(TRAIN_YEARS))
            if country in COUNTRIES:
                add(("country", country, sat), shared, SQUARE, row2, col2, year - TRAIN_YEARS[0], len(TRAIN_YEARS))
            old = own & (year >= HIST_YEARS[0]) & (year <= HIST_YEARS[-1]) & _on(_COMMON["terra_aqua"], rows.day)
            add(("hist", sat), old, SQUARE, row2, col2, year - HIST_YEARS[0], len(HIST_YEARS))
    elif sensor == "viirs-jpss1":
        noaa20 = fire & (rows.sat == SAT_OF["noaa20"]) & pair_years & _on(_COMMON["noaa20"], rows.day)
        add(("viirs", "noaa20"), noaa20, SQUARE, row2, col2, year - NOAA20_YEARS[0], len(NOAA20_YEARS))
        add(("viirs_half", "noaa20"), noaa20, HALF, iy // 2, ix // 2, year - NOAA20_YEARS[0], len(NOAA20_YEARS))
    else:
        snpp = fire & (rows.sat == SAT_OF["snpp"]) & train
        for pair in PAIRS:
            shared = snpp & _on(_COMMON[pair], rows.day)
            add(("snpp", pair), shared, SQUARE, row2, col2, year - TRAIN_YEARS[0], len(TRAIN_YEARS))
            add(("snpp_half", pair), shared, HALF, iy // 2, ix // 2, year - TRAIN_YEARS[0], len(TRAIN_YEARS))
            if country in COUNTRIES:
                add(("country", country, "snpp_" + pair), shared, SQUARE, row2, col2, year - TRAIN_YEARS[0],
                    len(TRAIN_YEARS))
        with_noaa20 = fire & (rows.sat == SAT_OF["snpp"]) & pair_years & _on(_COMMON["noaa20"], rows.day)
        add(("viirs", "snpp"), with_noaa20, SQUARE, row2, col2, year - NOAA20_YEARS[0], len(NOAA20_YEARS))
        add(("viirs_half", "snpp"), with_noaa20, HALF, iy // 2, ix // 2, year - NOAA20_YEARS[0], len(NOAA20_YEARS))
    return out


def _empty() -> Counts:
    years = len(TRAIN_YEARS)
    square = lambda n: np.zeros(SQUARE + (n, 12))
    return Counts(
        years=TRAIN_YEARS,
        modis={s: square(years) for s in PAIRS}, snpp={s: square(years) for s in PAIRS},
        modis_half={s: np.zeros(HALF + (years, 12), dtype=np.float32) for s in PAIRS},
        snpp_half={s: np.zeros(HALF + (years, 12), dtype=np.float32) for s in PAIRS},
        hist={s: square(len(HIST_YEARS)) for s in PAIRS},
        country={c: {k: square(years) for k in ("aqua", "terra", "snpp_aqua", "snpp_terra")} for c in COUNTRIES},
        viirs={s: square(len(NOAA20_YEARS)) for s in ("noaa20", "snpp")},
        viirs_half={s: np.zeros(HALF + (len(NOAA20_YEARS), 12), dtype=np.float32) for s in ("noaa20", "snpp")})


def _array(counts: Counts, target: tuple[str, ...]) -> np.ndarray:
    if target[0] == "country":
        return counts.country[target[1]][target[2]]
    return getattr(counts, target[0])[target[1]]


def _arrays(counts: Counts) -> dict[str, np.ndarray]:
    named = {f"{field}__{sat}": arr
             for field in ("modis", "snpp", "modis_half", "snpp_half", "hist", "viirs", "viirs_half")
             for sat, arr in getattr(counts, field).items()}
    named.update({f"country__{c}__{k}": arr for c, parts in counts.country.items() for k, arr in parts.items()})
    return named


def _cache_key(tasks: list[tuple[Member, str]], common: dict[str, np.ndarray]) -> str:
    digest = hashlib.sha256(f"format {COUNTS_FORMAT}".encode())
    for path in sorted({m.path for m, _ in tasks}):
        stat = path.stat()
        digest.update(f"{path.name} {stat.st_size} {stat.st_mtime_ns}".encode())
    for name in sorted(common):
        digest.update(np.packbits(common[name]).tobytes())
    return digest.hexdigest()[:20]


def build_counts(archive_dir: Path, days: dict[str, np.ndarray], jobs: int, cache_dir: Path | None) -> Counts:
    """Count the points of the MODIS archives 2003-2022, the Suomi NPP archives 2012-2025 and the NOAA-20
    archives 2018-2025."""
    snpp_years = tuple(sorted(set(TRAIN_YEARS) | set(NOAA20_YEARS)))
    tasks = ([(m, "modis") for m in archive_members(archive_dir, "modis", HIST_YEARS + TRAIN_YEARS)]
             + [(m, "viirs-snpp") for m in archive_members(archive_dir, "viirs-snpp", snpp_years)]
             + [(m, "viirs-jpss1") for m in archive_members(archive_dir, "viirs-jpss1", NOAA20_YEARS)])
    common = {pair: common_days(days, pair, "snpp") for pair in PAIRS}
    common["noaa20"] = common_days(days, "noaa20", "snpp")
    common["terra_aqua"] = common_days(days, "terra", "aqua")
    cache = cache_dir / f"counts-{_cache_key(tasks, common)}.npz" if cache_dir is not None and tasks else None
    counts = _empty()
    if cache is not None and cache.exists():
        log.info("counts from cache %s", cache)
        with np.load(cache) as saved:
            for name, arr in _arrays(counts).items():
                arr[...] = saved[name]
        return counts
    with Pool(max(1, jobs), initializer=_init_worker, initargs=(common,)) as pool:
        for parts in pool.imap_unordered(_count_member, tasks, chunksize=4):
            for target, keys, n in parts:
                np.add.at(_array(counts, target).reshape(-1), keys, n)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, **_arrays(counts))
        log.info("counts cached in %s", cache)
    return counts
