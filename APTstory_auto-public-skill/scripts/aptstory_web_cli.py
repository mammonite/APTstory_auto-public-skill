#!/usr/bin/env python3

import argparse
import datetime as dt
import getpass
import json
import os
import sys
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Any, Dict, Optional
from urllib import error, parse, request


DEFAULT_TIMEOUT = 15


@dataclass
class ApiError(Exception):
    status: int
    message: str
    payload: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        return f"{self.status}: {self.message}"


class AptStoryClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.api_base = f"{self.base_url}/comExec/api/index.php?api_path=/v2"
        self.cookie_jar = CookieJar()
        self.opener = request.build_opener(request.HTTPCookieProcessor(self.cookie_jar))
        self.default_headers = {
            "User-Agent": "aptstory-web-cli/0.1",
            "Accept": "application/json, text/plain, */*",
        }

    def login(self) -> None:
        self._request_text("GET", "/")
        self._request_text(
            "POST",
            "/comExec/procLogin.php",
            form_body={"tbID": self.username, "tbPWD": self.password},
        )
        root_html = self._request_text("GET", "/")
        if "/member/logout.apt" not in root_html:
            raise RuntimeError("login failed: logout marker not found")

    def get_settings(self) -> Dict[str, Any]:
        return self._api_json("GET", "/parking/settings")

    def list_visits(
        self,
        page: int = 1,
        limit: int = 10,
        car_no: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = {"page": page, "limit": limit}
        if car_no:
            query["carNo"] = car_no
        return self._api_json("GET", "/parking/visit", query=query)

    def get_visit(self, visit_id: int) -> Dict[str, Any]:
        return self._api_json("GET", f"/parking/visit/{visit_id}")

    def create_visit(
        self,
        car_no: str,
        visit_start_date: str,
        visit_end_date: str,
        visitor_phone_no: str = "",
        memo: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "carNo": car_no,
            "visitorPhoneNo": visitor_phone_no,
            "visitStartDate": visit_start_date,
            "visitEndDate": visit_end_date,
            "memo": memo,
        }
        return self._api_json("POST", "/parking/visit", json_body=payload)

    def delete_visit(self, visit_id: int) -> Dict[str, Any]:
        return self._api_json("DELETE", f"/parking/visit/{visit_id}")

    def list_bookmarks(self, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        return self._api_json("GET", "/parking/bookmark", query={"page": page, "limit": limit})

    def _api_json(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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
                return json.loads(body)
        except error.HTTPError as exc:
            payload = self._read_json_error(exc)
            raise self._as_api_error(exc.code, payload) from exc

    def _request_text(
        self,
        method: str,
        path: str,
        form_body: Optional[Dict[str, str]] = None,
    ) -> str:
        url = f"{self.base_url}{path}"
        headers = dict(self.default_headers)
        data = None
        if form_body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = parse.urlencode(form_body).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method=method)
        with self.opener.open(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8")

    def _build_api_url(
        self,
        path: str,
        query: Optional[Dict[str, Any]] = None,
    ) -> str:
        url = f"{self.api_base}{path}"
        if query:
            clean_query = {key: value for key, value in query.items() if value is not None}
            if clean_query:
                url = f"{url}&{parse.urlencode(clean_query)}"
        return url

    @staticmethod
    def _read_json_error(exc: error.HTTPError) -> Dict[str, Any]:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"error": {"status": exc.code, "message": body}}

    @staticmethod
    def _as_api_error(status: int, payload: Dict[str, Any]) -> ApiError:
        error_block = payload.get("error", payload)
        message = error_block.get("message", "request failed")
        return ApiError(status=status, message=message, payload=payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AptStory web client for visitor parking reservations."
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
        help="Login password. Falls back to APTSTORY_PASSWORD.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("settings", help="Fetch parking settings")

    list_visits_parser = subparsers.add_parser("list-visits", help="List visitor reservations")
    list_visits_parser.add_argument("--page", type=int, default=1)
    list_visits_parser.add_argument("--limit", type=int, default=10)
    list_visits_parser.add_argument("--car-no", default=None)

    get_visit_parser = subparsers.add_parser("get-visit", help="Fetch one visitor reservation")
    get_visit_parser.add_argument("visit_id", type=int)

    create_visit_parser = subparsers.add_parser("create-visit", help="Create one visitor reservation")
    create_visit_parser.add_argument("--car-no", required=True)
    create_visit_parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    create_visit_parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    create_visit_parser.add_argument("--visitor-phone-no", default="")
    create_visit_parser.add_argument("--memo", default="")

    delete_visit_parser = subparsers.add_parser("delete-visit", help="Delete one visitor reservation")
    delete_visit_parser.add_argument("visit_id", type=int)

    list_bookmarks_parser = subparsers.add_parser("list-bookmarks", help="List parking bookmarks")
    list_bookmarks_parser.add_argument("--page", type=int, default=1)
    list_bookmarks_parser.add_argument("--limit", type=int, default=10)

    return parser.parse_args()


def validate_date(value: str) -> str:
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"invalid date: {value}") from exc
    return value


def print_json(data: Dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


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
    return AptStoryClient(base_url=base_url, username=username, password=password)


def main() -> int:
    args = parse_args()
    client = build_client(args)
    try:
        client.login()
        if args.command == "settings":
            print_json(client.get_settings())
        elif args.command == "list-visits":
            print_json(client.list_visits(page=args.page, limit=args.limit, car_no=args.car_no))
        elif args.command == "get-visit":
            print_json(client.get_visit(args.visit_id))
        elif args.command == "create-visit":
            print_json(
                client.create_visit(
                    car_no=args.car_no,
                    visit_start_date=validate_date(args.start_date),
                    visit_end_date=validate_date(args.end_date),
                    visitor_phone_no=args.visitor_phone_no,
                    memo=args.memo,
                )
            )
        elif args.command == "delete-visit":
            print_json(client.delete_visit(args.visit_id))
        elif args.command == "list-bookmarks":
            print_json(client.list_bookmarks(page=args.page, limit=args.limit))
        else:
            raise SystemExit(f"unsupported command: {args.command}")
        return 0
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        if exc.payload:
            print_json(exc.payload)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
