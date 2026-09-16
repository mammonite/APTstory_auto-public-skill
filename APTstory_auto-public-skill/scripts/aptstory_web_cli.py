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
from pathlib import Path
from typing import Any, Optional
from urllib import error, parse, request
from urllib.parse import urlparse


DEFAULT_TIMEOUT = 15
USER_AGENT = "aptstory-web-cli/0.3"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RELATIVE_DAY_RE = re.compile(r"^\+(\d+)$")
# Korean plate patterns commonly seen in AptStory payloads (loose check).
CAR_NO_RE = re.compile(
    r"^(\d{2,3}[가-힣]\d{4}|\d{2}[가-힣]{1,2}\d{4}|[가-힣]{2}\d{2}[가-힣]\d{4})$"
)
DATE_ALIASES = {
    "today": 0,
    "tomorrow": 1,
    "오늘": 0,
    "내일": 1,
    "모레": 2,
}


class ApiError(Exception):
    """Raised when the AptStory API returns an error response."""

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
            raise RuntimeError(f"로그인 실패: HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"로그인 실패: 네트워크 오류 ({exc.reason})") from exc

        if "/member/logout.apt" not in root_html:
            raise RuntimeError(
                "로그인 실패: 로그아웃 링크를 찾지 못했습니다. "
                "아이디/비밀번호와 단지 도메인을 확인하세요."
            )

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
        return self._api_json(
            "POST",
            "/parking/visit",
            json_body=build_visit_payload(
                car_no, visit_start_date, visit_end_date, visitor_phone_no, memo
            ),
        )

    def update_visit(
        self,
        visit_id: int,
        car_no: str,
        visit_start_date: str,
        visit_end_date: str,
        visitor_phone_no: str = "",
        memo: str = "",
    ) -> dict[str, Any]:
        return self._api_json(
            "PUT",
            f"/parking/visit/{visit_id}",
            json_body=build_visit_payload(
                car_no, visit_start_date, visit_end_date, visitor_phone_no, memo
            ),
        )

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
        return self._api_json(
            "POST",
            "/parking/bookmark",
            json_body=build_bookmark_payload(car_no, title, visitor_phone_no, memo),
        )

    def update_bookmark(
        self,
        bookmark_id: int,
        car_no: str,
        title: str = "",
        visitor_phone_no: str = "",
        memo: str = "",
    ) -> dict[str, Any]:
        return self._api_json(
            "PUT",
            f"/parking/bookmark/{bookmark_id}",
            json_body=build_bookmark_payload(car_no, title, visitor_phone_no, memo),
        )

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
            raise RuntimeError(f"네트워크 오류: {exc.reason}") from exc

        if not body.strip():
            return {}

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"잘못된 JSON 응답: {path}") from exc

        if not isinstance(parsed, dict):
            raise RuntimeError(f"예상치 못한 응답 형식: {path}")
        return ensure_api_success(parsed)

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
            message = str(error_block.get("message") or "요청 실패")
        else:
            message = str(error_block) if error_block else "요청 실패"
        return ApiError(status=status, message=message, payload=payload)


def build_visit_payload(
    car_no: str,
    visit_start_date: str,
    visit_end_date: str,
    visitor_phone_no: str = "",
    memo: str = "",
) -> dict[str, str]:
    return {
        "carNo": car_no,
        "visitorPhoneNo": normalize_phone(visitor_phone_no),
        "visitStartDate": visit_start_date,
        "visitEndDate": visit_end_date,
        "memo": memo,
    }


def build_bookmark_payload(
    car_no: str,
    title: str = "",
    visitor_phone_no: str = "",
    memo: str = "",
) -> dict[str, str]:
    return {
        "carNo": car_no,
        "title": title,
        "visitorPhoneNo": normalize_phone(visitor_phone_no),
        "memo": memo,
    }


def ensure_api_success(payload: dict[str, Any]) -> dict[str, Any]:
    """Raise ApiError when the server embeds a failure inside HTTP 200 JSON."""
    if payload.get("success") is False:
        message = str(payload.get("message") or payload.get("msg") or "요청 실패")
        raise ApiError(status=400, message=message, payload=payload)

    error_block = payload.get("error")
    if isinstance(error_block, dict) and (
        error_block.get("message") or error_block.get("status")
    ):
        status = int(error_block.get("status") or 400)
        message = str(error_block.get("message") or "요청 실패")
        raise ApiError(status=status, message=message, payload=payload)

    return payload


def normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "단지 주소는 https://your-apartment.aptstory.com 형식이어야 합니다."
        )
    return base_url


def normalize_phone(value: str) -> str:
    return re.sub(r"[\s\-]", "", value.strip())


def validate_date(value: str, *, field: str = "date") -> str:
    if not DATE_RE.match(value):
        raise SystemExit(
            f"잘못된 {field}: {value} (예: 2026-03-10 / 오늘 / 내일 / +1)"
        )
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"잘못된 {field}: {value}") from exc
    return value


def resolve_date(
    value: str,
    *,
    field: str = "date",
    today: Optional[dt.date] = None,
) -> str:
    raw = value.strip()
    lowered = raw.lower()
    base = today or dt.date.today()

    if lowered in DATE_ALIASES:
        return (base + dt.timedelta(days=DATE_ALIASES[lowered])).isoformat()
    if raw in DATE_ALIASES:
        return (base + dt.timedelta(days=DATE_ALIASES[raw])).isoformat()

    relative = RELATIVE_DAY_RE.match(raw)
    if relative:
        return (base + dt.timedelta(days=int(relative.group(1)))).isoformat()

    return validate_date(raw, field=field)


def validate_date_range(
    start_date: str,
    end_date: str,
    *,
    today: Optional[dt.date] = None,
) -> tuple[str, str]:
    start = resolve_date(start_date, field="start-date", today=today)
    end = resolve_date(end_date, field="end-date", today=today)
    if end < start:
        raise SystemExit("종료일(end-date)은 시작일(start-date) 이후여야 합니다.")
    return start, end


def normalize_car_no(value: str, *, strict: bool = False) -> str:
    car_no = re.sub(r"\s+", "", value.strip())
    if not car_no:
        raise SystemExit("차량번호(--car-no)가 필요합니다.")
    if strict and not CAR_NO_RE.match(car_no):
        raise SystemExit(
            f"차량번호 형식이 이상합니다: {car_no} "
            "(예: 12가3456 / 검사 생략: --allow-any-car-no)"
        )
    return car_no


def validate_positive_int(value: int, *, field: str, maximum: Optional[int] = None) -> int:
    if value < 1:
        raise SystemExit(f"{field}는 1 이상이어야 합니다.")
    if maximum is not None and value > maximum:
        raise SystemExit(f"{field}는 {maximum} 이하여야 합니다.")
    return value


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs into os.environ without overriding existing values."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _as_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("list", "items", "data", "rows", "result"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _as_rows(value)
            if nested:
                return nested
    return []


def format_text(command: str, data: Any) -> str:
    rows = _as_rows(data)
    if command in {"list-visits", "get-visit"}:
        if command == "get-visit" and isinstance(data, dict) and not rows:
            rows = [data]
        if not rows and isinstance(data, dict):
            return "등록된 방문차량 예약이 없습니다."
        lines = ["ID        차량번호      시작일        종료일        메모"]
        lines.append("-" * 64)
        for row in rows:
            lines.append(
                f"{str(row.get('visitId', '-')):<10}"
                f"{str(row.get('carNo', '-')):<12}"
                f"{str(row.get('visitStartDate', '-')):<14}"
                f"{str(row.get('visitEndDate', '-')):<14}"
                f"{str(row.get('memo', '') or '')}"
            )
        return "\n".join(lines)

    if command in {"list-bookmarks", "create-bookmark", "update-bookmark"}:
        if command != "list-bookmarks" and isinstance(data, dict) and not rows:
            rows = [data]
        if not rows and isinstance(data, dict):
            return "등록된 즐겨찾기가 없습니다."
        lines = ["ID        차량번호      제목"]
        lines.append("-" * 40)
        for row in rows:
            lines.append(
                f"{str(row.get('bookmarkId', '-')):<10}"
                f"{str(row.get('carNo', '-')):<12}"
                f"{str(row.get('title') or row.get('bookmarkTitle') or '')}"
            )
        return "\n".join(lines)

    return json.dumps(data, ensure_ascii=False, indent=2)


def print_result(command: str, data: Any, output_format: str) -> None:
    if output_format == "text":
        print(format_text(command, data))
    else:
        print_json(data)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="아파트스토리 방문차량 예약 CLI (웹 세션 기반).",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("APTSTORY_BASE_URL", ""),
        help="단지 웹 주소. 예: https://your-apartment.aptstory.com",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("APTSTORY_USERNAME", ""),
        help="로그인 아이디. APTSTORY_USERNAME 환경변수 우선.",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("APTSTORY_PASSWORD", ""),
        help="로그인 비밀번호. APTSTORY_PASSWORD 환경변수 권장.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP 타임아웃 초 (기본: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--allow-any-car-no",
        action="store_true",
        help="차량번호 형식 검사를 건너뜁니다.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default=os.environ.get("APTSTORY_OUTPUT_FORMAT", "json"),
        help="출력 형식. json(기본) 또는 text(사람이 읽기 쉬운 표).",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="환경변수 파일 경로 (기본: .env). 이미 설정된 값은 덮어쓰지 않습니다.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("settings", help="주차 설정 조회")

    list_visits_parser = subparsers.add_parser(
        "list-visits", help="방문차량 예약 목록"
    )
    list_visits_parser.add_argument("--page", type=int, default=1)
    list_visits_parser.add_argument("--limit", type=int, default=10)
    list_visits_parser.add_argument("--car-no", default=None)

    get_visit_parser = subparsers.add_parser(
        "get-visit", help="방문차량 예약 단건 조회"
    )
    get_visit_parser.add_argument("visit_id", type=int)

    create_visit_parser = subparsers.add_parser(
        "create-visit", help="방문차량 예약 등록"
    )
    create_visit_parser.add_argument("--car-no", required=True)
    create_visit_parser.add_argument(
        "--start-date",
        required=True,
        help="YYYY-MM-DD / 오늘 / 내일 / +1",
    )
    create_visit_parser.add_argument(
        "--end-date",
        required=True,
        help="YYYY-MM-DD / 오늘 / 내일 / +1",
    )
    create_visit_parser.add_argument("--visitor-phone-no", default="")
    create_visit_parser.add_argument("--memo", default="")

    update_visit_parser = subparsers.add_parser(
        "update-visit", help="방문차량 예약 수정"
    )
    update_visit_parser.add_argument("visit_id", type=int)
    update_visit_parser.add_argument("--car-no", required=True)
    update_visit_parser.add_argument(
        "--start-date",
        required=True,
        help="YYYY-MM-DD / 오늘 / 내일 / +1",
    )
    update_visit_parser.add_argument(
        "--end-date",
        required=True,
        help="YYYY-MM-DD / 오늘 / 내일 / +1",
    )
    update_visit_parser.add_argument("--visitor-phone-no", default="")
    update_visit_parser.add_argument("--memo", default="")

    delete_visit_parser = subparsers.add_parser(
        "delete-visit", help="방문차량 예약 삭제"
    )
    delete_visit_parser.add_argument("visit_id", type=int)

    list_bookmarks_parser = subparsers.add_parser(
        "list-bookmarks", help="즐겨찾기 목록"
    )
    list_bookmarks_parser.add_argument("--page", type=int, default=1)
    list_bookmarks_parser.add_argument("--limit", type=int, default=10)

    create_bookmark_parser = subparsers.add_parser(
        "create-bookmark", help="즐겨찾기 등록"
    )
    create_bookmark_parser.add_argument("--car-no", required=True)
    create_bookmark_parser.add_argument("--title", default="")
    create_bookmark_parser.add_argument("--visitor-phone-no", default="")
    create_bookmark_parser.add_argument("--memo", default="")

    update_bookmark_parser = subparsers.add_parser(
        "update-bookmark", help="즐겨찾기 수정"
    )
    update_bookmark_parser.add_argument("bookmark_id", type=int)
    update_bookmark_parser.add_argument("--car-no", required=True)
    update_bookmark_parser.add_argument("--title", default="")
    update_bookmark_parser.add_argument("--visitor-phone-no", default="")
    update_bookmark_parser.add_argument("--memo", default="")

    delete_bookmark_parser = subparsers.add_parser(
        "delete-bookmark", help="즐겨찾기 삭제"
    )
    delete_bookmark_parser.add_argument("bookmark_id", type=int)

    return parser.parse_args(argv)


def build_client(args: argparse.Namespace) -> AptStoryClient:
    base_url = args.base_url.strip()
    username = args.username.strip()
    password = args.password
    if not base_url:
        raise SystemExit("--base-url 또는 APTSTORY_BASE_URL 이 필요합니다.")
    if not username:
        raise SystemExit("--username 또는 APTSTORY_USERNAME 이 필요합니다.")
    if not password:
        password = getpass.getpass("APTSTORY_PASSWORD: ")
    try:
        return AptStoryClient(
            base_url=base_url,
            username=username,
            password=password,
            timeout=validate_positive_int(args.timeout, field="timeout", maximum=120),
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
            limit=validate_positive_int(args.limit, field="limit", maximum=100),
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
            limit=validate_positive_int(args.limit, field="limit", maximum=100),
        )

    if args.command == "create-bookmark":
        return client.create_bookmark(
            car_no=normalize_car_no(args.car_no, strict=not args.allow_any_car_no),
            title=args.title,
            visitor_phone_no=args.visitor_phone_no,
            memo=args.memo,
        )

    if args.command == "update-bookmark":
        return client.update_bookmark(
            bookmark_id=validate_positive_int(args.bookmark_id, field="bookmark_id"),
            car_no=normalize_car_no(args.car_no, strict=not args.allow_any_car_no),
            title=args.title,
            visitor_phone_no=args.visitor_phone_no,
            memo=args.memo,
        )

    if args.command == "delete-bookmark":
        return client.delete_bookmark(
            validate_positive_int(args.bookmark_id, field="bookmark_id")
        )

    raise SystemExit(f"지원하지 않는 명령: {args.command}")


def main(argv: Optional[list[str]] = None) -> int:
    # Pre-parse --env-file so credentials can come from .env before argparse defaults.
    preload = argparse.ArgumentParser(add_help=False)
    preload.add_argument("--env-file", default=".env")
    pre_args, remaining = preload.parse_known_args(argv)
    load_dotenv(Path(pre_args.env_file))

    args = parse_args(remaining)
    args.env_file = pre_args.env_file
    client = build_client(args)
    try:
        client.login()
        result = run_command(client, args)
        print_result(args.command, result, args.format)
        return 0
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        if exc.payload is not None and args.format == "json":
            print_json(exc.payload)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("중단됨", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
