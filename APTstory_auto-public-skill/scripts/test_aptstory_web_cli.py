#!/usr/bin/env python3
"""Unit tests for aptstory_web_cli helpers (no live network)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib import error


SCRIPT_PATH = Path(__file__).resolve().parent / "aptstory_web_cli.py"


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

    def test_korean_relative_dates(self):
        today = dt.date(2026, 3, 10)
        self.assertEqual(
            cli.resolve_date("오늘", today=today),
            "2026-03-10",
        )
        self.assertEqual(
            cli.resolve_date("내일", today=today),
            "2026-03-11",
        )
        self.assertEqual(
            cli.resolve_date("모레", today=today),
            "2026-03-12",
        )
        self.assertEqual(
            cli.resolve_date("+3", today=today),
            "2026-03-13",
        )

    def test_english_relative_dates(self):
        today = dt.date(2026, 3, 10)
        self.assertEqual(cli.resolve_date("today", today=today), "2026-03-10")
        self.assertEqual(cli.resolve_date("tomorrow", today=today), "2026-03-11")


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


class PhoneAndPayloadTests(unittest.TestCase):
    def test_normalize_phone(self):
        self.assertEqual(cli.normalize_phone("010-1234-5678"), "01012345678")

    def test_visit_payload(self):
        payload = cli.build_visit_payload(
            "12가3456",
            "2026-03-10",
            "2026-03-10",
            visitor_phone_no="010-1111-2222",
            memo="손님",
        )
        self.assertEqual(payload["visitorPhoneNo"], "01011112222")
        self.assertEqual(payload["memo"], "손님")


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

    def test_ensure_api_success_raises_on_embedded_error(self):
        with self.assertRaises(cli.ApiError):
            cli.ensure_api_success({"error": {"status": 403, "message": "denied"}})

    def test_ensure_api_success_raises_on_success_false(self):
        with self.assertRaises(cli.ApiError):
            cli.ensure_api_success({"success": False, "message": "nope"})


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
                "내일",
                "--end-date",
                "모레",
            ]
        )
        self.assertEqual(args.command, "update-visit")
        self.assertEqual(args.visit_id, 99)
        self.assertEqual(args.start_date, "내일")

    def test_update_bookmark_parses(self):
        args = cli.parse_args(
            ["update-bookmark", "7", "--car-no", "12가3456", "--title", "부모님"]
        )
        self.assertEqual(args.command, "update-bookmark")
        self.assertEqual(args.bookmark_id, 7)


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

    def test_empty_body_returns_empty_dict(self):
        client = cli.AptStoryClient(
            base_url="https://demo.aptstory.com",
            username="u",
            password="p",
        )

        class FakeResp:
            def read(self):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch.object(client.opener, "open", return_value=FakeResp()):
            self.assertEqual(client._api_json("DELETE", "/parking/visit/1"), {})


class FormatTextTests(unittest.TestCase):
    def test_list_visits_table(self):
        text = cli.format_text(
            "list-visits",
            {
                "list": [
                    {
                        "visitId": 1,
                        "carNo": "12가3456",
                        "visitStartDate": "2026-03-10",
                        "visitEndDate": "2026-03-10",
                        "memo": "손님",
                    }
                ]
            },
        )
        self.assertIn("12가3456", text)
        self.assertIn("손님", text)


class DotEnvTests(unittest.TestCase):
    def test_load_dotenv_does_not_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("APTSTORY_USERNAME=from-file\n", encoding="utf-8")
            with mock.patch.dict(cli.os.environ, {"APTSTORY_USERNAME": "existing"}, clear=False):
                cli.load_dotenv(path)
                self.assertEqual(cli.os.environ["APTSTORY_USERNAME"], "existing")

    def test_load_dotenv_sets_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('APTSTORY_BASE_URL="https://demo.aptstory.com"\n', encoding="utf-8")
            with mock.patch.dict(cli.os.environ, {}, clear=False):
                cli.os.environ.pop("APTSTORY_BASE_URL", None)
                cli.load_dotenv(path)
                self.assertEqual(
                    cli.os.environ["APTSTORY_BASE_URL"],
                    "https://demo.aptstory.com",
                )


class LoginTests(unittest.TestCase):
    def test_login_success_when_logout_marker_present(self):
        client = cli.AptStoryClient(
            base_url="https://demo.aptstory.com",
            username="u",
            password="p",
        )
        responses = iter(["login page", "ok", '<a href="/member/logout.apt">out</a>'])

        def fake_request_text(*args, **kwargs):
            return next(responses)

        with mock.patch.object(client, "_request_text", side_effect=fake_request_text):
            client.login()

    def test_login_fails_without_marker(self):
        client = cli.AptStoryClient(
            base_url="https://demo.aptstory.com",
            username="u",
            password="p",
        )
        with mock.patch.object(client, "_request_text", return_value="nope"):
            with self.assertRaises(RuntimeError):
                client.login()


if __name__ == "__main__":
    unittest.main()
