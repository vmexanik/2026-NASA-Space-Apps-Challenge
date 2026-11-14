import datetime as dt
import io
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from firms import (
    BASE_URL,
    WORLD,
    AreaChunk,
    BoundingBox,
    FirmsClient,
    FirmsConfigError,
    FirmsHTTPError,
    FirmsNetworkError,
    FirmsResponseError,
    Source,
    load_map_key,
    merge_csv,
    split_dates,
)

HEADER = "latitude,longitude,bright_ti4,acq_date"
UKRAINE = BoundingBox(22, 44, 40.5, 52.5)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeOpener:
    """Answers each call with the next answer: a body string, an
    (HTTP code, body) tuple or an exception."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.urls = []

    def __call__(self, url, *, timeout):
        self.urls.append(url)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, tuple):
            code, body = answer
            raise urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(body.encode()))
        return FakeResponse(answer.encode())


def make_client(*answers, retries=3):
    opener = FakeOpener(*answers)
    sleeps = []
    client = FirmsClient("KEY", retries=retries, opener=opener, sleep=sleeps.append)
    return client, opener, sleeps


class SplitDatesTest(unittest.TestCase):
    def test_splits_into_five_day_chunks(self):
        chunks = split_dates(dt.date(2024, 1, 1), dt.date(2024, 1, 12))
        self.assertEqual(chunks, [
            (dt.date(2024, 1, 1), 5),
            (dt.date(2024, 1, 6), 5),
            (dt.date(2024, 1, 11), 2),
        ])

    def test_single_day(self):
        day = dt.date(2024, 2, 29)
        self.assertEqual(split_dates(day, day), [(day, 1)])

    def test_end_before_start(self):
        with self.assertRaises(ValueError):
            split_dates(dt.date(2024, 1, 2), dt.date(2024, 1, 1))


class BoundingBoxTest(unittest.TestCase):
    def test_world(self):
        self.assertIs(BoundingBox.parse("World"), WORLD)
        self.assertEqual(WORLD.to_path(), "world")
        self.assertEqual(BoundingBox(-180, -90, 180, 90).to_path(), "world")

    def test_bbox(self):
        box = BoundingBox.parse("22, 44, 40.5, 52.5")
        self.assertEqual(box, UKRAINE)
        self.assertEqual(box.to_path(), "22,44,40.5,52.5")

    def test_bad_bbox(self):
        for text in ("1,2,3", "40,44,22,52", "22,95,40,96", "north"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                BoundingBox.parse(text)


class AreaChunkTest(unittest.TestCase):
    def test_end_rows_and_count(self):
        chunk = AreaChunk(dt.date(2024, 1, 1), 5, HEADER + "\n1,2,3,2024-01-01\n")
        self.assertEqual(chunk.end, dt.date(2024, 1, 5))
        self.assertEqual(chunk.row_count, 1)
        self.assertEqual(chunk.rows()[0]["acq_date"], "2024-01-01")

    def test_empty_chunk(self):
        self.assertEqual(AreaChunk(dt.date(2024, 1, 1), 1, HEADER + "\n").row_count, 0)


class ClientTest(unittest.TestCase):
    def test_chunk_builds_url_with_date(self):
        client, opener, _ = make_client(HEADER + "\n")
        client.chunk(Source.MODIS_SP, WORLD, dt.date(2020, 8, 1), 5)
        self.assertEqual(
            opener.urls[0], BASE_URL + "/api/area/csv/KEY/MODIS_SP/world/5/2020-08-01"
        )

    def test_latest_has_no_date_in_url(self):
        client, opener, _ = make_client(HEADER + "\n")
        chunk = client.latest(Source.VIIRS_NOAA20_NRT, UKRAINE, 2)
        self.assertEqual(
            opener.urls[0],
            BASE_URL + "/api/area/csv/KEY/VIIRS_NOAA20_NRT/22,44,40.5,52.5/2",
        )
        self.assertEqual(chunk.end, dt.datetime.now(dt.UTC).date())

    def test_day_range_is_checked_before_the_request(self):
        client, opener, _ = make_client()
        for days in (0, 6):
            with self.subTest(days=days), self.assertRaises(ValueError):
                client.latest(Source.MODIS_NRT, WORLD, days)
        self.assertEqual(opener.urls, [])

    def test_iter_range_pauses_between_requests(self):
        client, opener, sleeps = make_client(HEADER + "\n", HEADER + "\n")
        chunks = list(client.iter_range(
            Source.MODIS_SP, WORLD, dt.date(2024, 1, 1), dt.date(2024, 1, 7), pause=0.5
        ))
        self.assertEqual([(c.start, c.day_count) for c in chunks],
                         [(dt.date(2024, 1, 1), 5), (dt.date(2024, 1, 6), 2)])
        self.assertTrue(opener.urls[1].endswith("/world/2/2024-01-06"))
        self.assertEqual(sleeps, [0.5])

    def test_http_error_carries_status_and_body(self):
        client, _, _ = make_client((400, "Invalid MAP_KEY."))
        with self.assertRaises(FirmsHTTPError) as ctx:
            client.latest(Source.MODIS_NRT)
        self.assertEqual((ctx.exception.status, ctx.exception.body), (400, "Invalid MAP_KEY."))

    def test_text_instead_of_csv_is_an_error(self):
        client, _, _ = make_client("Invalid area coordinates.")
        with self.assertRaisesRegex(FirmsResponseError, "Invalid area"):
            client.latest(Source.MODIS_NRT)

    def test_retries_on_503_then_succeeds(self):
        client, opener, sleeps = make_client((503, "busy"), HEADER + "\n")
        client.latest(Source.MODIS_NRT)
        self.assertEqual(len(opener.urls), 2)
        self.assertEqual(sleeps, [2])

    def test_gives_up_after_retries(self):
        err = urllib.error.URLError("down")
        client, opener, _ = make_client(err, err, retries=1)
        with self.assertRaises(FirmsNetworkError):
            client.latest(Source.MODIS_NRT)
        self.assertEqual(len(opener.urls), 2)

    def test_key_status(self):
        client, _, _ = make_client(
            '{"transaction_limit": 5000, "current_transactions": 31,'
            ' "transaction_interval": "10 minutes"}'
        )
        status = client.key_status()
        self.assertEqual(status.remaining, 4969)

    def test_availability(self):
        client, opener, _ = make_client(
            "data_id,min_date,max_date\nMODIS_SP,2000-11-01,2026-08-31\n"
        )
        items = client.availability(Source.MODIS_SP)
        self.assertTrue(opener.urls[0].endswith("/api/data_availability/csv/KEY/MODIS_SP"))
        self.assertEqual(items[0].min_date, dt.date(2000, 11, 1))

    def test_repr_hides_key(self):
        self.assertNotIn("KEY", repr(FirmsClient("KEY"))[len("FirmsClient"):])


class LoadMapKeyTest(unittest.TestCase):
    def test_env_var_wins_over_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("FIRMS_MAP_KEY=from_file\n")
            with mock.patch.dict(os.environ, {"FIRMS_MAP_KEY": "from_env"}):
                self.assertEqual(load_map_key(env_file), "from_env")
            with mock.patch.dict(os.environ, {"FIRMS_MAP_KEY": ""}):
                self.assertEqual(load_map_key(env_file), "from_file")

    def test_no_key(self):
        with mock.patch.dict(os.environ, {"FIRMS_MAP_KEY": ""}):
            with self.assertRaises(FirmsConfigError):
                load_map_key(Path("/nonexistent/.env"))


class MergeCsvTest(unittest.TestCase):
    def test_keeps_one_header(self):
        out = io.StringIO()
        rows = merge_csv([HEADER + "\n1,2,3,a\n", HEADER + "\n", HEADER + "\n4,5,6,b\n"], out)
        self.assertEqual(rows, 2)
        self.assertEqual(out.getvalue(), HEADER + "\n1,2,3,a\n4,5,6,b\n")

    def test_different_headers_are_refused(self):
        with self.assertRaises(FirmsResponseError):
            merge_csv([HEADER + "\n", HEADER + ",type\n"], io.StringIO())


if __name__ == "__main__":
    unittest.main()
