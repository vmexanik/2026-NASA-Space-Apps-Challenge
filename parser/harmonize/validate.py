"""The check of a method version: every learning year guessed with factors learned on the other years.

The guesses are compared with the real Suomi NPP points on grid-aligned areas of 0.5, 2 and 8 degrees. The
same guesses give the error table that the application shows next to every harmonized number.
"""

from __future__ import annotations

import html
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from .counts import HIST_YEARS, Counts
from .factors import chain_without_each_year, cross_sum

N_MIN: Final[tuple[int, ...]] = (1, 3, 10, 30, 100, 300, 1000)
EDGES: Final[tuple[float, ...]] = (0.5, 0.8, 1.25, 2.0)
MIN_ACTUAL: Final[int] = 100
SPARSE: Final[int] = 100


@dataclass
class AreaSet:
    """Guessed and real Suomi NPP points of areas and the points of the satellite they are guessed from (MODIS, or
    NOAA-20), each shaped (areas, years, 12). `sparse` marks area-months whose square has fewer than 100 MODIS
    points in the other years."""

    pred: np.ndarray
    actual: np.ndarray
    n_points: np.ndarray
    sparse: np.ndarray | None


def _blocks(values: np.ndarray, size: int) -> np.ndarray:
    """Sums over blocks of size x size cells of a (rows, cols, ...) array, rows padded with zeros."""
    rows = -(-values.shape[0] // size) * size
    padded = np.zeros((rows,) + values.shape[1:], dtype=values.dtype)
    padded[:values.shape[0]] = values
    shape = (rows // size, size, values.shape[1] // size, size) + values.shape[2:]
    return padded.reshape(shape).sum(axis=(1, 3))


def _flat(values: np.ndarray) -> np.ndarray:
    return values.reshape((-1,) + values.shape[2:])


def predictions(counts: Counts, satellite: str, years: Sequence[int], lam: float) -> dict[str, AreaSet]:
    """Each of `years` guessed with the factors learned without it, on areas of 0.5, 2 and 8 degrees."""
    idx = [counts.years.index(y) for y in years]
    modis = counts.modis[satellite][:, :, idx, :]
    viirs = counts.snpp[satellite][:, :, idx, :]
    factors = chain_without_each_year(modis, viirs, lam)
    rest = modis.sum(axis=2, keepdims=True) - modis
    pred2 = factors * modis
    half_factors = np.repeat(np.repeat(factors, 4, axis=0), 4, axis=1).astype(np.float32)
    modis_half = counts.modis_half[satellite][:, :, idx, :]
    return {
        "0.5": AreaSet(_flat(half_factors * modis_half), _flat(counts.snpp_half[satellite][:, :, idx, :]),
                       _flat(modis_half), None),
        "2": AreaSet(_flat(pred2), _flat(viirs), _flat(modis), _flat(rest < SPARSE)),
        "8": AreaSet(_flat(_blocks(pred2, 4)), _flat(_blocks(viirs, 4)), _flat(_blocks(modis, 4)), None),
    }


def _median_error(pred: np.ndarray, actual: np.ndarray, sel: np.ndarray) -> float | None:
    return float(np.median(np.abs(pred[sel] / actual[sel] - 1))) if sel.any() else None


def metrics(area: AreaSet) -> dict[str, object]:
    """error: median |guess / real - 1| over area-months with 100+ real points; calendar: share of area-months
    whose colour class (month / mean of that calendar month, cut at EDGES) matches, over calendar months
    averaging 100+ points; error_sparse: the error in sparse squares; yearly_ratio: guess / real per year."""
    pred, actual = area.pred.astype(float), area.actual.astype(float)
    big = actual >= MIN_ACTUAL
    norm = actual.mean(axis=1, keepdims=True)
    usual = np.broadcast_to(norm >= MIN_ACTUAL, actual.shape)
    with np.errstate(divide="ignore", invalid="ignore"):
        same = np.digitize(pred / norm, EDGES) == np.digitize(actual / norm, EDGES)
    yearly = [float(pred[:, y].sum() / actual[:, y].sum()) if actual[:, y].sum() else None
              for y in range(actual.shape[1])]
    return {
        "error": _median_error(pred, actual, big),
        "calendar": float(same[usual].mean()) if usual.any() else None,
        "error_sparse": _median_error(pred, actual, big & area.sparse) if area.sparse is not None else None,
        "yearly_ratio": yearly,
    }


def error_rows(sets: dict[str, AreaSet], satellite: str, source: str = "modis") -> list[tuple[str, str, int, float, int]]:
    """Rows (source, satellite, n_min, rel_error, samples): rel_error is the median of |real - guess| / guess
    over the area-months of all given area sizes whose points of the converted satellite lie in [n_min, next n_min)."""
    pred = np.concatenate([a.pred.ravel() for a in sets.values()]).astype(float)
    actual = np.concatenate([a.actual.ravel() for a in sets.values()]).astype(float)
    n = np.concatenate([a.n_points.ravel() for a in sets.values()]).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.abs(actual - pred) / pred
    rows = []
    for i, n_min in enumerate(N_MIN):
        upper = N_MIN[i + 1] if i + 1 < len(N_MIN) else np.inf
        sel = (n >= n_min) & (n < upper) & (pred > 0)
        if sel.any():
            rows.append((source, satellite, n_min, float(np.median(rel[sel])), int(sel.sum())))
    return rows


def compare_chains(counts: Counts, country: str, lam: float) -> tuple[float, float]:
    """The error on the country's 2-degree squares (Aqua, every learning year guessed without itself) of the
    chain the topic tested (own -> cross -> country factor, country data only) and of the world chain."""
    modis_c = counts.country[country]["aqua"].astype(float)
    viirs_c = counts.country[country]["snpp_aqua"].astype(float)
    rest_m = modis_c.sum(axis=2, keepdims=True) - modis_c
    rest_v = viirs_c.sum(axis=2, keepdims=True) - viirs_c
    tot_m, tot_v = rest_m.sum(axis=(0, 1)), rest_v.sum(axis=(0, 1))
    region = np.where(tot_m > 0, tot_v / np.where(tot_m > 0, tot_m, 1.0), 1.0)
    cross = (cross_sum(rest_v) + lam * region) / (cross_sum(rest_m) + lam)
    old = (rest_v + lam * cross) / (rest_m + lam)
    new = chain_without_each_year(counts.modis["aqua"], counts.snpp["aqua"], lam)
    big = viirs_c >= MIN_ACTUAL
    return (_median_error(old * modis_c, viirs_c, big) or 0.0, _median_error(new * modis_c, viirs_c, big) or 0.0)


def noaa20_sets(counts: Counts) -> dict[str, AreaSet]:
    """NOAA-20 points taken as they are, with weight 1, against the Suomi NPP points of the same days, on areas of
    0.5, 2 and 8 degrees. Nothing is learned, so no year is left out."""
    noaa20, snpp = counts.viirs["noaa20"], counts.viirs["snpp"]
    noaa20_half, snpp_half = counts.viirs_half["noaa20"], counts.viirs_half["snpp"]
    return {
        "0.5": AreaSet(_flat(noaa20_half), _flat(snpp_half), _flat(noaa20_half), None),
        "2": AreaSet(_flat(noaa20), _flat(snpp), _flat(noaa20), None),
        "8": AreaSet(_flat(_blocks(noaa20, 4)), _flat(_blocks(snpp, 4)), _flat(_blocks(noaa20, 4)), None),
    }


def _hist_totals(counts: Counts, factors: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """The world total harmonized from Terra and from Aqua in each MODIS-only year, on the days both gave points."""
    return {s: (factors[s][:, :, None, :] * counts.hist[s]).sum(axis=(0, 1, 3)) for s in ("terra", "aqua")}


def terra_aqua_agreement(counts: Counts, factors: dict[str, np.ndarray]) -> dict[int, float]:
    """For each MODIS-only year, the world total harmonized from Terra over the one from Aqua, minus 1."""
    totals = _hist_totals(counts, factors)
    return {year: float(totals["terra"][i] / totals["aqua"][i] - 1) for i, year in enumerate(HIST_YEARS)}


def terra_aqua_gap(counts: Counts, factors: dict[str, np.ndarray]) -> float | None:
    """The total harmonized from Terra over the one from Aqua, minus 1, over all MODIS-only years; None when Aqua
    has no point in them."""
    totals = {s: float(t.sum()) for s, t in _hist_totals(counts, factors).items()}
    return totals["terra"] / totals["aqua"] - 1 if totals["aqua"] > 0 else None


def _table(head: list[str], rows: list[list[object]]) -> str:
    cell = lambda v: f"{v:.4f}" if isinstance(v, float) else html.escape(str(v))
    return ("<table><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in head) + "</tr>"
            + "".join("<tr>" + "".join(f"<td>{cell(v)}</td>" for v in r) + "</tr>" for r in rows) + "</table>")


def write_report(out_dir: Path, report: dict) -> None:
    """report.json with every number and report.html with the main tables."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    parts = [f"<h1>Версія методу {html.escape(str(report.get('version', '')))}</h1>"]
    if "validation" in report:
        rows = [[sat, area, m.get("error"), m.get("calendar"), m.get("error_sparse")]
                for sat, areas in report["validation"].items() for area, m in areas.items()]
        parts += ["<h2>Перевірка: кожен рік без себе</h2>",
                  _table(["супутник", "області, °", "помилка", "календар", "помилка, бідні квадрати"], rows)]
    if "countries" in report:
        parts += ["<h2>Країни, квадрати 2°: ланцюжок теми проти світового</h2>",
                  _table(["країна", "з країною", "світовий"], [[c, v["old"], v["new"]] for c, v in report["countries"].items()])]
    if "terra_aqua" in report:
        parts += ["<h2>Terra проти Aqua, 2003–2011</h2>",
                  _table(["рік", "Terra / Aqua − 1"], [[y, v] for y, v in report["terra_aqua"].items()])]
    if "error_table" in report:
        parts += ["<h2>Похибка за кількістю точок</h2>",
                  _table(["джерело", "супутник", "n_min", "rel_error", "зразків"], report["error_table"])]
    if "rows" in report:
        parts += ["<h2>Рядки файлів</h2>", _table(["файл", "рядків"], [[k, v] for k, v in report["rows"].items()])]
    page = ("<!doctype html><html lang=\"uk\"><head><meta charset=\"utf-8\"><title>Звіт версії методу</title>"
            "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px}"
            "table{border-collapse:collapse;margin:8px 0 20px}td,th{border-bottom:1px solid #ddd;padding:4px 10px;"
            "text-align:right}td:first-child,th:first-child{text-align:left}</style></head><body>"
            + "".join(parts) + "</body></html>")
    (out_dir / "report.html").write_text(page, encoding="utf-8")
