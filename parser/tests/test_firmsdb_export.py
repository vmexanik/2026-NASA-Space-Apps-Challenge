"""Tests of firmsdb.export and firmsdb.method: the dump package that restore.sh loads, built from small yearly zips and
API files that the tests write into a temporary folder, and the rows of the method versions."""

from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest import mock

import export_dump
from firms.grid import cell_id_e5
from firmsdb import export, method
from firmsdb.export import build_package
from firmsdb.precedence import assign_batches
from firmsdb.rows import SATELLITES, to_e5
from firmsdb.sources import list_api, list_archive

HARMONIZATION = Path(__file__).with_name("data") / "harmonization"  # holds the version vtest

#: Points of the fixture: Testland (T1-T3), Otherland (O1, O2), the open sea (S) and a place that no zip has (F).
T1, T2, T3 = ("50.45001", "30.52345"), ("50.1", "30.1"), ("49.8", "31.2")
O1, O2 = ("-20.3", "130.2"), ("-20.8", "131")
SEA, FAR = ("0.5", "-30.5"), ("10.1", "10.1")

ZIP_MODIS, ZIP_SNPP = "modis_2021_all_countries.zip", "viirs-snpp_2021_all_countries.zip"
SP, NRT_A, NRT_B = ("VIIRS_SNPP_SP/2026-01-01_5d.csv", "VIIRS_SNPP_NRT/2026-01-04_5d.csv",
                    "VIIRS_SNPP_NRT/2026-01-07_5d.csv")
#: When each file of the fixture was changed last: the NRT file B is newer than A, and both are newer than the SP.
MTIMES = {ZIP_MODIS: datetime(2026, 11, 14, 12, 52, tzinfo=UTC), ZIP_SNPP: datetime(2026, 11, 14, 19, 29, tzinfo=UTC),
          SP: datetime(2026, 11, 14, 12, 0, tzinfo=UTC), NRT_A: datetime(2026, 11, 14, 12, 30, tzinfo=UTC),
          NRT_B: datetime(2026, 11, 14, 13, 0, tzinfo=UTC)}

FIRE = "fire"
MODIS_COLUMNS = ("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
                 "bright_t31,frp,daynight")
VIIRS_COLUMNS = ("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
                 "bright_ti5,frp,daynight")


@dataclass(frozen=True)
class Point:
    """One detection of the fixture, the files that hold it, and where the package of the world and the package of
    Testland put it: FIRE for firms.hotspot, 1, 2 or 3 for firms.hotspot_static with that type, None for nowhere."""

    name: str
    where: tuple[str, str]  # latitude and longitude as the files write them
    day: str
    time: str  # acq_time as the files write it: the archive keeps the leading zeros, the API drops them
    satellite: str  # the FIRMS value
    confidence: str
    type: str | None  # the FIRMS type, which NRT files do not write
    files: tuple[str, ...]  # "<zip>/<Country>" for a member of a zip, else an API file
    world: str | int | None
    testland: str | int | None


POINTS = [
    # The archive. The rows of a member are not in the order of the parts.
    Point("a2", T1, "2021-08-01", "0049", "Aqua", "59", "0", (f"{ZIP_MODIS}/Testland",), FIRE, FIRE),
    Point("a3", T1, "2021-03-15", "0830", "Terra", "20", "0", (f"{ZIP_MODIS}/Testland",), FIRE, FIRE),
    Point("a1", T2, "2021-08-02", "1015", "Terra", "85", "0", (f"{ZIP_MODIS}/Testland",), FIRE, FIRE),
    Point("a4", T3, "2021-01-08", "0906", "Terra", "35", "2", (f"{ZIP_MODIS}/Testland",), 2, 2),
    Point("a5", O1, "2021-09-10", "0140", "Aqua", "90", "0", (f"{ZIP_MODIS}/Otherland",), FIRE, None),
    Point("b1", T1, "2021-08-01", "1048", "N", "n", "0", (f"{ZIP_SNPP}/Testland",), FIRE, FIRE),
    Point("b2", T1, "2021-08-01", "0024", "N", "l", "0", (f"{ZIP_SNPP}/Testland",), FIRE, FIRE),
    Point("b3", T2, "2021-07-31", "2318", "N", "h", "0", (f"{ZIP_SNPP}/Testland",), FIRE, FIRE),
    Point("b4", O1, "2021-09-10", "0420", "N", "n", "0", (f"{ZIP_SNPP}/Otherland",), FIRE, None),
    Point("b5", O2, "2021-10-01", "0510", "N", "n", "3", (f"{ZIP_SNPP}/Otherland",), 3, None),
    # The SP file holds 2026-01-01..05; NRT A holds 01-04..08 and keeps only 01-06; the newer NRT B holds 01-07..11.
    Point("s5", T3, "2026-01-01", "1200", "N", "l", "2", (SP,), 2, 2),
    Point("s1", T1, "2026-01-02", "113", "N", "n", "0", (SP,), FIRE, FIRE),
    Point("s6", FAR, "2026-01-02", "946", "N", "n", "1", (SP,), 1, None),
    Point("s4", FAR, "2026-01-03", "945", "N", "n", "0", (SP,), 3, None),
    Point("s2", T2, "2026-01-04", "28", "N", "h", "0", (SP, NRT_A), FIRE, FIRE),
    Point("s3", O1, "2026-01-05", "1305", "N", "n", "0", (SP,), FIRE, None),
    Point("n6", T1, "2026-01-04", "2200", "N", "n", None, (NRT_A,), None, None),
    Point("n2", T1, "2026-01-06", "5", "N", "n", None, (NRT_A,), FIRE, FIRE),
    Point("n5", T1, "2026-01-07", "300", "N", "l", None, (NRT_A,), None, None),
    Point("n3", O1, "2026-01-07", "2210", "N", "n", None, (NRT_A, NRT_B), FIRE, None),
    Point("n4", T2, "2026-01-08", "1", "N", "h", None, (NRT_A, NRT_B), FIRE, FIRE),
    Point("m3", SEA, "2026-01-09", "350", "N", "n", None, (NRT_B,), 3, None),
    Point("m4", T2, "2026-01-11", "2359", "N", "h", None, (NRT_B,), FIRE, FIRE),
]


def holder(point: Point) -> str:
    """The file whose row of the point goes into the package."""
    if not point.day.startswith("2026"):
        return point.files[0].split("/")[0]
    day = date.fromisoformat(point.day)
    return SP if day <= date(2026, 1, 5) else NRT_A if day == date(2026, 1, 6) else NRT_B


def key(point: Point) -> tuple[str, ...]:
    """acq_date, acq_time, satellite, lat_e5 and lon_e5 of a point, as the package writes them."""
    return (point.day, str(int(point.time)), str(SATELLITES[point.satellite]), str(to_e5(point.where[0])),
            str(to_e5(point.where[1])))


def cell(where: tuple[str, str]) -> int:
    return cell_id_e5(to_e5(where[0]), to_e5(where[1]))


def csv_line(point: Point, *, version: str, with_type: bool) -> str:
    lat, lon = point.where
    if point.satellite in ("Terra", "Aqua"):
        values = [lat, lon, "310.5", "1.1", "1", point.day, point.time, point.satellite, "MODIS", point.confidence,
                  version, "290.2", "12.5", "D"]
    else:
        values = [lat, lon, "330.55", "0.39", "0.36", point.day, point.time, point.satellite, "VIIRS",
                  point.confidence, version, "295.25", "3.5", "D"]
    return ",".join(values + ([point.type or "0"] if with_type else []))


def csv_text(points: list[Point], *, modis: bool, version: str, with_type: bool) -> str:
    header = (MODIS_COLUMNS if modis else VIIRS_COLUMNS) + (",type" if with_type else "")
    return "\n".join([header] + [csv_line(p, version=version, with_type=with_type) for p in points])


def write_fixture(root: Path, points: list[Point], mtimes: dict[str, datetime]) -> tuple[Path, Path]:
    """The folders archive/ and api/ under root with the files that hold the points, changed last at mtimes."""
    archive_dir, api_dir = root / "archive", root / "api"
    archive_dir.mkdir(parents=True)
    api_dir.mkdir(parents=True)
    names = sorted({name for p in points for name in p.files})
    for zip_name in sorted({name.split("/")[0] for name in names if ".zip/" in name}):
        prefix, year = zip_name.split("_")[:2]
        modis = prefix == "modis"
        with zipfile.ZipFile(archive_dir / zip_name, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.mkdir(f"{prefix}/{year}/")
            for country in ("Otherland", "Testland"):
                member_points = [p for p in points if f"{zip_name}/{country}" in p.files]
                if member_points:
                    archive.writestr(f"{prefix}/{year}/{prefix}_{year}_{country}.csv",
                                     csv_text(member_points, modis=modis, version="6.03" if modis else "2",
                                              with_type=True) + "\n")
        os.utime(archive_dir / zip_name, (mtimes[zip_name].timestamp(),) * 2)
    for name in names:
        if ".zip/" not in name:
            source = name.split("/")[0]
            nrt, modis = source.endswith("_NRT"), source.startswith("MODIS")
            version = ("6.1NRT" if nrt else "61.03") if modis else ("2.0NRT" if nrt else "2")
            path = api_dir / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(csv_text([p for p in points if name in p.files], modis=modis, version=version,
                                     with_type=not nrt), encoding="utf-8")
            os.utime(path, (mtimes[name].timestamp(),) * 2)
    return archive_dir, api_dir


def table_rows(package: Path, rel: str) -> list[list[str]]:
    """The rows of a data file of a package, as fields of text."""
    with gzip.open(package / rel, "rt", encoding="utf-8", newline="\n") as handle:
        return [line.split("\t") for line in handle.read().splitlines()]


def part_files(package: Path) -> list[str]:
    return sorted(p.relative_to(package).as_posix() for table in ("hotspot", "hotspot_static")
                  for p in (package / "data" / table).glob("*.tsv.gz"))


def data_files(package: Path) -> dict[str, bytes]:
    return {p.relative_to(package).as_posix(): p.read_bytes() for p in sorted((package / "data").rglob("*"))
            if p.is_file()}


class TestExport(unittest.TestCase):
    """The packages of the world and of Testland, built once from the fixture of POINTS."""

    root: Path
    archive_dir: Path
    api_dir: Path
    world: Path
    world_manifest: dict
    testland: Path
    testland_manifest: dict

    @classmethod
    def setUpClass(cls) -> None:
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.root = Path(tmp.name)
        cls.archive_dir, cls.api_dir = write_fixture(cls.root / "raw", POINTS, MTIMES)
        cls.world = cls.root / "dump" / "world"
        cls.world_manifest = cls.build(cls.world, methods=["v0-raw", "vtest"], countries=None, jobs=2)
        cls.testland = cls.root / "dump" / "testland"
        cls.testland_manifest = cls.build(cls.testland, methods=["vtest"], countries=["Testland"], jobs=2)

    @classmethod
    def build(cls, out: Path, *, methods: list[str], countries: list[str] | None, jobs: int,
              years: tuple[int, int] | None = None) -> dict:
        return build_package(out, archive_dir=cls.archive_dir, api_dir=cls.api_dir, harmonization_dir=HARMONIZATION,
                             methods=methods, countries=countries, years=years, jobs=jobs, name=out.name)

    def batch(self, name: str) -> int:
        files = list_archive(self.archive_dir, None) + list_api(self.api_dir, None)
        ids = assign_batches(files)
        return next(ids[src.path] for src in files if src.path.as_posix().endswith(name))

    def parts(self, package: Path) -> dict[str, list[list[str]]]:
        return {rel: table_rows(package, rel) for rel in part_files(package)}

    def test_manifest_counts(self) -> None:
        for package, manifest in [(self.world, self.world_manifest), (self.testland, self.testland_manifest)]:
            with self.subTest(package=package.name):
                self.assertEqual(json.loads((package / "manifest.json").read_text(encoding="utf-8")), manifest)
                listed = [entry["file"] for entry in manifest["files"]]
                self.assertEqual(sorted(listed), sorted(data_files(package)))
                self.assertEqual(len(listed), len(set(listed)))
                for entry in manifest["files"]:
                    text = subprocess.run(["gzip", "-dc", str(package / entry["file"])], capture_output=True,
                                          check=True).stdout.decode("utf-8")
                    self.assertEqual(text.count("\n"), entry["rows"], entry["file"])
                    self.assertTrue(text == "" or text.endswith("\n"), entry["file"])

    def test_manifest(self) -> None:
        manifest = self.world_manifest
        self.assertEqual((manifest["format"], manifest["name"], manifest["scope"], manifest["countries"],
                          manifest["years"], manifest["methods"]),
                         (1, "world", "world", None, [2021, 2026], ["v0-raw", "vtest"]))
        datetime.strptime(manifest["built_at"], "%Y-%m-%dT%H:%M:%SZ")
        entries = {entry["file"]: entry for entry in manifest["files"]}
        self.assertEqual(entries["data/hotspot/2021_aqua.tsv.gz"],
                         {"table": "hotspot", "partition": "hotspot_2021_aqua", "year": 2021, "satellite": "aqua",
                          "file": "data/hotspot/2021_aqua.tsv.gz", "rows": 2})
        self.assertEqual(entries["data/hotspot_static/2026_snpp.tsv.gz"],
                         {"table": "hotspot_static", "partition": "hotspot_static_2026", "year": 2026,
                          "file": "data/hotspot_static/2026_snpp.tsv.gz", "rows": 4})
        self.assertEqual(entries["data/method/v0-raw/method_weight.tsv.gz"],
                         {"table": "method_weight", "version": "v0-raw",
                          "file": "data/method/v0-raw/method_weight.tsv.gz", "rows": 777_600})
        self.assertEqual(entries["data/satellite.tsv.gz"],
                         {"table": "satellite", "file": "data/satellite.tsv.gz", "rows": 5})
        self.assertEqual(sorted(entry["table"] for entry in manifest["files"] if entry.get("version") == "vtest"),
                         ["method", "method_error", "method_factor", "method_gap", "method_weight"])
        self.assertEqual(sorted(entry["table"] for entry in manifest["files"] if entry.get("version") == "v0-raw"),
                         ["method", "method_weight"])
        self.assertEqual(manifest["sources"], [
            {"file": f"api/{name}", "size": (self.api_dir / name).stat().st_size,
             "mtime": MTIMES[name].strftime("%Y-%m-%dT%H:%M:%SZ")} for name in (NRT_A, NRT_B, SP)] + [
            {"file": f"archive/{name}", "size": (self.archive_dir / name).stat().st_size,
             "mtime": MTIMES[name].strftime("%Y-%m-%dT%H:%M:%SZ")} for name in (ZIP_MODIS, ZIP_SNPP)])
        self.assertEqual(table_rows(self.world, "data/satellite.tsv.gz"), [
            ["1", "terra", "Terra", "MODIS", "Terra"], ["2", "aqua", "Aqua", "MODIS", "Aqua"],
            ["3", "snpp", "N", "VIIRS", "Suomi NPP"], ["4", "noaa20", "N20", "VIIRS", "NOAA-20"],
            ["5", "noaa21", "N21", "VIIRS", "NOAA-21"]])
        self.assertTrue((self.world / "README.md").is_file())

    def test_each_point_once(self) -> None:
        for package, outcome in [(self.world, "world"), (self.testland, "testland")]:
            with self.subTest(package=package.name):
                found = Counter()
                batches = {}
                for rows in self.parts(package).values():
                    for row in rows:
                        found[tuple(row[:3] + row[4:6])] += 1
                        batches[tuple(row[:3] + row[4:6])] = int(row[15])
                expected = [p for p in POINTS if getattr(p, outcome) is not None]
                self.assertEqual(found, Counter(key(p) for p in expected))
                for p in expected:
                    self.assertEqual(batches[key(p)], self.batch(holder(p)), p.name)

    def test_static_rows(self) -> None:
        def types(package: Path) -> dict[tuple[str, ...], int]:
            return {tuple(row[:3] + row[4:6]): int(row[16]) for rel, rows in self.parts(package).items()
                    if rel.startswith("data/hotspot_static/") for row in rows}

        def fires(package: Path) -> set[tuple[str, ...]]:
            return {tuple(row[:3] + row[4:6]) for rel, rows in self.parts(package).items()
                    if rel.startswith("data/hotspot/") for row in rows}

        for package, outcome in [(self.world, "world"), (self.testland, "testland")]:
            with self.subTest(package=package.name):
                self.assertEqual(types(package), {key(p): getattr(p, outcome) for p in POINTS
                                                  if getattr(p, outcome) not in (None, FIRE)})
                self.assertEqual(fires(package), {key(p) for p in POINTS if getattr(p, outcome) == FIRE})
        by_name = {p.name: p for p in POINTS}
        world_types = types(self.world)
        self.assertEqual(world_types[key(by_name["a4"])], 2)  # FIRMS type 2 in the archive
        self.assertEqual(world_types[key(by_name["m3"])], 3)  # an NRT point in the open sea, outside the footprint
        self.assertEqual(world_types[key(by_name["s6"])], 1)  # a volcano outside the footprint keeps its type

    def test_sorted(self) -> None:
        for package in (self.world, self.testland):
            for rel, rows in self.parts(package).items():
                with self.subTest(package=package.name, part=rel):
                    order = [(int(row[3]), row[0], int(row[1])) for row in rows]
                    self.assertEqual(order, sorted(order))
        self.assertEqual([row[1] for row in table_rows(self.world, "data/hotspot/2021_snpp.tsv.gz")],
                         ["420", "2318", "24", "1048"])  # O1, T2, then T1 at 00:24 before T1 at 10:48 on one day

    def test_hotspot_lines(self) -> None:
        aqua = table_rows(self.world, "data/hotspot/2021_aqua.tsv.gz")
        self.assertIn(["2021-08-01", "49", "2", str(cell(T1)), "5045001", "3052345", "12.5", "310.5", "290.2", "1.1",
                       "1.0", "n", "59", "t", "f", str(self.batch(ZIP_MODIS))], aqua)
        snpp = table_rows(self.world, "data/hotspot/2026_snpp.tsv.gz")
        self.assertIn(["2026-01-06", "5", "3", str(cell(T1)), "5045001", "3052345", "3.5", "330.55", "295.25", "0.39",
                       "0.36", "n", r"\N", "t", "t", str(self.batch(NRT_A))], snpp)
        static = table_rows(self.world, "data/hotspot_static/2021_modis.tsv.gz")
        self.assertEqual(static, [["2021-01-08", "906", "1", str(cell(T3)), "4980000", "3120000", "12.5", "310.5",
                                   "290.2", "1.1", "1.0", "n", "35", "t", "f", str(self.batch(ZIP_MODIS)), "2"]])

    def test_reproducible(self) -> None:
        again = self.root / "dump" / "world-again"
        self.build(again, methods=["v0-raw", "vtest"], countries=None, jobs=1)
        first, second = data_files(self.world), data_files(again)
        self.assertEqual(sorted(first), sorted(second))
        for rel in first:
            self.assertEqual(first[rel], second[rel], rel)
            self.assertEqual(first[rel][:10], b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff", rel)  # no time, no name
        self.build(again, methods=["vtest"], countries=None, jobs=3)  # a second build replaces the package
        self.assertEqual(sorted(data_files(again)), sorted(rel for rel in first if "/v0-raw/" not in rel))

    def test_countries_slice(self) -> None:
        manifest = self.testland_manifest
        self.assertEqual((manifest["scope"], manifest["countries"], manifest["methods"]),
                         ("countries", ["Testland"], ["vtest"]))
        self.assertEqual(table_rows(self.testland, "data/archive_cell.tsv.gz"),
                         [[str(c)] for c in sorted({cell(T1), cell(T2), cell(T3)})])
        self.assertEqual(table_rows(self.world, "data/archive_cell.tsv.gz"),
                         [[str(c)] for c in sorted({cell(T1), cell(T2), cell(T3), cell(O1), cell(O2)})])
        cells = {int(row[3]) for rows in self.parts(self.testland).values() for row in rows}
        self.assertEqual(cells, {cell(T1), cell(T2), cell(T3)})

    def test_day_source(self) -> None:
        def days(first: str, last: str) -> list[str]:
            start, end = date.fromisoformat(first), date.fromisoformat(last)
            return [(start + timedelta(days=n)).isoformat() for n in range((end - start).days + 1)]

        modis, snpp = str(self.batch(ZIP_MODIS)), str(self.batch(ZIP_SNPP))
        sp, nrt_a, nrt_b = (str(self.batch(name)) for name in (SP, NRT_A, NRT_B))
        api = ([["3", d, "f", sp] for d in days("2026-01-01", "2026-01-05")] + [["3", "2026-01-06", "t", nrt_a]]
               + [["3", d, "t", nrt_b] for d in days("2026-01-07", "2026-01-11")])
        self.assertEqual(table_rows(self.world, "data/day_source.tsv.gz"),
                         [["1", d, "f", modis] for d in days("2021-01-08", "2021-08-02")]
                         + [["2", d, "f", modis] for d in days("2021-08-01", "2021-09-10")]
                         + [["3", d, "f", snpp] for d in days("2021-07-31", "2021-10-01")] + api)
        self.assertEqual(table_rows(self.testland, "data/day_source.tsv.gz"),
                         [["1", d, "f", modis] for d in days("2021-01-08", "2021-08-02")]
                         + [["2", "2021-08-01", "f", modis]]
                         + [["3", d, "f", snpp] for d in days("2021-07-31", "2021-08-01")] + api)

    def test_load_batch(self) -> None:
        def row(name: str, folder: Path, source: str, nrt: str, members: str, versions: str, first: str, last: str,
                fires: int, statics: int) -> list[str]:
            path = folder / name
            raw_name = f"{'archive' if folder == self.archive_dir else 'api'}/{name}"
            return [str(self.batch(name)), source, nrt, raw_name, members, str(path.stat().st_size),
                    MTIMES[name].isoformat(sep=" "), versions, first, last, str(fires), str(statics)]

        self.assertEqual(table_rows(self.world, "data/load_batch.tsv.gz"), [
            row(ZIP_MODIS, self.archive_dir, "MODIS_SP", "f", "2", "{6.03}", "2021-01-08", "2021-09-10", 4, 1),
            row(ZIP_SNPP, self.archive_dir, "VIIRS_SNPP_SP", "f", "2", "{2}", "2021-07-31", "2021-10-01", 4, 1),
            row(SP, self.api_dir, "VIIRS_SNPP_SP", "f", r"\N", "{2}", "2026-01-01", "2026-01-05", 3, 3),
            row(NRT_A, self.api_dir, "VIIRS_SNPP_NRT", "t", r"\N", "{2.0NRT}", "2026-01-06", "2026-01-06", 1, 0),
            row(NRT_B, self.api_dir, "VIIRS_SNPP_NRT", "t", r"\N", "{2.0NRT}", "2026-01-07", "2026-01-11", 3, 1),
        ])
        self.assertEqual(table_rows(self.testland, "data/load_batch.tsv.gz")[0],
                         row(ZIP_MODIS, self.archive_dir, "MODIS_SP", "f", "1", "{6.03}", "2021-01-08", "2021-08-02",
                             3, 1))

    def test_method_files(self) -> None:
        self.assertEqual(table_rows(self.world, "data/method/vtest/method_weight.tsv.gz")[3],
                         ["vtest", "4", "2026-11-03", r"\N", "12705", "8", r"\N", "1.0"])
        self.assertEqual(table_rows(self.world, "data/method/vtest/method_error.tsv.gz")[2],
                         ["vtest", "viirs", r"\N", "1", "0.0"])
        self.assertEqual(table_rows(self.world, "data/method/vtest/method_gap.tsv.gz"),
                         [["vtest", "2001-06-16"], ["vtest", "2001-06-17"]])
        vtest, = table_rows(self.world, "data/method/vtest/method.tsv.gz")
        self.assertEqual(vtest[:2] + vtest[3:], ["vtest", "Test version of the exporter tests", r"\N"])
        self.assertEqual(json.loads(vtest[2]), {"confidence_filter": None, "lambda": 300.0, "square_deg": 2})
        v0, = table_rows(self.world, "data/method/v0-raw/method.tsv.gz")
        self.assertEqual(json.loads(v0[2]), {"confidence_filter": None, "harmonized": False})

    def test_years(self) -> None:
        # An NRT file from 2025-12-30 to 2026-01-03 holds 2025-12-30 and 31, as no zip of 2025 is there, and loses
        # its 2026 days to the SP file.
        crossing = "VIIRS_SNPP_NRT/2025-12-30_5d.csv"
        points = POINTS + [Point("y1", T1, "2025-12-31", "1200", "N", "n", None, (crossing,), FIRE, FIRE),
                           Point("y2", T2, "2026-01-02", "1300", "N", "n", None, (crossing,), None, None)]
        archive_dir, api_dir = write_fixture(self.root / "raw-years", points,
                                             {**MTIMES, crossing: datetime(2026, 11, 14, 14, tzinfo=UTC)})

        def build(out: Path, years: tuple[int, int] | None) -> dict:
            return build_package(out, archive_dir=archive_dir, api_dir=api_dir, harmonization_dir=HARMONIZATION,
                                 methods=[], countries=None, years=years, jobs=2, name=out.name)

        every_year = self.root / "dump" / "every-year"
        build(every_year, None)
        self.assertEqual([row[1] for row in table_rows(every_year, "data/hotspot/2025_snpp.tsv.gz")], ["1200"])
        only_2026 = self.root / "dump" / "only-2026"
        manifest = build(only_2026, (2026, 2026))
        self.assertEqual(part_files(only_2026),
                         ["data/hotspot/2026_snpp.tsv.gz", "data/hotspot_static/2026_snpp.tsv.gz"])
        self.assertEqual(manifest["years"], [2026, 2026])
        for rel in part_files(only_2026) + ["data/day_source.tsv.gz"]:
            self.assertEqual(table_rows(only_2026, rel),
                             [row for row in table_rows(self.world, rel) if "2026-" in row[0] + row[1]], rel)
        # The footprint comes from every zip, also outside the years: otherwise every 2026 fire would be type 3.
        self.assertEqual(table_rows(only_2026, "data/archive_cell.tsv.gz"),
                         table_rows(self.world, "data/archive_cell.tsv.gz"))
        self.assertEqual([row[1] for row in table_rows(only_2026, "data/load_batch.tsv.gz")],
                         ["VIIRS_SNPP_NRT", "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT", "VIIRS_SNPP_NRT"])
        self.assertEqual(table_rows(only_2026, "data/load_batch.tsv.gz")[0][7:], [r"\N", r"\N", r"\N", "0", "0"])
        self.assertEqual(len(manifest["sources"]), 6)
        only_2021 = self.root / "dump" / "only-2021"
        build(only_2021, (2021, 2021))
        self.assertEqual(part_files(only_2021), [rel for rel in part_files(self.world) if "/2021_" in rel])
        self.assertEqual([row[1] for row in table_rows(only_2021, "data/load_batch.tsv.gz")],
                         ["MODIS_SP", "VIIRS_SNPP_SP"])

    def test_raw_files_outside_the_repository(self) -> None:
        # The fixture lies in a temporary folder, as the raw data lies outside the application's repository.
        self.assertFalse(self.root.resolve().is_relative_to(Path(export_dump.__file__).resolve().parent))
        names = [row[3] for row in table_rows(self.world, "data/load_batch.tsv.gz")]
        self.assertEqual(names, [f"archive/{ZIP_MODIS}", f"archive/{ZIP_SNPP}", f"api/{SP}", f"api/{NRT_A}",
                                 f"api/{NRT_B}"])
        self.assertEqual([source["file"] for source in self.world_manifest["sources"]], sorted(names))
        for package in (self.world, self.testland):
            text = ((package / "manifest.json").read_text(encoding="utf-8")
                    + gzip.decompress((package / "data" / "load_batch.tsv.gz").read_bytes()).decode())
            self.assertNotIn(str(self.root), text)

    def test_source_times(self) -> None:
        # manifest.json gives the time of a raw file in whole seconds, load_batch keeps it as the file system has it.
        points = [Point("t1", T1, "2021-08-01", "0049", "Aqua", "59", "0", (f"{ZIP_MODIS}/Testland",), FIRE, FIRE)]
        mtimes = {ZIP_MODIS: MTIMES[ZIP_MODIS] + timedelta(microseconds=123456)}
        with tempfile.TemporaryDirectory() as tmp:
            archive_dir, api_dir = write_fixture(Path(tmp), points, mtimes)
            out = Path(tmp) / "package"
            manifest = build_package(out, archive_dir=archive_dir, api_dir=api_dir, harmonization_dir=HARMONIZATION,
                                     methods=[], countries=None, years=None, jobs=1, name="times")
            self.assertEqual(manifest["sources"][0]["mtime"], "2026-11-14T12:52:00Z")
            self.assertEqual(table_rows(out, "data/load_batch.tsv.gz")[0][6], "2026-11-14 12:52:00.123456+00:00")

    def test_json_is_ascii(self) -> None:
        # jsonb text goes in ASCII, so its bytes do not depend on the client encoding of psql.
        field = export._field({"note": "Київ", "lambda": 300.0})
        self.assertTrue(field.isascii(), field)
        self.assertEqual(json.loads(field.replace("\\\\", "\\")), {"note": "Київ", "lambda": 300.0})

    def test_unknown_country(self) -> None:
        out = self.root / "dump" / "typo"
        with self.assertRaisesRegex(ValueError, "Nowhereland"):
            self.build(out, methods=[], countries=["Testland", "Nowhereland"], jobs=1)
        self.assertFalse(out.exists())
        with self.assertRaisesRegex(ValueError, "Testlan\\b"):  # a country is matched whole
            self.build(out, methods=[], countries=["Testlan"], jobs=1)

    def test_cli(self) -> None:
        out = self.root / "dump" / "cli"
        argv = ["--out", str(out), "--countries", "Testland,Otherland", "--years", "2021-2026", "--method", "vtest",
                "--jobs", "2", "--archive", str(self.archive_dir), "--api", str(self.api_dir),
                "--harmonization", str(HARMONIZATION)]
        quiet = mock.patch("logging.basicConfig")  # main would leave a log handler for the other tests
        quiet.start()
        self.addCleanup(quiet.stop)
        self.assertEqual(export_dump.main(argv), 0)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["name"], manifest["scope"], manifest["countries"], manifest["methods"]),
                         ("cli", "countries", ["Otherland", "Testland"], ["vtest"]))
        self.assertEqual(export_dump.main(argv[:3] + ["Nowhereland"] + argv[4:]), 1)
        self.assertEqual(export_dump.main(["--out", str(out), "--name", "v0", "--years", "2021", "--archive",
                                           str(self.archive_dir), "--api", str(self.api_dir)]), 0)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["name"], manifest["scope"], manifest["years"], manifest["methods"]),
                         ("v0", "world", [2021, 2021], ["v0-raw"]))


class TestArchiveYearOverApi(unittest.TestCase):
    """A zip of a family and year holds every day of that year: the API files of the family keep none of them."""

    def test_zip_and_api_of_one_year(self) -> None:
        zip_name, modis_sp, modis_nrt = ("modis_2026_all_countries.zip", "MODIS_SP/2026-01-01_5d.csv",
                                         "MODIS_NRT/2026-01-03_5d.csv")
        snpp_sp = "VIIRS_SNPP_SP/2026-01-01_5d.csv"
        points = [
            Point("z1", T1, "2026-01-02", "0830", "Terra", "60", "0", (f"{zip_name}/Testland", modis_sp), FIRE, FIRE),
            Point("z2", T2, "2026-01-03", "1015", "Aqua", "70", "0",
                  (f"{zip_name}/Testland", modis_sp, modis_nrt), FIRE, FIRE),
            Point("p1", T1, "2026-01-04", "1300", "Aqua", "80", "0", (modis_sp,), None, None),
            Point("p2", T2, "2026-01-07", "100", "Terra", "40", None, (modis_nrt,), None, None),
            Point("v1", T1, "2026-01-02", "1048", "N", "n", "0", (snpp_sp,), FIRE, FIRE),
        ]
        mtime = datetime(2026, 11, 14, 12, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            archive_dir, api_dir = write_fixture(Path(tmp), points, {name: mtime + timedelta(minutes=n) for n, name in
                                                                    enumerate([zip_name, modis_sp, modis_nrt,
                                                                               snpp_sp])})
            out = Path(tmp) / "package"
            build_package(out, archive_dir=archive_dir, api_dir=api_dir, harmonization_dir=HARMONIZATION, methods=[],
                          countries=None, years=None, jobs=2, name="one-year")
            ids = assign_batches(list_archive(archive_dir, None) + list_api(api_dir, None))
            zip_id, snpp_id = ids[archive_dir / zip_name], ids[api_dir / snpp_sp]
            found = Counter()
            for rel in part_files(out):
                for row in table_rows(out, rel):
                    found[tuple(row[:3] + row[4:6])] += 1
                    self.assertEqual(int(row[15]), snpp_id if row[2] == "3" else zip_id)
            self.assertEqual(found, Counter(key(p) for p in points if p.world is not None))
            self.assertEqual(table_rows(out, "data/day_source.tsv.gz"),
                             [["1", "2026-01-02", "f", str(zip_id)], ["2", "2026-01-03", "f", str(zip_id)]]
                             + [["3", f"2026-01-0{d}", "f", str(snpp_id)] for d in range(1, 6)])
            batches = {row[3]: (row[10], row[11]) for row in table_rows(out, "data/load_batch.tsv.gz")}
            self.assertEqual(batches[f"api/{modis_sp}"], ("0", "0"))
            self.assertEqual(batches[f"api/{modis_nrt}"], ("0", "0"))


class TestRefusedRows(unittest.TestCase):
    """A row that the precedence of the files cannot place stops the export, and no package is left behind."""

    def test_refused(self) -> None:
        testland = f"{ZIP_MODIS}/Testland"
        noaa20 = "VIIRS_NOAA20_NRT/2026-01-01_5d.csv"
        zip_point = Point("x0", T1, "2021-08-01", "1200", "Aqua", "50", "0", (testland,), FIRE, FIRE)
        cases = {
            "an API row outside the days of its file's name": [
                zip_point, Point("x1", T1, "2026-01-07", "1200", "N", "n", "0", (SP,), FIRE, FIRE)],
            "a Suomi NPP row in a file of NOAA-20": [
                zip_point, Point("x2", T1, "2026-01-02", "1200", "N", "n", None, (noaa20,), FIRE, FIRE)],
            "a row of 2020 in the zip of 2021": [
                Point("x3", T1, "2020-12-31", "1200", "Aqua", "50", "0", (testland,), FIRE, FIRE)],
        }
        for case, points in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                archive_dir, api_dir = write_fixture(Path(tmp), points, {**MTIMES, noaa20: MTIMES[SP]})
                out = Path(tmp) / "package"
                with self.assertRaises(ValueError):
                    build_package(out, archive_dir=archive_dir, api_dir=api_dir, harmonization_dir=HARMONIZATION,
                                  methods=[], countries=None, years=None, jobs=1, name="refused")
                self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["api", "archive"])


class TestMethod(unittest.TestCase):
    def test_v0_raw_rows(self) -> None:
        tables = method.v0_raw()
        self.assertEqual(sorted(tables), ["method", "method_weight"])
        (version, label, params, created_at), = tables["method"]
        self.assertEqual((version, params, created_at), ("v0-raw", {"confidence_filter": None, "harmonized": False},
                                                         None))
        self.assertTrue(label)
        weights = tables["method_weight"]
        self.assertEqual(len(weights), 4 * 194_400)
        segments = Counter((w[1], w[2], w[3]) for w in weights)
        self.assertEqual(segments, {
            (1, date(2000, 11, 1), date(2002, 7, 3)): 16200 * 12,
            (2, date(2002, 7, 4), date(2012, 1, 19)): 16200 * 12,
            (3, date(2012, 1, 20), date(2026, 11, 2)): 16200 * 12,
            (4, date(2026, 11, 3), None): 16200 * 12,
        })
        self.assertEqual({(w[0], w[6], w[7]) for w in weights}, {("v0-raw", None, 1.0)})
        self.assertEqual(len({(w[1], w[4], w[5]) for w in weights}), len(weights))
        self.assertEqual({w[4] for w in weights}, set(range(16200)))
        self.assertEqual({w[5] for w in weights}, set(range(1, 13)))

    def test_read_version(self) -> None:
        tables = method.read_version(HARMONIZATION / "vtest")
        self.assertEqual(sorted(tables), ["method", "method_error", "method_factor", "method_gap", "method_weight"])
        self.assertEqual(tables["method"], [("vtest", "Test version of the exporter tests",
                                             {"confidence_filter": None, "lambda": 300.0, "square_deg": 2}, None)])
        self.assertEqual(tables["method_weight"], [
            ("vtest", 1, date(2000, 11, 1), date(2002, 7, 3), 12705, 8, None, 1.3),
            ("vtest", 2, date(2002, 7, 4), date(2012, 1, 19), 12705, 8, None, 2.25),
            ("vtest", 3, date(2012, 1, 20), date(2026, 11, 2), 12705, 8, None, 1.0),
            ("vtest", 4, date(2026, 11, 3), None, 12705, 8, None, 1.0)])
        self.assertEqual(tables["method_factor"], [
            ("vtest", 1, 12705, 8, 1.3, 120, 156, 0.2857142857142857, 1.4, 800, 1.5, 1.6),
            ("vtest", 2, 12705, 8, 2.25, 40, 90, 0.11764705882352941, 2.0, 350, None, 2.2)])
        self.assertEqual(tables["method_error"], [
            ("vtest", "modis", 1, 1, 0.7438362781729015), ("vtest", "modis", 2, 1, 0.6884399544841339),
            ("vtest", "viirs", None, 1, 0.0)])
        self.assertEqual(tables["method_gap"], [("vtest", date(2001, 6, 16)), ("vtest", date(2001, 6, 17))])

    def test_read_version_refuses(self) -> None:
        cases = {
            "a satellite that is not a code": ("method_weight.csv", "vtest,terra,", "vtest,Terra,"),
            "a row of another version": ("method_gap.csv", "2001-06-17,vtest", "2001-06-17,vother"),
            "an unknown column": ("method_gap.csv", "day,version", "day,version,note"),
            "a missing column": ("method_error.csv", "n_min,rel_error", "n_min"),
            "an empty value of a column that is not NULL": ("method_weight.csv", ",,1.3", ",,"),
            "a number that is not a number": ("method_factor.csv", "1.3,120", "1.3,12x"),
            "a value that is not finite": ("method_factor.csv", "1.3,120", "nan,120"),
        }
        for case, (name, old, new) in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / "vtest"
                shutil.copytree(HARMONIZATION / "vtest", folder)
                text = (folder / name).read_text(encoding="utf-8")
                self.assertIn(old, text)
                (folder / name).write_text(text.replace(old, new, 1), encoding="utf-8")
                with self.assertRaises(ValueError):
                    method.read_version(folder)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "vother"
            shutil.copytree(HARMONIZATION / "vtest", folder)
            with self.assertRaisesRegex(ValueError, "vtest"):  # method.json names another version than its folder
                method.read_version(folder)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "vtest"
            shutil.copytree(HARMONIZATION / "vtest", folder)
            (folder / "method_gap.csv").unlink()
            with self.assertRaises(FileNotFoundError):
                method.read_version(folder)


if __name__ == "__main__":
    unittest.main()
