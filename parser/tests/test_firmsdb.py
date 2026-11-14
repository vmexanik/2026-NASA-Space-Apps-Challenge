"""Tests of the firmsdb package, which turns FIRMS files into the dump package, and of the grid it uses."""

from __future__ import annotations

import csv
import io
import json
import unittest
from datetime import date
from pathlib import Path

from firms import grid
from firmsdb import rows

GRID_POINTS = Path(__file__).with_name("data") / "grid_points.json"

#: ((lat_e5, lon_e5), cell_id): the corners of the globe, its origin and a point in Kyiv.
POINTS = [((-9000000, -18000000), 0), ((9000000, 18000000), 1036799),
          ((0, 0), 519120), ((5045000, 3050000), 808682)]

#: Sample rows of docs/data-standard.md: the MODIS archive (Aqua, Ukraine) and VIIRS NRT (NOAA-20).
MODIS_ARCHIVE = {"latitude": "47.5888", "longitude": "31.5712", "brightness": "304.2",
                 "scan": "2.6", "track": "1.6", "acq_date": "2021-08-01", "acq_time": "0049",
                 "satellite": "Aqua", "instrument": "MODIS", "confidence": "59", "version": "6.03",
                 "bright_t31": "288", "frp": "28.4", "daynight": "N", "type": "0"}
VIIRS_NRT = {"latitude": "48.29334", "longitude": "39.91782", "bright_ti4": "297.61",
             "scan": "0.37", "track": "0.58", "acq_date": "2026-11-14", "acq_time": "28",
             "satellite": "N20", "instrument": "VIIRS", "confidence": "n", "version": "2.0NRT",
             "bright_ti5": "282.11", "frp": "0.37", "daynight": "N"}


def changed(row: dict[str, str], **values: str) -> dict[str, str]:
    """A copy of row with some values replaced."""
    return {**row, **values}


def without(row: dict[str, str], column: str) -> dict[str, str]:
    """A copy of row without one column."""
    return {name: value for name, value in row.items() if name != column}


class TestGrid(unittest.TestCase):
    def test_points(self) -> None:  # tests/data/grid_points.json holds the same rows
        for (lat, lon), cid in POINTS:
            self.assertEqual(grid.cell_id_e5(lat, lon), cid)
            self.assertEqual(grid.cell_id(lat / 1e5, lon / 1e5), cid)
        self.assertEqual(grid.cell2_id(808682), 12705)
        self.assertEqual(grid.cell8_id(12705), 791)
        self.assertEqual(grid.cell_bounds(808682), (30.5, 50.25, 30.75, 50.5))

    def test_points_file(self) -> None:
        points = json.loads(GRID_POINTS.read_text())
        cells = {(p["lat_e5"], p["lon_e5"]): p["cell_id"] for p in points}
        for lat_lon, cid in POINTS:
            self.assertEqual(cells.get(lat_lon), cid)
        for p in points:
            with self.subTest(lat_e5=p["lat_e5"], lon_e5=p["lon_e5"]):
                lat, lon = p["lat_e5"] / 1e5, p["lon_e5"] / 1e5
                self.assertEqual(grid.cell_id_e5(p["lat_e5"], p["lon_e5"]), p["cell_id"])
                self.assertEqual(grid.cell_id(lat, lon), p["cell_id"])
                self.assertEqual(grid.cell2_id(p["cell_id"]), p["cell2_id"])
                self.assertEqual(grid.cell8_id(p["cell2_id"]), p["cell8_id"])
                bounds = west, south, east, north = grid.cell_bounds(p["cell_id"])
                self.assertTrue(west <= lon < east or lon == east == 180.0, bounds)
                self.assertTrue(south <= lat < north or lat == north == 90.0, bounds)

    def test_outside_the_globe(self) -> None:
        for lat_e5, lon_e5 in [(9000001, 0), (-9000001, 0), (0, 18000001), (0, -18000001)]:
            with self.subTest(lat_e5=lat_e5, lon_e5=lon_e5), self.assertRaises(ValueError):
                grid.cell_id_e5(lat_e5, lon_e5)
        with self.assertRaises(ValueError):
            grid.cell_id(-90.00001, 0.0)


class TestRows(unittest.TestCase):
    def test_to_e5(self) -> None:
        self.assertEqual(rows.to_e5("48.74919"), 4874919)
        self.assertEqual(rows.to_e5("-12.0288"), -1202880)
        self.assertEqual(rows.to_e5("30"), 3000000)
        self.assertEqual(rows.to_e5("-0.5"), -50000)
        with self.assertRaises(ValueError):
            rows.to_e5("1.123456")
        # FIRMS writes a coordinate nearer 0 than 0.0001 in exponent form, in the archive and the API.
        self.assertEqual([rows.to_e5(text) for text in ["4e-05", "-7e-05", "1e-05"]], [4, -7, 1])
        for text in ["", "abc", " 30", "30.", ".5", "+1", "1,5", "--1", "1e-06", "1.5e-05", "1E-05"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                rows.to_e5(text)

    def test_detection_columns(self) -> None:  # the columns of hotspot, then type
        self.assertEqual(rows.Detection._fields, (
            "acq_date", "acq_time", "satellite", "cell_id", "lat_e5", "lon_e5", "frp", "brightness",
            "brightness_2", "scan", "track", "conf_class", "conf_pct", "is_day", "is_nrt", "batch_id",
            "type"))

    def test_satellites(self) -> None:
        self.assertEqual(rows.SATELLITES, {
            "Terra": 1, "T": 1, "terra": 1, "Aqua": 2, "A": 2, "aqua": 2, "N": 3, "snpp": 3,
            "N20": 4, "noaa20": 4, "N21": 5, "noaa21": 5})
        self.assertEqual(rows.CODES, {1: "terra", 2: "aqua", 3: "snpp", 4: "noaa20", 5: "noaa21"})
        for name, sid in [("T", 1), ("A", 2)]:
            d = rows.parse_row(changed(MODIS_ARCHIVE, satellite=name), is_nrt=False, batch_id=1)
            self.assertEqual(d.satellite, sid)

    def test_parse_modis_archive(self) -> None:
        d = rows.parse_row(MODIS_ARCHIVE, is_nrt=False, batch_id=7)
        self.assertEqual((d.acq_date, d.acq_time, d.satellite, d.lat_e5, d.lon_e5),
                         (date(2021, 8, 1), 49, 2, 4758880, 3157120))
        self.assertEqual((d.conf_class, d.conf_pct, d.is_day, d.type, d.brightness_2),
                         ("n", 59, False, 0, 288.0))
        self.assertEqual(d, rows.Detection(date(2021, 8, 1), 49, 2, 792846, 4758880, 3157120, 28.4, 304.2,
                                           288.0, 2.6, 1.6, "n", 59, False, False, 7, 0))
        terra = {"latitude": "48.7114", "longitude": "38.0979", "brightness": "330.6", "scan": "1",
                 "track": "1", "acq_date": "2021-08-01", "acq_time": "0832", "satellite": "Terra",
                 "instrument": "MODIS", "confidence": "63", "version": "6.03", "bright_t31": "310.4",
                 "frp": "15.6", "daynight": "D", "type": "0"}
        self.assertEqual(rows.parse_row(terra, is_nrt=False, batch_id=7),
                         rows.Detection(date(2021, 8, 1), 832, 1, 798632, 4871140, 3809790, 15.6, 330.6,
                                        310.4, 1.0, 1.0, "n", 63, True, False, 7, 0))

    def test_parse_viirs_nrt(self) -> None:
        d = rows.parse_row(VIIRS_NRT, is_nrt=True, batch_id=1)
        self.assertEqual((d.acq_time, d.satellite, d.conf_class, d.conf_pct, d.type, d.is_nrt),
                         (28, 4, "n", None, None, True))
        self.assertEqual(d, rows.Detection(date(2026, 11, 14), 28, 4, 797199, 4829334, 3991782, 0.37, 297.61,
                                           282.11, 0.37, 0.58, "n", None, False, True, 1, None))
        noaa21 = changed(VIIRS_NRT, latitude="51.89175", longitude="29.34097", acq_time="113",
                         satellite="N21")
        d = rows.parse_row(noaa21, is_nrt=True, batch_id=1)
        self.assertEqual((d.acq_time, d.satellite, d.lat_e5, d.lon_e5), (113, 5, 5189175, 2934097))
        near_origin = changed(VIIRS_NRT, latitude="-4e-05", longitude="7e-05")
        d = rows.parse_row(near_origin, is_nrt=True, batch_id=1)
        self.assertEqual((d.lat_e5, d.lon_e5, d.cell_id), (-4, 7, 517680))

    def test_modis_confidence_classes(self) -> None:
        for pct, cls in [("0", "l"), ("29", "l"), ("30", "n"), ("79", "n"), ("80", "h"), ("100", "h")]:
            with self.subTest(pct=pct):
                d = rows.parse_row(changed(MODIS_ARCHIVE, confidence=pct), is_nrt=False, batch_id=1)
                self.assertEqual((d.conf_class, d.conf_pct), (cls, int(pct)))

    def test_viirs_confidence_classes(self) -> None:
        for cls in ["l", "n", "h"]:
            d = rows.parse_row(changed(VIIRS_NRT, confidence=cls), is_nrt=True, batch_id=1)
            self.assertEqual((d.conf_class, d.conf_pct), (cls, None))

    def test_unknown_values_fail(self) -> None:
        cases = [
            ("satellite X", changed(MODIS_ARCHIVE, satellite="X"), False),
            ("daynight Q", changed(MODIS_ARCHIVE, daynight="Q"), False),
            ("VIIRS confidence z", changed(VIIRS_NRT, confidence="z"), True),
            ("VIIRS confidence in capitals", changed(VIIRS_NRT, confidence="N"), True),
            ("MODIS confidence above 100", changed(MODIS_ARCHIVE, confidence="101"), False),
            ("MODIS confidence as a letter", changed(MODIS_ARCHIVE, confidence="n"), False),
            ("type 4", changed(MODIS_ARCHIVE, type="4"), False),
            ("empty type", changed(MODIS_ARCHIVE, type=""), False),
            ("archive row without type", without(MODIS_ARCHIVE, "type"), False),
            ("VIIRS row without bright_ti5", without(VIIRS_NRT, "bright_ti5"), True),
            ("acq_time hour 24", changed(MODIS_ARCHIVE, acq_time="2400"), False),
            ("acq_time minute 60", changed(MODIS_ARCHIVE, acq_time="0960"), False),
            ("acq_time of five digits", changed(VIIRS_NRT, acq_time="00028"), True),
            ("empty acq_time", changed(VIIRS_NRT, acq_time=""), True),
            ("acq_date month 13", changed(MODIS_ARCHIVE, acq_date="2021-13-01"), False),
            ("latitude with six decimals", changed(MODIS_ARCHIVE, latitude="47.588801"), False),
            ("latitude beyond the pole", changed(MODIS_ARCHIVE, latitude="90.00001"), False),
            ("longitude beyond 180", changed(MODIS_ARCHIVE, longitude="-180.5"), False),
            ("frp not a number", changed(MODIS_ARCHIVE, frp="x"), False),
        ]
        for name, row, is_nrt in cases:
            with self.subTest(name), self.assertRaises(ValueError):
                rows.parse_row(row, is_nrt=is_nrt, batch_id=1)

    def test_short_rows_fail(self) -> None:
        def read(values: list[str]) -> dict[str, str]:  # csv.DictReader puts None in the missing fields
            return next(csv.DictReader(io.StringIO(",".join(MODIS_ARCHIVE) + "\n" + ",".join(values) + "\n")))

        values = list(MODIS_ARCHIVE.values())
        self.assertEqual(rows.parse_row(read(values), is_nrt=False, batch_id=1),
                         rows.parse_row(MODIS_ARCHIVE, is_nrt=False, batch_id=1))
        for name, kept in [("cut before type", 14), ("cut after instrument", 9)]:
            with self.subTest(name), self.assertRaises(ValueError):
                rows.parse_row(read(values[:kept]), is_nrt=False, batch_id=1)

    def test_number_columns(self) -> None:
        for text, value in [("288", 288.0), ("28.4", 28.4), ("5e-05", 5e-05)]:
            self.assertEqual(rows.parse_row(changed(MODIS_ARCHIVE, frp=text), is_nrt=False, batch_id=1).frp,
                             value)
        for text in ["nan", "inf", "infinity", "-inf", " 28.4", "28.4 ", "2_8.4", "", ".5", "28.", "1,5"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                rows.parse_row(changed(MODIS_ARCHIVE, frp=text), is_nrt=False, batch_id=1)
        columns = [(MODIS_ARCHIVE, False, name) for name in ["brightness", "bright_t31", "scan", "track"]]
        columns += [(VIIRS_NRT, True, name) for name in ["bright_ti4", "bright_ti5"]]
        for row, is_nrt, column in columns:
            with self.subTest(column=column), self.assertRaises(ValueError):
                rows.parse_row(changed(row, **{column: "nan"}), is_nrt=is_nrt, batch_id=1)

    def test_codes_are_not_firms_values(self) -> None:
        cases = [("terra", MODIS_ARCHIVE, False), ("aqua", MODIS_ARCHIVE, False), ("snpp", VIIRS_NRT, True),
                 ("noaa20", VIIRS_NRT, True), ("noaa21", VIIRS_NRT, True)]
        for code, row, is_nrt in cases:
            with self.subTest(code=code), self.assertRaises(ValueError):
                rows.parse_row(changed(row, satellite=code), is_nrt=is_nrt, batch_id=1)

    def test_static_type(self) -> None:
        def archive(kind: str) -> rows.Detection:
            return rows.parse_row(changed(MODIS_ARCHIVE, type=kind), is_nrt=False, batch_id=1)

        nrt = rows.parse_row(VIIRS_NRT, is_nrt=True, batch_id=1)
        sp = rows.parse_row(changed(VIIRS_NRT, version="2", type="0"), is_nrt=False, batch_id=1)
        self.assertEqual(rows.static_type(archive("2"), True), 2)
        self.assertIsNone(rows.static_type(archive("0"), True))
        self.assertEqual(rows.static_type(nrt, False), 3)
        self.assertIsNone(rows.static_type(nrt, True))
        self.assertEqual(rows.static_type(sp, False), 3)
        for kind in ["1", "2", "3"]:  # FIRMS's own type stays, in the footprint and outside it
            for in_footprint in [True, False]:
                self.assertEqual(rows.static_type(archive(kind), in_footprint), int(kind))


if __name__ == "__main__":
    unittest.main()
