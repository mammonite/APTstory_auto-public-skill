#!/usr/bin/env python3
"""Unit tests for aptstory_web_cli helpers (no live network)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib import error


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "aptstory_web_cli.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("aptstory_web_cli", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli = load_cli()


class NormalizeBaseUrlTests(unittest.TestCase):
    def test_strips_trailing_slash(self):
        self.assertEqual(
            cli.normalize_base_url("https://demo.aptstory.com/"),
            "https://demo.aptstory.com",
        )

    def test_rejects_missing_scheme(self):
        with self.assertRaises(ValueError):
            cli.normalize_base_url("demo.aptstory.com")


class DateValidationTests(unittest.TestCase):
    def test_valid_date(self):
        self.assertEqual(cli.validate_date("2026-03-10"), "2026-03-10")

    def test_rejects_non_iso_shape(self):
        with self.assertRaises(SystemExit):
            cli.validate_date("2026/03/10")

    def test_rejects_impossible_calendar_date(self):
        with self.assertRaises(SystemExit):
            cli.validate_date("2026-02-30")

    def test_date_range_order(self):
        start, end = cli.validate_date_range("2026-03-10", "2026-03-12")
        self.assertEqual((start, end), ("2026-03-10", "2026-03-12"))

    def test_rejects_inverted_range(self):
        with self.assertRaises(SystemExit):
            cli.validate_date_range("2026-03-12", "2026-03-10")


class CarNoTests(unittest.TestCase):
    def test_strips_spaces(self):
        self.assertEqual(cli.normalize_car_no("12 가 3456"), "12가3456")

    def test_strict_accepts_common_plate(self):
        self.assertEqual(cli.normalize_car_no("12가3456", strict=True), "12가3456")

    def test_strict_rejects_garbage(self):
        with self.assertRaises(SystemExit):
            cli.normalize_car_no("ABC", strict=True)

    def test_non_strict_allows_custom(self):
        self.assertEqual(cli.normalize_car_no("TEMP-1", strict=False), "TEMP-1")


class ApiErrorParsingTests(unittest.TestCase):
    def test_as_api_error_reads_nested_message(self):
        err = cli.AptStoryClient._as_api_error(
            400, {"error": {"status": 400, "message": "bad request"}}
        )
        self.assertEqual(err.status, 400)
        self.assertEqual(err.message, "bad request")

    def test_read_json_error_fallback(self):
        http_err = error.HTTPError(
            url="https://example.com",
            code=500,
            msg="server error",
            hdrs=None,
            fp=mock.Mock(read=mock.Mock(return_value=b"not-json")),
        )
        payload = cli.AptStoryClient._read_json_error(http_err)
        self.assertEqual(payload["error"]["status"], 500)
        self.assertEqual(payload["error"]["message"], "not-json")


class BuildApiUrlTests(unittest.TestCase):
    def test_appends_query(self):
        client = cli.AptStoryClient(
            base_url="https://demo.aptstory.com",
            username="u",
            password="p",
        )
        url = client._build_api_url("/parking/visit", {"page": 1, "limit": 5})
        self.assertTrue(url.startswith("https://demo.aptstory.com/comExec/api/index.php"))
        self.assertIn("api_path=/v2/parking/visit", url)
        self.assertIn("page=1", url)
        self.assertIn("limit=5", url)


class ArgParseTests(unittest.TestCase):
    def test_create_visit_requires_dates(self):
        with self.assertRaises(SystemExit):
            cli.parse_args(["create-visit", "--car-no", "12가3456"])

    def test_update_visit_parses(self):
        args = cli.parse_args(
            [
                "update-visit",
                "99",
                "--car-no",
                "12가3456",
                "--start-date",
                "2026-03-10",
                "--end-date",
                "2026-03-11",
            ]
        )
        self.assertEqual(args.command, "update-visit")
        self.assertEqual(args.visit_id, 99)


class ClientJsonDecodeTests(unittest.TestCase):
    def test_invalid_json_becomes_runtime_error(self):
        client = cli.AptStoryClient(
            base_url="https://demo.aptstory.com",
            username="u",
            password="p",
        )

        class FakeResp:
            def read(self):
                return b"<html>oops</html>"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch.object(client.opener, "open", return_value=FakeResp()):
            with self.assertRaises(RuntimeError):
                client._api_json("GET", "/parking/settings")


if __name__ == "__main__":
    unittest.main()
