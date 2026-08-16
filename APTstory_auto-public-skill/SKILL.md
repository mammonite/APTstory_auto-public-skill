---
name: aptstory-web-reservation
description: Automate AptStory apartment-specific web parking flows through the official website session, not the mobile app. Use when Codex needs to log in to an AptStory site such as `https://subdomain.aptstory.com`, inspect confirmed parking APIs, list visitor reservations, create/update/delete visitor reservations, manage bookmarks, or reverse engineer a new apartment AptStory parking workflow from the web UI.
---

# AptStory Web Reservation

아파트스토리(AptStory) 단지별 웹사이트 세션으로 방문차량 예약을 자동화합니다. 모바일 앱보다 웹 로그인(폼 + 쿠키)이 단순하므로 웹 플로우를 우선합니다.

단지 도메인은 관리사무소에 문의하세요. 예: `홍길동더샵아파트` → `https://hgdthesharp.aptstory.com`

## Workflow

1. Identify the apartment-specific domain such as `https://your-apartment.aptstory.com`.
2. Load `/` and inspect the login form. Confirm the form posts to `/comExec/procLogin.php`.
3. Log in with `tbID` and `tbPWD`.
4. Confirm login by checking that the home page contains `/member/logout.apt`.
5. Use the session cookies for subsequent API requests.
6. Prefer the confirmed v2 parking APIs under `/comExec/api/index.php?api_path=/v2`.

## Confirmed API Surface

Read [`references/api-notes.md`](./references/api-notes.md) before changing reservation logic. It contains:

- confirmed endpoints
- payload keys
- response fields
- observed safety caveats

## Script

Use [`scripts/aptstory_web_cli.py`](./scripts/aptstory_web_cli.py) for the baseline implementation. Prefer extending it instead of rewriting login and request plumbing from scratch.

Credentials (prefer env vars):

```bash
export APTSTORY_BASE_URL="https://your-apartment.aptstory.com"
export APTSTORY_USERNAME="your-id"
export APTSTORY_PASSWORD="your-password"
```

Typical commands:

```bash
python3 scripts/aptstory_web_cli.py settings
python3 scripts/aptstory_web_cli.py list-visits --limit 5
python3 scripts/aptstory_web_cli.py create-visit --car-no 12가3456 --start-date 2026-03-10 --end-date 2026-03-10
python3 scripts/aptstory_web_cli.py update-visit 123456 --car-no 12가3456 --start-date 2026-03-11 --end-date 2026-03-11
python3 scripts/aptstory_web_cli.py delete-visit 123456
python3 scripts/aptstory_web_cli.py list-bookmarks
python3 scripts/aptstory_web_cli.py create-bookmark --car-no 12가3456 --title "부모님"
python3 scripts/aptstory_web_cli.py delete-bookmark 42
```

## Implementation Rules

- Prefer web-session automation over app UI automation.
- Treat `dong` and `ho` as server-derived session fields unless evidence shows otherwise for a different apartment.
- Require explicit reservation dates in user-facing tooling even if the API accepts less, because the server may create same-day reservations from partial payloads.
- Validate `end-date >= start-date` before calling create/update.
- Prefer `APTSTORY_PASSWORD` env var over `--password` so credentials stay out of shell history.
- Verify create and delete operations against live responses when changing payload shape.
- If working on a different AptStory apartment, re-check the domain, login form action, and parking endpoints before assuming they match this one exactly.
