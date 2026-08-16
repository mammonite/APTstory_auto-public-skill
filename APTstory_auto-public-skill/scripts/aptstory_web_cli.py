#!/usr/bin/env python3
"""AptStory web client for visitor parking reservations.

Uses the apartment-specific website session (cookie login), not the mobile app.
"""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import re
import sys
from http.cookiejar import CookieJar
from typing import Any, Optional
from urllib import error, parse, request
from urllib.parse import urlparse


DEFAULT_TIMEOUT = 15
USER_AGENT = "aptstory-web-cli/0.2"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Korean plate patterns commonly seen in AptStory payloads (loose check).
CAR_NO_RE = re.compile(
    r"^(\d{2,3}[가-힣]\d{4}|\d{2}[가-힣]{1,2}\d{4}|[가-힣]{2}\d{2}[가-힣]\d{4})$"
)


class ApiError(Exception):
    """Raised when the AptStory API returns an HTTP error response."""

    def __init__(
        self,
        status: int,
        message: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        self.status = status
        self.message = message
        self.payload = payload
        super().__init__(f"{status}: {message}")


class AptStoryClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self.username = username
        self.password = password
        self.timeout = timeout
        self.api_base = f"{self.base_url}/comExec/api/index.php?api_path=/v2"
        self.cookie_jar = CookieJar()
        self.opener = request.build_opener(request.HTTPCookieProcessor(self.cookie_jar))
        self.default_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        }

    def login(self) -> None:
        try:
            self._request_text("GET", "/")
            self._request_text(
                "POST",
                "/comExec/procLogin.php",
                form_body={"tbID": self.username, "tbPWD": self.password},
            )
            root_html = self._request_text("GET", "/")
        except error.HTTPError as exc:
            raise RuntimeError(f"login failed: HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"login failed: network error ({exc.reason})") from exc

        if "/member/logout.apt" not in root_html:
            raise RuntimeError("login failed: logout marker not found (check credentials)")

    def get_settings(self) -> dict[str, Any]:
        return self._api_json("GET", "/parking/settings")

    def list_visits(
        self,
        page: int = 1,
        limit: int = 10,
        car_no: Optional[str] = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"page": page, "limit": limit}
        if car_no:
            query["carNo"] = car_no
        return self._api_json("GET", "/parking/visit", query=query)

    def get_visit(self, visit_id: int) -> dict[str, Any]:
        return self._api_json("GET", f"/parking/visit/{visit_id}")

    def create_visit(
        self,
        car_no: str,
        visit_start_date: str,
        visit_end_date: str,
        visitor_phone_no: str = "",
        memo: str = "",
    ) -> dict[str, Any]:
        payload = {
            "carNo": car_no,
            "visitorPhoneNo": visitor_phone_no,
            "visitStartDate": visit_start_date,
            "visitEndDate": visit_end_date,
            "memo": memo,
        }
        return self._api_json("POST", "/parking/visit", json_body=payload)

    def update_visit(
        self,
        visit_id: int,
        car_no: str,
        visit_start_date: str,
        visit_end_date: str,
        visitor_phone_no: str = "",
        memo: str = "",
    ) -> dict[str, Any]:
        payload = {
            "carNo": car_no,
            "visitorPhoneNo": visitor_phone_no,
            "visitStartDate": visit_start_date,
            "visitEndDate": visit_end_date,
            "memo": memo,
        }
        return self._api_json("PUT", f"/parking/visit/{visit_id}", json_body=payload)

    def delete_visit(self, visit_id: int) -> dict[str, Any]:
        return self._api_json("DELETE", f"/parking/visit/{visit_id}")

    def list_bookmarks(self, page: int = 1, limit: int = 10) -> dict[str, Any]:
        return self._api_json(
            "GET", "/parking/bookmark", query={"page": page, "limit": limit}
        )

    def create_bookmark(
        self,
        car_no: str,
        title: str = "",
        visitor_phone_no: str = "",
        memo: str = "",
    ) -> dict[str, Any]:
        payload = {
            "carNo": car_no,
            "title": title,
            "visitorPhoneNo": visitor_phone_no,
            "memo": memo,
        }
        return self._api_json("POST", "/parking/bookmark", json_body=payload)

    def delete_bookmark(self, bookmark_id: int) -> dict[str, Any]:
        return self._api_json("DELETE", f"/parking/bookmark/{bookmark_id}")

    def _api_json(
        self,
        method: str,
        path: str,
        query: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = self._build_api_url(path, query)
        headers = dict(self.default_headers)
        data = None
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            payload = self._read_json_error(exc)
            raise self._as_api_error(exc.code, payload) from exc
        except error.URLError as exc:
            raise RuntimeError(f"network error: {exc.reason}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid JSON response from {path}") from exc

    def _request_text(
        self,
        method: str,
        path: str,
        form_body: Optional[dict[str, str]] = None,
    ) -> str:
        url = f"{self.base_url}{path}"
        headers = dict(self.default_headers)
        data = None
        if form_body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = parse.urlencode(form_body).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method=method)
        with self.opener.open(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _build_api_url(
        self,
        path: str,
        query: Optional[dict[str, Any]] = None,
    ) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        url = f"{self.api_base}{path}"
        if query:
            clean_query = {
                key: value for key, value in query.items() if value is not None
            }
            if clean_query:
                url = f"{url}&{parse.urlencode(clean_query)}"
        return url

    @staticmethod
    def _read_json_error(exc: error.HTTPError) -> dict[str, Any]:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return parsed
            return {"error": {"status": exc.code, "message": body}}
        except json.JSONDecodeError:
            return {"error": {"status": exc.code, "message": body or "request failed"}}

    @staticmethod
    def _as_api_error(status: int, payload: dict[str, Any]) -> ApiError:
        error_block = payload.get("error", payload)
        if isinstance(error_block, dict):
            message = str(error_block.get("message") or "request failed")
        else:
            message = str(error_block) if error_block else "request failed"
        return ApiError(status=status, message=message, payload=payload)


def normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "base URL must look like https://your-apartment.aptstory.com"
        )
    return base_url


def validate_date(value: str, *, field: str = "date") -> str:
    if not DATE_RE.match(value):
        raise SystemExit(f"invalid {field}: {value} (expected YYYY-MM-DD)")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"invalid {field}: {value}") from exc
    return value


def validate_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    start = validate_date(start_date, field="start-date")
    end = validate_date(end_date, field="end-date")
    if end < start:
        raise SystemExit("end-date must be on or after start-date")
    return start, end


def normalize_car_no(value: str, *, strict: bool = False) -> str:
    car_no = re.sub(r"\s+", "", value.strip())
    if not car_no:
        raise SystemExit("car-no is required")
    if strict and not CAR_NO_RE.match(car_no):
        raise SystemExit(
            f"car-no looks invalid: {car_no} "
            "(example: 12가3456; use --allow-any-car-no to skip this check)"
        )
    return car_no


def validate_positive_int(value: int, *, field: str) -> int:
    if value < 1:
        raise SystemExit(f"{field} must be >= 1")
    return value


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AptStory web client for visitor parking reservations.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("APTSTORY_BASE_URL", ""),
        help="Apartment-specific web base URL, e.g. https://your-apartment.aptstory.com",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("APTSTORY_USERNAME", ""),
        help="Login ID. Falls back to APTSTORY_USERNAME.",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("APTSTORY_PASSWORD", ""),
        help="Login password. Prefer APTSTORY_PASSWORD env var over this flag.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--allow-any-car-no",
        action="store_true",
        help="Skip Korean plate format check for --car-no.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("settings", help="Fetch parking settings")

    list_visits_parser = subparsers.add_parser(
        "list-visits", help="List visitor reservations"
    )
    list_visits_parser.add_argument("--page", type=int, default=1)
    list_visits_parser.add_argument("--limit", type=int, default=10)
    list_visits_parser.add_argument("--car-no", default=None)

    get_visit_parser = subparsers.add_parser(
        "get-visit", help="Fetch one visitor reservation"
    )
    get_visit_parser.add_argument("visit_id", type=int)

    create_visit_parser = subparsers.add_parser(
        "create-visit", help="Create one visitor reservation"
    )
    create_visit_parser.add_argument("--car-no", required=True)
    create_visit_parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    create_visit_parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    create_visit_parser.add_argument("--visitor-phone-no", default="")
    create_visit_parser.add_argument("--memo", default="")

    update_visit_parser = subparsers.add_parser(
        "update-visit", help="Update one visitor reservation"
    )
    update_visit_parser.add_argument("visit_id", type=int)
    update_visit_parser.add_argument("--car-no", required=True)
    update_visit_parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    update_visit_parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    update_visit_parser.add_argument("--visitor-phone-no", default="")
    update_visit_parser.add_argument("--memo", default="")

    delete_visit_parser = subparsers.add_parser(
        "delete-visit", help="Delete one visitor reservation"
    )
    delete_visit_parser.add_argument("visit_id", type=int)

    list_bookmarks_parser = subparsers.add_parser(
        "list-bookmarks", help="List parking bookmarks"
    )
    list_bookmarks_parser.add_argument("--page", type=int, default=1)
    list_bookmarks_parser.add_argument("--limit", type=int, default=10)

    create_bookmark_parser = subparsers.add_parser(
        "create-bookmark", help="Create a parking bookmark"
    )
    create_bookmark_parser.add_argument("--car-no", required=True)
    create_bookmark_parser.add_argument("--title", default="")
    create_bookmark_parser.add_argument("--visitor-phone-no", default="")
    create_bookmark_parser.add_argument("--memo", default="")

    delete_bookmark_parser = subparsers.add_parser(
        "delete-bookmark", help="Delete a parking bookmark"
    )
    delete_bookmark_parser.add_argument("bookmark_id", type=int)

    return parser.parse_args(argv)


def build_client(args: argparse.Namespace) -> AptStoryClient:
    base_url = args.base_url.strip()
    username = args.username.strip()
    password = args.password
    if not base_url:
        raise SystemExit("--base-url or APTSTORY_BASE_URL is required")
    if not username:
        raise SystemExit("--username or APTSTORY_USERNAME is required")
    if not password:
        password = getpass.getpass("APTSTORY_PASSWORD: ")
    try:
        return AptStoryClient(
            base_url=base_url,
            username=username,
            password=password,
            timeout=validate_positive_int(args.timeout, field="timeout"),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _car_no_from_args(args: argparse.Namespace, raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    return normalize_car_no(raw, strict=not args.allow_any_car_no)


def run_command(client: AptStoryClient, args: argparse.Namespace) -> Any:
    if args.command == "settings":
        return client.get_settings()

    if args.command == "list-visits":
        return client.list_visits(
            page=validate_positive_int(args.page, field="page"),
            limit=validate_positive_int(args.limit, field="limit"),
            car_no=_car_no_from_args(args, args.car_no),
        )

    if args.command == "get-visit":
        return client.get_visit(validate_positive_int(args.visit_id, field="visit_id"))

    if args.command in {"create-visit", "update-visit"}:
        start_date, end_date = validate_date_range(args.start_date, args.end_date)
        car_no = normalize_car_no(args.car_no, strict=not args.allow_any_car_no)
        if args.command == "create-visit":
            return client.create_visit(
                car_no=car_no,
                visit_start_date=start_date,
                visit_end_date=end_date,
                visitor_phone_no=args.visitor_phone_no,
                memo=args.memo,
            )
        return client.update_visit(
            visit_id=validate_positive_int(args.visit_id, field="visit_id"),
            car_no=car_no,
            visit_start_date=start_date,
            visit_end_date=end_date,
            visitor_phone_no=args.visitor_phone_no,
            memo=args.memo,
        )

    if args.command == "delete-visit":
        return client.delete_visit(
            validate_positive_int(args.visit_id, field="visit_id")
        )

    if args.command == "list-bookmarks":
        return client.list_bookmarks(
            page=validate_positive_int(args.page, field="page"),
            limit=validate_positive_int(args.limit, field="limit"),
        )

    if args.command == "create-bookmark":
        return client.create_bookmark(
            car_no=normalize_car_no(args.car_no, strict=not args.allow_any_car_no),
            title=args.title,
            visitor_phone_no=args.visitor_phone_no,
            memo=args.memo,
        )

    if args.command == "delete-bookmark":
        return client.delete_bookmark(
            validate_positive_int(args.bookmark_id, field="bookmark_id")
        )

    raise SystemExit(f"unsupported command: {args.command}")


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    client = build_client(args)
    try:
        client.login()
        print_json(run_command(client, args))
        return 0
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        if exc.payload is not None:
            print_json(exc.payload)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
