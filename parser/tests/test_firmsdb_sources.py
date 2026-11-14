"""Tests of firmsdb.sources and firmsdb.precedence: the raw FIRMS files the exporter reads, and which file holds
each day of each family of satellites, so that every point gets into the dump package once."""

from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from firmsdb.precedence import assign_batches, keeps, winners
from firmsdb.sources import SourceFile, archive_members, list_api, list_archive, read_rows

#: When every file the tests write was changed last.
MTIME = datetime(2026, 11, 14, 20, 15, tzinfo=UTC)

#: A VIIRS NRT file of the area API as FIRMS writes it: acq_time without leading zeros, no newline after the last
#: line.
VIIRS_NRT = ("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
             "bright_ti5,frp,daynight\n"
             "48.29334,39.91782,297.61,0.37,0.58,2026-10-30,28,N20,VIIRS,n,2.0NRT,282.11,0.37,N\n"
             "-33.99026,22.43891,305.28,0.49,0.4,2026-10-31,113,N20,VIIRS,h,2.0NRT,281.04,1.44,D")
NRT_ROWS = [
    {"latitude": "48.29334", "longitude": "39.91782", "bright_ti4": "297.61", "scan": "0.37", "track": "0.58",
     "acq_date": "2026-10-30", "acq_time": "28", "satellite": "N20", "instrument": "VIIRS", "confidence": "n",
     "version": "2.0NRT", "bright_ti5": "282.11", "frp": "0.37", "daynight": "N"},
    {"latitude": "-33.99026", "longitude": "22.43891", "bright_ti4": "305.28", "scan": "0.49", "track": "0.4",
     "acq_date": "2026-10-31", "acq_time": "113", "satellite": "N20", "instrument": "VIIRS", "confidence": "h",
     "version": "2.0NRT", "bright_ti5": "281.04", "frp": "1.44", "daynight": "D"},
]

#: Two country members of a MODIS yearly archive, one row each.
MODIS_HEADER = ("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
                "bright_t31,frp,daynight,type\n")
UKRAINE = MODIS_HEADER + "47.5888,31.5712,304.2,2.6,1.6,2021-08-01,0049,Aqua,MODIS,59,6.03,288,28.4,N,0\n"
POLAND = MODIS_HEADER + "52.2297,21.0122,310.1,1,1,2021-08-02,1015,Terra,MODIS,85,6.03,295,12.5,D,2\n"
UKRAINE_ROW = {"latitude": "47.5888", "longitude": "31.5712", "brightness": "304.2", "scan": "2.6", "track": "1.6",
               "acq_date": "2021-08-01", "acq_time": "0049", "satellite": "Aqua", "instrument": "MODIS",
               "confidence": "59", "version": "6.03", "bright_t31": "288", "frp": "28.4", "daynight": "N",
               "type": "0"}

#: The source and family of each zip prefix, as list_archive gives them.
ZIP_PREFIXES = {"modis": ("MODIS_SP", "modis"), "viirs-snpp": ("VIIRS_SNPP_SP", "snpp"),
                "viirs-jpss1": ("VIIRS_NOAA20_SP", "noaa20")}


def write(path: Path, text: str) -> Path:
    """A file at path that holds text and was changed last at MTIME."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    os.utime(path, (MTIME.timestamp(), MTIME.timestamp()))
    return path


def write_zip(path: Path, members: dict[str, str]) -> Path:
    """A zip at path that holds members and was changed last at MTIME; a member name that ends in / is a folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            if name.endswith("/"):
                archive.mkdir(name)
            else:
                archive.writestr(name, text)
    os.utime(path, (MTIME.timestamp(), MTIME.timestamp()))
    return path


def api(source: str, family: str, start: str, days: int, minute: int) -> SourceFile:
    """The API file <source>/<start>_<days>d.csv, changed last at 2026-11-14 12:<minute> UTC."""
    return SourceFile(path=Path("api", source, f"{start}_{days}d.csv"), source_code=source, family=family,
                      is_nrt=source.endswith("_NRT"), year=None, first_day=date.fromisoformat(start), days=days,
                      size=0, mtime=datetime(2026, 11, 14, 12, minute, tzinfo=UTC))


def archive(prefix: str, year: int, hour: int = 20) -> SourceFile:
    """The yearly archive <prefix>_<year>_all_countries.zip, changed last at 2026-11-14 <hour>:00 UTC."""
    source_code, family = ZIP_PREFIXES[prefix]
    return SourceFile(path=Path("archive", f"{prefix}_{year}_all_countries.zip"), source_code=source_code,
                      family=family, is_nrt=False, year=year, first_day=None, days=None, size=0,
                      mtime=datetime(2026, 11, 14, hour, tzinfo=UTC))


class TestSources(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.archive_dir = self.root / "archive"
        self.api_dir = self.root / "api"

    def test_api_name(self) -> None:
        path = write(self.api_dir / "VIIRS_NOAA20_NRT" / "2026-10-30_4d.csv", VIIRS_NRT)
        self.assertEqual(list_api(self.api_dir, None), [SourceFile(
            path=path, source_code="VIIRS_NOAA20_NRT", family="noaa20", is_nrt=True, year=None,
            first_day=date(2026, 10, 30), days=4, size=len(VIIRS_NRT), mtime=MTIME)])

    def test_api_sources(self) -> None:
        sources = {"MODIS_SP": ("modis", False), "MODIS_NRT": ("modis", True),
                   "VIIRS_SNPP_SP": ("snpp", False), "VIIRS_SNPP_NRT": ("snpp", True),
                   "VIIRS_NOAA20_SP": ("noaa20", False), "VIIRS_NOAA20_NRT": ("noaa20", True),
                   "VIIRS_NOAA21_SP": ("noaa21", False), "VIIRS_NOAA21_NRT": ("noaa21", True)}
        for source in sources:
            write(self.api_dir / source / "2026-11-01_5d.csv", VIIRS_NRT)
        self.assertEqual({src.source_code: (src.family, src.is_nrt) for src in list_api(self.api_dir, None)},
                         sources)

    def test_archive_name(self) -> None:
        def zip_file(prefix: str, source_code: str, family: str) -> SourceFile:
            path = self.archive_dir / f"{prefix}_2021_all_countries.zip"
            return SourceFile(path=path, source_code=source_code, family=family, is_nrt=False, year=2021,
                              first_day=None, days=None, size=path.stat().st_size, mtime=MTIME)

        for prefix in ("modis", "viirs-snpp", "viirs-jpss1"):
            write_zip(self.archive_dir / f"{prefix}_2021_all_countries.zip", {f"{prefix}/2021/": ""})
        self.assertEqual(list_archive(self.archive_dir, None), [zip_file("modis", "MODIS_SP", "modis"),
                                                                zip_file("viirs-jpss1", "VIIRS_NOAA20_SP", "noaa20"),
                                                                zip_file("viirs-snpp", "VIIRS_SNPP_SP", "snpp")])

    def test_years(self) -> None:
        for year in (2020, 2021, 2022):
            write_zip(self.archive_dir / f"modis_{year}_all_countries.zip", {f"modis/{year}/": ""})
        # 2020-12-27_5d ends on 2020-12-31; 2020-12-30_5d holds 2021-01-01..03 as well.
        for name in ("2020-12-27_5d.csv", "2020-12-30_5d.csv", "2021-12-30_2d.csv", "2022-01-01_5d.csv"):
            write(self.api_dir / "MODIS_NRT" / name, VIIRS_NRT)
        self.assertEqual([src.year for src in list_archive(self.archive_dir, (2021, 2021))], [2021])
        self.assertEqual([src.path.name for src in list_api(self.api_dir, (2021, 2021))],
                         ["2020-12-30_5d.csv", "2021-12-30_2d.csv"])
        self.assertEqual(len(list_api(self.api_dir, None)), 4)

    def test_downloads_in_progress_skipped(self) -> None:  # fetch_archive.py and fetch_current_year.py write .part
        write(self.archive_dir / "modis_2026_all_countries.zip.part", "")
        write(self.api_dir / "MODIS_NRT" / "2026-11-10_5d.csv.part", "")
        self.assertEqual(list_archive(self.archive_dir, None), [])
        self.assertEqual(list_api(self.api_dir, None), [])

    def test_unknown_files_fail(self) -> None:
        for case, name in enumerate(("api/LANDSAT_NRT/2026-11-01_5d.csv",  # not a source of this database
                                     "api/MODIS_NRT/latest.csv",
                                     "api/MODIS_NRT/2026-11-01_0d.csv",
                                     "api/MODIS_NRT/2026-02-30_5d.csv",
                                     "archive/viirs-noaa21_2025_all_countries.zip",  # no such prefix yet
                                     "archive/modis_2021.zip")):
            with self.subTest(name=name):
                root = self.root / str(case)
                write(root / name, "")
                folder, _ = name.split("/", 1)
                lister = list_api if folder == "api" else list_archive
                with self.assertRaises(ValueError):
                    lister(root / folder, None)

    def test_missing_folder_fails(self) -> None:
        for lister in (list_archive, list_api):
            with self.subTest(lister=lister.__name__), self.assertRaises(FileNotFoundError):
                lister(self.root / "missing", None)

    def test_archive_members_countries(self) -> None:
        write_zip(self.archive_dir / "modis_2021_all_countries.zip", {
            "modis/2021/": "", "modis/2021/modis_2021_Poland.csv": POLAND,
            "modis/2021/modis_2021_Ukraine.csv": UKRAINE, "modis/2021/AttributesReadme.txt": "columns"})
        [src] = list_archive(self.archive_dir, None)
        self.assertEqual(archive_members(src, ["Ukraine"]), ["modis/2021/modis_2021_Ukraine.csv"])
        self.assertEqual(archive_members(src, None),
                         ["modis/2021/modis_2021_Poland.csv", "modis/2021/modis_2021_Ukraine.csv"])

    def test_archive_members_exact_country(self) -> None:  # FIRMS has all four of these countries
        write_zip(self.archive_dir / "viirs-snpp_2021_all_countries.zip", {
            f"viirs-snpp/2021/viirs-snpp_2021_{country}.csv": UKRAINE
            for country in ("Equatorial_Guinea", "Guinea", "Guinea-Bissau", "Papua_New_Guinea")})
        [src] = list_archive(self.archive_dir, None)
        self.assertEqual(archive_members(src, ["Guinea"]), ["viirs-snpp/2021/viirs-snpp_2021_Guinea.csv"])

    def test_archive_member_not_a_country_fails(self) -> None:
        write_zip(self.archive_dir / "modis_2021_all_countries.zip", {
            "modis/2021/modis_2021_Ukraine.csv": UKRAINE, "modis/2021/countries/modis_2021_Poland.csv": POLAND})
        [src] = list_archive(self.archive_dir, None)
        with self.assertRaises(ValueError):
            archive_members(src, ["Ukraine"])

    def test_read_rows(self) -> None:
        write(self.api_dir / "VIIRS_NOAA20_NRT" / "2026-10-30_4d.csv", VIIRS_NRT)
        write_zip(self.archive_dir / "modis_2021_all_countries.zip", {
            "modis/2021/modis_2021_Poland.csv": POLAND, "modis/2021/modis_2021_Ukraine.csv": UKRAINE})
        [api_src] = list_api(self.api_dir, None)
        [zip_src] = list_archive(self.archive_dir, None)
        self.assertEqual(list(read_rows(api_src)), NRT_ROWS)
        self.assertEqual(list(read_rows(zip_src, "modis/2021/modis_2021_Ukraine.csv")), [UKRAINE_ROW])

    def test_read_rows_errors(self) -> None:
        cases = (("the last row loses its daynight", VIIRS_NRT.rsplit(",", 1)[0]),
                 ("the first row gains a field", VIIRS_NRT.replace("2.0NRT", "2.0,NRT", 1)),
                 ("an empty file", ""))
        for case, (label, text) in enumerate(cases):
            with self.subTest(label):
                write(self.root / str(case) / "MODIS_NRT" / "2026-10-30_4d.csv", text)
                [src] = list_api(self.root / str(case), None)
                with self.assertRaises(ValueError):
                    list(read_rows(src))
        # The call itself refuses a wrong member, before a byte is read: a zip read as text would fail too, with
        # UnicodeDecodeError, which is also a ValueError.
        write_zip(self.archive_dir / "modis_2021_all_countries.zip", {"modis/2021/modis_2021_Ukraine.csv": UKRAINE})
        [zip_src] = list_archive(self.archive_dir, None)
        with self.subTest("a zip without a member"), self.assertRaises(ValueError):
            read_rows(zip_src)
        with self.subTest("a CSV file with a member"), self.assertRaises(ValueError):
            read_rows(api("MODIS_NRT", "modis", "2026-10-30", 4, minute=0), "modis_2021_Ukraine.csv")


class TestPrecedence(unittest.TestCase):
    def test_winners_sp_over_nrt(self) -> None:
        sp = api("VIIRS_SNPP_SP", "snpp", "2026-07-30", 2, minute=0)
        nrt = api("VIIRS_SNPP_NRT", "snpp", "2026-07-31", 3, minute=30)  # newer, and shares 2026-07-31
        expected = {("snpp", date(2026, 7, 30)): sp.path, ("snpp", date(2026, 7, 31)): sp.path,
                    ("snpp", date(2026, 8, 1)): nrt.path, ("snpp", date(2026, 8, 2)): nrt.path}
        for files in ([sp, nrt], [nrt, sp]):
            self.assertEqual(winners(files), expected)

    def test_winners_newer_nrt(self) -> None:
        old = api("MODIS_NRT", "modis", "2026-11-03", 5, minute=0)
        new = api("MODIS_NRT", "modis", "2026-10-31", 5, minute=30)  # shares 2026-11-03 and 2026-11-04
        expected = {("modis", date(2026, 10, 31)): new.path, ("modis", date(2026, 11, 1)): new.path,
                    ("modis", date(2026, 11, 2)): new.path, ("modis", date(2026, 11, 3)): new.path,
                    ("modis", date(2026, 11, 4)): new.path, ("modis", date(2026, 11, 5)): old.path,
                    ("modis", date(2026, 11, 6)): old.path, ("modis", date(2026, 11, 7)): old.path}
        for files in ([old, new], [new, old]):
            self.assertEqual(winners(files), expected)

    def test_winners_newer_sp(self) -> None:
        old = api("MODIS_SP", "modis", "2026-08-29", 5, minute=0)  # the later path
        new = api("MODIS_SP", "modis", "2026-08-29", 3, minute=30)  # shares 2026-08-29..31
        expected = {("modis", date(2026, 8, 29)): new.path, ("modis", date(2026, 8, 30)): new.path,
                    ("modis", date(2026, 8, 31)): new.path, ("modis", date(2026, 9, 1)): old.path,
                    ("modis", date(2026, 9, 2)): old.path}
        for files in ([old, new], [new, old]):
            self.assertEqual(winners(files), expected)

    def test_winners_per_family(self) -> None:
        modis = api("MODIS_SP", "modis", "2026-10-30", 2, minute=0)
        snpp = api("VIIRS_SNPP_NRT", "snpp", "2026-10-30", 2, minute=30)
        noaa20 = api("VIIRS_NOAA20_NRT", "noaa20", "2026-10-30", 2, minute=15)
        self.assertEqual(winners([modis, snpp, noaa20]), {
            ("modis", date(2026, 10, 30)): modis.path, ("modis", date(2026, 10, 31)): modis.path,
            ("snpp", date(2026, 10, 30)): snpp.path, ("snpp", date(2026, 10, 31)): snpp.path,
            ("noaa20", date(2026, 10, 30)): noaa20.path, ("noaa20", date(2026, 10, 31)): noaa20.path})

    def test_winners_same_mtime_deterministic(self) -> None:
        first = api("MODIS_NRT", "modis", "2026-10-31", 5, minute=0)
        second = api("MODIS_NRT", "modis", "2026-11-03", 5, minute=0)  # as new as the first
        self.assertEqual(winners([first, second]), winners([second, first]))

    def test_winners_archive_year(self) -> None:
        zip_2026 = archive("modis", 2026, hour=11)  # older than every API file below
        sp = api("MODIS_SP", "modis", "2026-08-29", 3, minute=30)
        nrt = api("MODIS_NRT", "modis", "2026-12-30", 5, minute=45)  # its last 3 days are in 2027
        noaa20 = api("VIIRS_NOAA20_NRT", "noaa20", "2026-10-30", 5, minute=0)
        win = winners([sp, zip_2026, nrt, noaa20])
        year_2026 = {("modis", date(2026, 1, 1) + timedelta(days=offset)): zip_2026.path for offset in range(365)}
        self.assertEqual(win, {
            **year_2026,
            ("modis", date(2027, 1, 1)): nrt.path, ("modis", date(2027, 1, 2)): nrt.path,
            ("modis", date(2027, 1, 3)): nrt.path,
            ("noaa20", date(2026, 10, 30)): noaa20.path, ("noaa20", date(2026, 10, 31)): noaa20.path,
            ("noaa20", date(2026, 11, 1)): noaa20.path, ("noaa20", date(2026, 11, 2)): noaa20.path,
            ("noaa20", date(2026, 11, 3)): noaa20.path})
        self.assertFalse(any(keeps(src, day, win) for src in (sp, nrt) for _, day in year_2026))
        self.assertTrue(keeps(nrt, date(2027, 1, 1), win))
        self.assertTrue(keeps(noaa20, date(2026, 10, 30), win))
        self.assertTrue(keeps(zip_2026, date(2026, 8, 30), win))
        leap = winners([archive("viirs-jpss1", 2024)])
        self.assertEqual((len(leap), max(leap)), (366, ("noaa20", date(2024, 12, 31))))

    def test_keeps(self) -> None:
        zip_2025 = archive("modis", 2025)
        old = api("MODIS_NRT", "modis", "2026-11-03", 5, minute=0)
        new = api("MODIS_NRT", "modis", "2026-10-31", 5, minute=30)
        win = winners([zip_2025, old, new])
        self.assertTrue(keeps(zip_2025, date(2025, 6, 1), win))
        self.assertTrue(keeps(zip_2025, date(2026, 11, 3), win))  # a zip keeps every row, whatever win holds
        self.assertTrue(keeps(new, date(2026, 11, 3), win))
        self.assertTrue(keeps(old, date(2026, 11, 5), win))
        self.assertFalse(keeps(old, date(2026, 11, 3), win))  # won by the newer file
        self.assertFalse(keeps(old, date(2026, 11, 8), win))  # not a day of its name

    def test_batches_deterministic(self) -> None:
        sp = api("MODIS_SP", "modis", "2026-01-01", 5, minute=0)  # day 9497 from 2000-01-01
        nrt = api("MODIS_NRT", "modis", "2026-09-01", 5, minute=0)  # day 9740
        zip_2025 = archive("modis", 2025)
        expected = {sp.path: 1_000_949_725, nrt.path: 1_000_974_035, zip_2025.path: 20251}
        for files in ([sp, nrt, zip_2025], [zip_2025, nrt, sp], [nrt, zip_2025, sp]):
            self.assertEqual(assign_batches(files), expected)

    def test_batch_ids(self) -> None:  # 2026-10-30 is day 9799 from 2000-01-01
        files = {archive("modis", 2021): 20211, archive("viirs-snpp", 2021): 20212,
                 archive("viirs-jpss1", 2021): 20213,
                 api("MODIS_SP", "modis", "2026-10-30", 5, minute=0): 1_000_979_925,
                 api("VIIRS_SNPP_SP", "snpp", "2026-10-30", 4, minute=0): 1_000_979_944,
                 api("VIIRS_NOAA20_NRT", "noaa20", "2026-10-30", 5, minute=0): 1_000_979_975,
                 api("VIIRS_NOAA21_NRT", "noaa21", "2026-10-30", 5, minute=0): 1_000_979_995}
        self.assertEqual(assign_batches(list(files)), {src.path: number for src, number in files.items()})

    def test_batch_ids_same_start_other_days(self) -> None:  # a grown SP chunk: 2026-08-29 is day 9737
        three = api("MODIS_SP", "modis", "2026-08-29", 3, minute=0)
        five = api("MODIS_SP", "modis", "2026-08-29", 5, minute=30)
        self.assertEqual(assign_batches([three, five]), {three.path: 1_000_973_723, five.path: 1_000_973_725})

    def test_batch_ids_stable_across_lists(self) -> None:  # a world package, then a one-year package of 2026
        sp = api("MODIS_SP", "modis", "2026-01-01", 5, minute=0)
        nrt = api("MODIS_NRT", "modis", "2026-09-01", 5, minute=0)
        world = assign_batches([archive("modis", 2021), sp, nrt])
        one_year = assign_batches([nrt, api("MODIS_NRT", "modis", "2026-11-10", 5, minute=0), sp])
        self.assertEqual((one_year[sp.path], one_year[nrt.path]), (world[sp.path], world[nrt.path]))

    def test_batch_ids_refused(self) -> None:
        one = api("MODIS_NRT", "modis", "2026-10-30", 5, minute=0)
        no_days = replace(archive("modis", 2021), year=None)
        cases = (("ten days", [api("MODIS_NRT", "modis", "2026-10-30", 10, minute=0)]),
                 ("no days", [api("MODIS_NRT", "modis", "2026-10-30", 0, minute=0)]),
                 ("one id for two files", [one, replace(one, path=Path("copy", "2026-10-30_5d.csv"))]),
                 ("neither a year nor days", [no_days]))
        for label, files in cases:
            with self.subTest(label), self.assertRaises(ValueError):
                assign_batches(files)
        with self.subTest("winners: neither a year nor days"), self.assertRaises(ValueError):
            winners([no_days])


if __name__ == "__main__":
    unittest.main()
