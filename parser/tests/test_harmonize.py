"""Tests of the harmonize package: harmonization factors of MODIS against VIIRS Suomi NPP."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import logging
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import numpy as np

import build_factors
from firms.archive import archive_files
from harmonize.counts import Counts, build_counts
from harmonize.days import day_index, satellite_days
from harmonize.export import write_version
from harmonize.factors import chain, chain_without_each_year
from harmonize.series import Segment, backup_segments, weight_rows
from harmonize.sources import EPOCH, Member, api_files, archive_members, country_of, read_member
from harmonize.validate import (AreaSet, compare_chains, error_rows, metrics, noaa20_sets, predictions,
                                terra_aqua_agreement, terra_aqua_gap, write_report)


def empty_grid() -> np.ndarray:
    """Points of every 2-degree square and calendar month, all zero."""
    return np.zeros((90, 180, 12))


class FactorsTest(unittest.TestCase):
    def test_uniform(self) -> None:
        levels = chain(np.full((90, 180, 12), 100.0), np.full((90, 180, 12), 900.0))
        for values in (levels.factor, levels.cross_factor, levels.square8_factor, levels.world_factor):
            np.testing.assert_allclose(values, 9.0)

    def test_chain_values(self) -> None:
        modis, viirs = empty_grid(), empty_grid()
        modis[21, 21], viirs[21, 21] = 150, 1200
        for row, col in ((20, 21), (22, 21), (21, 20), (21, 22)):
            modis[row, col], viirs[row, col] = 500, 4500
        modis[60, 100], viirs[60, 100] = 10000, 70000
        levels = chain(modis, viirs)
        self.assertAlmostEqual(levels.world_factor[0], 7.341563786008231, places=9)
        self.assertAlmostEqual(levels.square8_factor[21, 21, 0], 8.73570168808264, places=9)
        self.assertAlmostEqual(levels.cross_factor[21, 21, 0], 8.965526307141214, places=9)
        self.assertAlmostEqual(levels.factor[21, 21, 0], 8.64368420476081, places=9)
        self.assertAlmostEqual(levels.own_share[21, 21, 0], 1 / 3, places=12)
        self.assertEqual(levels.cross_modis[21, 21, 0], 2000)

    def test_empty_square_inherits(self) -> None:
        modis, viirs = np.full((90, 180, 12), 100.0), np.full((90, 180, 12), 800.0)
        modis[10, 10], viirs[10, 10] = 0, 0
        levels = chain(modis, viirs)
        self.assertAlmostEqual(levels.factor[10, 10, 3], levels.cross_factor[10, 10, 3], places=12)
        self.assertEqual(levels.own_share[10, 10, 3], 0.0)

    def test_longitude_wraps(self) -> None:
        modis, viirs = empty_grid(), empty_grid()
        modis[40, 179], viirs[40, 179] = 500, 4000
        modis[40, 178], viirs[40, 178] = 70, 560
        levels = chain(modis, viirs)
        self.assertEqual(levels.cross_modis[40, 0, 5], 500)

    def test_pole_edge(self) -> None:
        modis, viirs = empty_grid(), empty_grid()
        for row, col in ((1, 50), (0, 49), (0, 51), (89, 50)):
            modis[row, col], viirs[row, col] = 100, 700
        levels = chain(modis, viirs)
        self.assertEqual(levels.cross_modis[0, 50, 0], 300)

    def test_without_each_year(self) -> None:
        modis = np.full((90, 180, 2, 12), 100.0)
        viirs = np.full((90, 180, 2, 12), 900.0)
        viirs[:, :, 1, :] = 500.0
        factors = chain_without_each_year(modis, viirs)
        np.testing.assert_allclose(factors[:, :, 0, :], 5.0)
        np.testing.assert_allclose(factors[:, :, 1, :], 9.0)

    def test_square_without_modis_but_viirs(self) -> None:
        modis, viirs = np.full((90, 180, 12), 100.0), np.full((90, 180, 12), 800.0)
        modis[30, 30], viirs[30, 30] = 0, 600
        levels = chain(modis, viirs)
        self.assertTrue(np.isfinite(levels.factor).all())
        self.assertAlmostEqual(levels.factor[30, 30, 0], 600 / 300 + levels.cross_factor[30, 30, 0], places=12)


FLYING = {"terra": date(2000, 11, 1), "aqua": date(2002, 7, 4), "snpp": date(2012, 1, 20), "noaa20": date(2018, 1, 5)}
SNPP_END = date(2026, 11, 2)


def presence(last: date) -> dict[str, np.ndarray]:
    """Days each satellite gave points: every day from its first one to `last` (Suomi NPP to its end)."""
    days = {}
    for sat, first in FLYING.items():
        flags = np.zeros(day_index(last) + 1, dtype=bool)
        end = min(last, SNPP_END) if sat == "snpp" else last
        flags[day_index(first):day_index(end) + 1] = True
        days[sat] = flags
    return days


class SeriesTest(unittest.TestCase):
    def test_no_gaps(self) -> None:
        self.assertEqual(backup_segments(presence(date(2026, 11, 10))), ([], []))

    def test_snpp_gap_noaa20(self) -> None:
        days = presence(date(2026, 11, 10))
        days["snpp"][day_index(date(2022, 7, 28)):day_index(date(2022, 7, 29)) + 1] = False
        self.assertEqual(backup_segments(days), ([Segment("noaa20", date(2022, 7, 28), date(2022, 7, 29))], []))

    def test_snpp_gap_before_noaa20(self) -> None:
        days = presence(date(2026, 11, 10))
        days["snpp"][day_index(date(2015, 3, 10))] = False
        self.assertEqual(backup_segments(days), ([Segment("aqua", date(2015, 3, 10), date(2015, 3, 10))], []))

    def test_partial_day_not_filled(self) -> None:
        days = presence(date(2026, 11, 10))
        days["snpp"][day_index(date(2023, 5, 1))] = True  # one point that day is enough
        self.assertEqual(backup_segments(days)[0], [])

    def test_aqua_gap_terra(self) -> None:
        days = presence(date(2026, 11, 10))
        days["aqua"][day_index(date(2002, 7, 30))] = False
        self.assertEqual(backup_segments(days), ([Segment("terra", date(2002, 7, 30), date(2002, 7, 30))], []))

    def test_terra_gap(self) -> None:
        days = presence(date(2026, 11, 10))
        days["terra"][day_index(date(2001, 6, 20))] = False
        self.assertEqual(backup_segments(days), ([], [date(2001, 6, 20)]))

    def test_weight_rows_counts(self) -> None:
        factors = {"aqua": np.full((90, 180, 12), 7.0), "terra": np.full((90, 180, 12), 6.0)}
        factors["aqua"][21, 21, 6] = 8.5
        backups = [Segment("noaa20", date(2022, 7, 31), date(2022, 8, 1))]
        rows = weight_rows(factors, backups)
        self.assertEqual(len(rows), 4 * 16200 * 12 + 2 * 16200)
        aqua = {(r[3], r[4]): r[5] for r in rows if r[0] == "aqua"}
        self.assertEqual(aqua[(21 * 180 + 21, 7)], 8.5)
        self.assertEqual({r[5] for r in rows if r[0] == "snpp"}, {1.0})
        backup = [r for r in rows if r[0] == "noaa20" and r[1] == date(2022, 7, 31)]
        self.assertEqual({r[4] for r in backup}, {7, 8})
        self.assertEqual(rows, sorted(rows, key=lambda r: (r[1], r[0], r[3], r[4])))


def proportional_counts(years: tuple[int, ...], ratio: float) -> Counts:
    """Counts where every 0.5-degree cell has 30 MODIS points a month and Suomi NPP sees `ratio` times more."""
    shape_half = (360, 720, len(years), 12)
    modis_half = np.full(shape_half, 30.0, dtype=np.float32)
    viirs_half = (modis_half * ratio).astype(np.float32)
    modis_sq = np.full((90, 180, len(years), 12), 480.0)
    viirs_sq = modis_sq * ratio
    hist = np.full((90, 180, 9, 12), 480.0)
    country = {"aqua": modis_sq, "terra": modis_sq, "snpp_aqua": viirs_sq, "snpp_terra": viirs_sq}
    pair = {sat: np.zeros((90, 180, 1, 12)) for sat in ("noaa20", "snpp")}
    pair_half = {sat: np.zeros((360, 720, 1, 12), dtype=np.float32) for sat in ("noaa20", "snpp")}
    return Counts(years=years, modis={"aqua": modis_sq, "terra": modis_sq}, snpp={"aqua": viirs_sq, "terra": viirs_sq},
                  modis_half={"aqua": modis_half, "terra": modis_half}, snpp_half={"aqua": viirs_half, "terra": viirs_half},
                  hist={"aqua": hist, "terra": hist}, country={"Ukraine": country}, viirs=pair, viirs_half=pair_half)


class ValidateTest(unittest.TestCase):
    def test_perfect_proportion(self) -> None:
        counts = proportional_counts((2012, 2013, 2014), 8.0)
        sets = predictions(counts, "aqua", [2012, 2013, 2014], 300.0)
        self.assertEqual(sorted(sets), ["0.5", "2", "8"])
        for area in sets.values():
            result = metrics(area)
            self.assertAlmostEqual(result["error"], 0.0, places=6)
            self.assertEqual(result["calendar"], 1.0)

    def test_error_rows_bins(self) -> None:
        area = AreaSet(pred=np.array([10.0, 100.0, 5.0]).reshape(3, 1, 1),
                       actual=np.array([15.0, 90.0, 7.0]).reshape(3, 1, 1),
                       n_points=np.array([2.0, 50.0, 0.0]).reshape(3, 1, 1), sparse=None)
        rows = error_rows({"2": area}, "aqua")
        self.assertEqual([(r[0], r[1], r[2], r[4]) for r in rows], [("modis", "aqua", 1, 1), ("modis", "aqua", 30, 1)])
        self.assertAlmostEqual(rows[0][3], 0.5)
        self.assertAlmostEqual(rows[1][3], 0.1)

    def test_noaa20_rows_take_its_points_as_they_are(self) -> None:
        counts = proportional_counts((2012,), 8.0)
        counts.viirs["noaa20"][20, 30, 0, 5], counts.viirs["snpp"][20, 30, 0, 5] = 150, 200
        counts.viirs_half["noaa20"][80, 120, 0, 5], counts.viirs_half["snpp"][80, 120, 0, 5] = 150, 200
        rows = error_rows(noaa20_sets(counts), "noaa20", source="viirs")
        self.assertEqual([(r[0], r[1], r[2], r[4]) for r in rows], [("viirs", "noaa20", 100, 3)])
        self.assertAlmostEqual(rows[0][3], 50 / 150)

    def test_terra_aqua_gap_over_all_years(self) -> None:
        counts = proportional_counts((2012,), 8.0)
        factors = {"aqua": np.full((90, 180, 12), 8.0), "terra": np.full((90, 180, 12), 6.0)}
        self.assertAlmostEqual(terra_aqua_gap(counts, factors), -0.25)
        counts.hist["aqua"] = np.zeros((90, 180, 9, 12))
        self.assertIsNone(terra_aqua_gap(counts, factors))

    def test_agreement_zero_when_identical(self) -> None:
        counts = proportional_counts((2012,), 8.0)
        factors = {"aqua": np.full((90, 180, 12), 8.0), "terra": np.full((90, 180, 12), 8.0)}
        agreement = terra_aqua_agreement(counts, factors)
        self.assertEqual(sorted(agreement), list(range(2003, 2012)))
        self.assertTrue(all(abs(v) < 1e-12 for v in agreement.values()))

    def test_compare_chains_proportional(self) -> None:
        old, new = compare_chains(proportional_counts((2012, 2013), 8.0), "Ukraine", 300.0)
        self.assertAlmostEqual(old, 0.0, places=9)
        self.assertAlmostEqual(new, 0.0, places=9)

    def test_write_report_files(self) -> None:
        report = {"version": "v-test", "validation": {"aqua": {"2": {"error": 0.18, "calendar": 0.74}}}}
        with tempfile.TemporaryDirectory() as tmp:
            write_report(Path(tmp), report)
            self.assertEqual(json.loads((Path(tmp) / "report.json").read_text(encoding="utf-8")), report)
            self.assertGreater((Path(tmp) / "report.html").stat().st_size, 0)


VERSION_FILES = {"method.json", "method_weight.csv", "method_factor.csv", "method_error.csv", "method_gap.csv",
                 "report.html", "report.json"}


def write_small_version(out_dir: Path) -> None:
    write_version(out_dir, method={"version": "v1", "label": "test", "params": {"lambda": 300}},
                  weights=[("aqua", date(2002, 7, 4), date(2012, 1, 19), 0, 1, 7.25),
                           ("noaa20", date(2026, 11, 3), None, 0, 1, 1.0)],
                  factors=[("aqua", 0, 1, 7.25, 10, 70, 10 / 310, 7.0, 40, 6.9, 6.8)],
                  errors=[("modis", "aqua", 1, 0.5), ("viirs", "snpp", 1, 0.0)],
                  gaps=[date(2001, 6, 20)], report={"version": "v1"})


class ExportTest(unittest.TestCase):
    def test_files_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "v1"
            write_small_version(out)
            self.assertEqual({p.name for p in out.iterdir()}, VERSION_FILES)
            weights = (out / "method_weight.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(weights[0], "version,satellite,date_from,date_to,cell2_id,calendar_month,is_day,weight")
            self.assertEqual(weights[2], "v1,noaa20,2026-11-03,,0,1,,1.0")
            errors = (out / "method_error.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(errors, ["version,source,satellite,n_min,rel_error", "v1,modis,aqua,1,0.5", "v1,viirs,snpp,1,0.0"])
            self.assertEqual((out / "method_gap.csv").read_text(encoding="utf-8").splitlines(), ["version,day", "v1,2001-06-20"])

    def test_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a", Path(tmp) / "b"
            write_small_version(first)
            write_small_version(second)
            for name in ("method.json", "method_weight.csv", "method_factor.csv", "method_error.csv", "method_gap.csv"):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(), name)


MODIS_HEADER = "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type"
VIIRS_NRT_HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight"


def write_zip(path: Path, members: dict[str, list[str]]) -> Path:
    """A yearly archive with the given member files, each a list of CSV lines."""
    with zipfile.ZipFile(path, "w") as z:
        for name, lines in members.items():
            z.writestr(name, "\n".join(lines) + "\n")
    return path


def modis_row(lat: float, lon: float, day: str, sat: str = "Aqua", type_: int = 0) -> str:
    return f"{lat},{lon},330.1,1.2,1.1,{day},1340,{sat},MODIS,60,6.1,290.2,12.5,D,{type_}"


class SourcesTest(unittest.TestCase):
    def test_reads_archive_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_zip(Path(tmp) / "modis_2015_all_countries.zip", {"modis/2015/modis_2015_Ukraine.csv": [
                MODIS_HEADER, modis_row(50.45, 30.5, "2015-07-01"), modis_row(48.1, 35.2, "2015-07-02", type_=2)]})
            rows = read_member(Member(path, "modis/2015/modis_2015_Ukraine.csv"))
        self.assertEqual(rows.sat.tolist(), [2, 2])
        self.assertEqual(rows.type.tolist(), [0, 2])
        self.assertEqual(rows.day.tolist(), [(date(2015, 7, 1) - EPOCH).days, (date(2015, 7, 2) - EPOCH).days])
        self.assertEqual(rows.cell[0], 808682)
        self.assertEqual(rows.cell2[0], 12705)

    def test_api_file_without_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "VIIRS_NOAA20_NRT" / "2026-10-01_5d.csv"
            path.parent.mkdir()
            path.write_text(VIIRS_NRT_HEADER + "\n51.89,29.34,339.6,0.35,0.57,2026-10-01,113,N20,VIIRS,n,2.0NRT,274.2,3.4,N\n",
                            encoding="utf-8")
            self.assertEqual(api_files(Path(tmp)), [Member(path, None)])
            rows = read_member(Member(path, None))
        self.assertEqual(rows.type.tolist(), [-1])
        self.assertEqual(rows.sat.tolist(), [4])

    def test_bad_rows_skipped(self) -> None:
        lines = [MODIS_HEADER, ",30.5,330.1,1.2,1.1,2015-07-01,1340,Aqua,MODIS,60,6.1,290.2,12.5,D,0",
                 modis_row(50.0, 30.0, "2015-13-01"), modis_row(50.0, 30.0, "2015-07-01", sat="X"),
                 modis_row(95.0, 30.0, "2015-07-01"), modis_row(50.0, 30.0, "2015-07-03")]
        with tempfile.TemporaryDirectory() as tmp:
            path = write_zip(Path(tmp) / "modis_2015_all_countries.zip", {"modis/2015/modis_2015_Ukraine.csv": lines})
            with self.assertLogs("harmonize.sources", level="WARNING") as logs:
                rows = read_member(Member(path, "modis/2015/modis_2015_Ukraine.csv"))
        self.assertEqual(rows.day.tolist(), [(date(2015, 7, 3) - EPOCH).days])
        self.assertIn("skipped 4 rows", logs.output[0])

    def test_exponent_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_zip(Path(tmp) / "modis_2015_all_countries.zip", {"modis/2015/modis_2015_Gabon.csv": [
                MODIS_HEADER, "4e-05,-3e-05,330.1,1.2,1.1,2015-07-01,1340,Aqua,MODIS,60,6.1,290.2,12.5,D,0"]})
            rows = read_member(Member(path, "modis/2015/modis_2015_Gabon.csv"))
        self.assertEqual(rows.cell.tolist(), [519119])

    def test_short_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_zip(Path(tmp) / "modis_2001_all_countries.zip", {"modis/2001/modis_2001_Chad.csv": [
                MODIS_HEADER, modis_row(12.0, 18.0, "2001-02-01", sat="T"), modis_row(12.0, 18.0, "2001-02-01", sat="A")]})
            rows = read_member(Member(path, "modis/2001/modis_2001_Chad.csv"))
        self.assertEqual(rows.sat.tolist(), [1, 2])

    def test_archive_members_and_country(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_zip(Path(tmp) / "viirs-snpp_2015_all_countries.zip", {
                "viirs-snpp/2015/viirs-snpp_2015_Russian_Federation.csv": ["x"], "viirs-snpp/2015/readme.txt": ["x"]})
            with self.assertLogs("harmonize.sources", level="WARNING") as logs:
                members = archive_members(Path(tmp), "viirs-snpp", [2014, 2015])
        self.assertIn("viirs-snpp_2014_all_countries.zip", logs.output[0])
        self.assertEqual([m.member for m in members], ["viirs-snpp/2015/viirs-snpp_2015_Russian_Federation.csv"])
        self.assertEqual(country_of(members[0]), "Russian_Federation")
        self.assertIsNone(country_of(Member(Path("x.csv"), None)))


class DaysTest(unittest.TestCase):
    def test_presence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "a.csv", Path(tmp) / "b.csv"
            first.write_text("\n".join([MODIS_HEADER, modis_row(10.0, 20.0, "2002-07-04"),
                                         modis_row(10.0, 20.0, "2002-07-06")]) + "\n", encoding="utf-8")
            second.write_text("\n".join([MODIS_HEADER, modis_row(10.0, 20.0, "2002-07-05", sat="Terra")]) + "\n",
                              encoding="utf-8")
            days = satellite_days([Member(first, None), Member(second, None)], jobs=2)
        self.assertEqual({len(flags) for flags in days.values()}, {day_index(date(2002, 7, 6)) + 1})
        self.assertTrue(days["aqua"][day_index(date(2002, 7, 4))])
        self.assertFalse(days["aqua"][day_index(date(2002, 7, 5))])
        self.assertTrue(days["terra"][day_index(date(2002, 7, 5))])
        self.assertFalse(days["snpp"].any())


VIIRS_HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight,type"


def viirs_row(lat: float, lon: float, day: str, sat: str = "N") -> str:
    return f"{lat},{lon},330.0,0.4,0.4,{day},1340,{sat},VIIRS,n,2,290.0,5.0,D,0"


def small_archive(folder: Path) -> list[Member]:
    """Archives of 2005, 2015 and 2020: Aqua points on 2015-07-01 (Suomi NPP flies) and 2015-07-02 (Suomi NPP
    silent), one static row, one point on the corner of the globe, one in Brazil; in 2005 Aqua on 03-01, when
    Terra flies too, and on 03-02, when Terra is silent; in 2020 NOAA-20 on 08-01, when Suomi NPP flies too,
    and on 08-02, when Suomi NPP is silent."""
    write_zip(folder / "modis_2005_all_countries.zip", {"modis/2005/modis_2005_Ukraine.csv": [
        MODIS_HEADER, modis_row(50.45, 30.5, "2005-03-01"), modis_row(50.45, 30.5, "2005-03-01", sat="Terra"),
        modis_row(50.45, 30.5, "2005-03-02")]})
    write_zip(folder / "viirs-jpss1_2020_all_countries.zip", {"viirs-jpss1/2020/viirs-jpss1_2020_Ukraine.csv": [
        VIIRS_HEADER, viirs_row(50.45, 30.5, "2020-08-01", "N20"), viirs_row(50.45, 30.5, "2020-08-01", "N20"),
        viirs_row(50.45, 30.5, "2020-08-02", "N20")]})
    write_zip(folder / "viirs-snpp_2020_all_countries.zip", {"viirs-snpp/2020/viirs-snpp_2020_Ukraine.csv": [
        VIIRS_HEADER, viirs_row(50.45, 30.5, "2020-08-01")]})
    write_zip(folder / "modis_2015_all_countries.zip", {
        "modis/2015/modis_2015_Ukraine.csv": [MODIS_HEADER, modis_row(50.45, 30.5, "2015-07-01"),
                                              modis_row(50.45, 30.5, "2015-07-02"),
                                              modis_row(50.45, 30.5, "2015-07-01", type_=2),
                                              modis_row(90.0, 180.0, "2015-07-01")],
        "modis/2015/modis_2015_Brazil.csv": [MODIS_HEADER, modis_row(-15.8, -47.9, "2015-07-01")]})
    write_zip(folder / "viirs-snpp_2015_all_countries.zip", {"viirs-snpp/2015/viirs-snpp_2015_Ukraine.csv": [
        VIIRS_HEADER, "50.45,30.5,330.0,0.4,0.4,2015-07-01,1340,N,VIIRS,n,2,290.0,5.0,D,0"]})
    return (archive_members(folder, "modis", [2005, 2015]) + archive_members(folder, "viirs-snpp", [2015, 2020])
            + archive_members(folder, "viirs-jpss1", [2020]))


class CountsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.days = satellite_days(small_archive(self.folder), jobs=1)
        sources_log = logging.getLogger("harmonize.sources")
        self.addCleanup(sources_log.setLevel, sources_log.level)
        sources_log.setLevel(logging.ERROR)  # the small archive lacks most years on purpose

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_common_days_only(self) -> None:
        counts = build_counts(self.folder, self.days, jobs=2, cache_dir=None)
        self.assertEqual(counts.modis["aqua"].sum(), 3)
        self.assertEqual(counts.snpp["aqua"].sum(), 1)
        self.assertEqual(counts.snpp["terra"].sum(), 0)

    def test_hist_years_on_days_terra_and_aqua_share(self) -> None:
        counts = build_counts(self.folder, self.days, jobs=1, cache_dir=None)
        self.assertEqual(counts.hist["aqua"][:, :, 2005 - 2003, 2].sum(), 1)
        self.assertEqual(counts.hist["terra"][:, :, 2005 - 2003, 2].sum(), 1)

    def test_noaa20_and_snpp_on_shared_days(self) -> None:
        counts = build_counts(self.folder, self.days, jobs=1, cache_dir=None)
        self.assertEqual(counts.viirs["noaa20"][:, :, 2020 - 2018, 7].sum(), 2)
        self.assertEqual(counts.viirs["snpp"][:, :, 2020 - 2018, 7].sum(), 1)
        self.assertEqual(counts.viirs_half["noaa20"].sum(), 2)
        self.assertEqual(counts.viirs_half["snpp"].sum(), 1)
        self.assertEqual(counts.snpp["aqua"].sum(), 1)

    def test_country_split(self) -> None:
        counts = build_counts(self.folder, self.days, jobs=1, cache_dir=None)
        self.assertEqual(counts.country["Brazil"]["aqua"].sum(), 1)
        self.assertEqual(counts.country["Ukraine"]["aqua"].sum(), 2)
        self.assertEqual(counts.country["Ukraine"]["snpp_aqua"].sum(), 1)

    def test_edge_point(self) -> None:
        counts = build_counts(self.folder, self.days, jobs=1, cache_dir=None)
        self.assertEqual(counts.modis["aqua"][89, 179, 2015 - 2012, 6], 1)
        self.assertEqual(counts.modis_half["aqua"][359, 719, 2015 - 2012, 6], 1)

    def test_cache_reused(self) -> None:
        cache = self.folder / "cache"
        first = build_counts(self.folder, self.days, jobs=1, cache_dir=cache)
        with mock.patch("harmonize.counts.read_member", side_effect=AssertionError("read again")):
            second = build_counts(self.folder, self.days, jobs=1, cache_dir=cache)
        np.testing.assert_array_equal(first.modis["aqua"], second.modis["aqua"])
        np.testing.assert_array_equal(first.country["Brazil"]["aqua"], second.country["Brazil"]["aqua"])


def full_archive(data: Path) -> None:
    """Every yearly archive up to 2025 for one place in Ukraine, with points on every day a satellite flies:
    Terra 1 a day, Aqua 3 a day before 2012 and 2 from 2012, Suomi NPP 8 and NOAA-20 6."""
    archive = data / "raw" / "archive"
    archive.mkdir(parents=True)
    for item in archive_files(2025):
        sensor, year = item.sensor.value, item.year
        lines = [MODIS_HEADER if sensor == "modis" else VIIRS_HEADER]
        day = date(year, 1, 1)
        while day.year == year:
            text = day.isoformat()
            if sensor == "modis":
                if day >= date(2000, 11, 1):
                    lines.append(modis_row(50.45, 30.5, text, sat="Terra"))
                if day >= date(2002, 7, 4):
                    lines += [modis_row(50.45, 30.5, text)] * (3 if year < 2012 else 2)
            elif sensor == "viirs-snpp":
                if day >= date(2012, 1, 20):
                    lines += [viirs_row(50.45, 30.5, text)] * 8
            else:
                lines += [viirs_row(50.45, 30.5, text, "N20")] * 6
            day += timedelta(days=1)
        write_zip(archive / item.name, {f"{sensor}/{year}/{sensor}_{year}_Ukraine.csv": lines})


class CommandTest(unittest.TestCase):
    def test_refuses_existing_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "v1"
            existing.mkdir()
            (existing / "keep.txt").write_text("old", encoding="utf-8")
            with self.assertLogs("build_factors", level="ERROR"):
                code = build_factors.main(["--version", "v1", "--out", tmp, "--data", tmp])
            self.assertEqual(code, 1)
            self.assertEqual([p.name for p in existing.iterdir()], ["keep.txt"])

    def test_missing_archives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertLogs("build_factors", level="ERROR") as logs:
                code = build_factors.main(["--version", "v1", "--out", str(Path(tmp) / "out"), "--data", tmp])
            self.assertEqual(code, 2)
            self.assertIn("modis_2012_all_countries.zip", logs.output[0])
            self.assertFalse((Path(tmp) / "out").exists())

    def test_rejects_version_that_is_not_a_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            (out / "v-older").mkdir(parents=True)
            for name in ("", ".", "..", "/abs", "a/b", "v1/.."):
                with self.subTest(name=name), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as stop:
                        build_factors.main(["--version", name, "--force", "--out", str(out), "--data", tmp])
                    self.assertEqual(stop.exception.code, 2)
            self.assertTrue((out / "v-older").is_dir())

    def test_missing_archive_outside_learning_years(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "raw" / "archive"
            archive.mkdir(parents=True)
            for item in archive_files(2025):
                if item.name != "modis_2005_all_countries.zip":
                    (archive / item.name).touch()
            with self.assertLogs("build_factors", level="WARNING") as logs:
                code = build_factors.main(["--version", "v1", "--last-year", "2025", "--out", str(Path(tmp) / "out"),
                                           "--data", tmp])
            self.assertEqual(code, 2)
            errors = [line for line in logs.output if line.startswith("ERROR")]
            self.assertEqual(len(errors), 1)
            self.assertIn("modis_2005_all_countries.zip", errors[0])
            self.assertNotIn("modis_2012_all_countries.zip", errors[0])
            self.assertTrue(any("current-year" in line for line in logs.output if line.startswith("WARNING")))
            self.assertFalse((Path(tmp) / "out").exists())

    def test_builds_a_version_and_replaces_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            full_archive(Path(tmp))
            out = Path(tmp) / "out" / "v1"
            argv = ["--version", "v1", "--last-year", "2025", "--data", tmp, "--out", str(out.parent), "--jobs", "2"]
            with self.assertLogs("build_factors", level="INFO"):
                self.assertEqual(build_factors.main(argv), 0)
            first = {p.name: p.read_bytes() for p in out.iterdir() if p.name != "report.json"}
            with (out / "method_error.csv").open(encoding="utf-8", newline="") as fh:
                viirs = {(r["satellite"], r["n_min"]): float(r["rel_error"])
                         for r in csv.DictReader(fh) if r["source"] == "viirs"}
            self.assertEqual(sorted(viirs), [("noaa20", "100"), ("snpp", "1")])
            self.assertAlmostEqual(viirs[("noaa20", "100")], 2 / 6)
            self.assertEqual(viirs[("snpp", "1")], 0.0)
            params = json.loads((out / "method.json").read_text(encoding="utf-8"))["params"]
            self.assertEqual((params["terra_only"]["date_from"], params["terra_only"]["date_to"]),
                             ("2000-11-01", "2002-07-03"))
            self.assertAlmostEqual(params["terra_only"]["terra_vs_aqua_2003_2011"], -1 / 3, places=4)
            self.assertIn("so the days from date_from to date_to may be off", params["terra_only"]["note"])
            self.assertEqual(params["noaa20_error_years"], [2018, 2025])
            with self.assertLogs("build_factors", level="INFO"):
                self.assertEqual(build_factors.main(argv + ["--force"]), 0)
            self.assertEqual({p.name: p.read_bytes() for p in out.iterdir() if p.name != "report.json"}, first)


if __name__ == "__main__":
    unittest.main()
