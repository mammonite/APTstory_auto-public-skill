---
name: aptstory-web-reservation
description: Automate AptStory apartment-specific web parking flows through the official website session, not the mobile app. Use when an agent needs to log in to an AptStory site such as `https://subdomain.aptstory.com`, list/create/update/delete visitor reservations, manage bookmarks, or reverse engineer a new apartment AptStory parking workflow from the web UI. Korean users may ask in natural language (방문차량 조회/등록/삭제).
---

# AptStory Web Reservation

아파트스토리(AptStory) 단지별 웹사이트 세션으로 방문차량 예약을 자동화합니다.  
모바일 앱보다 웹 로그인(폼 + 쿠키)이 단순하므로 **웹 플로우를 우선**하세요.

단지 도메인은 관리사무소에 문의하세요. 예: `홍길동더샵아파트` → `https://hgdthesharp.aptstory.com`

## 에이전트 사용 팁 (Hermes / OpenClaw / Cursor)

사용자가 평문으로 요청하면 CLI를 통해 **실제 조회·예약**을 수행하세요.

예시 요청 → 명령:

| 사용자 말 | 실행 |
|---|---|
| 방문차량 목록 보여줘 | `list-visits --limit 5 --format text` |
| 내일 12가3456 등록해줘 | `create-visit --car-no 12가3456 --start-date 내일 --end-date 내일` |
| 예약 123456 삭제 | `delete-visit 123456` |

날짜는 `YYYY-MM-DD`뿐 아니라 `오늘` / `내일` / `모레` / `+1` 도 됩니다.

## Workflow

1. Identify the apartment-specific domain such as `https://your-apartment.aptstory.com`.
2. Load `/` and inspect the login form. Confirm the form posts to `/comExec/procLogin.php`.
3. Log in with `tbID` and `tbPWD`.
4. Confirm login by checking that the home page contains `/member/logout.apt`.
5. Use the session cookies for subsequent API requests.
6. Prefer the confirmed v2 parking APIs under `/comExec/api/index.php?api_path=/v2`.

## Confirmed API Surface

Read [`references/api-notes.md`](./references/api-notes.md) before changing reservation logic.

## Script

Use [`scripts/aptstory_web_cli.py`](./scripts/aptstory_web_cli.py). Prefer extending it instead of rewriting login/request plumbing.

Credentials (prefer env vars or `.env`):

```bash
export APTSTORY_BASE_URL="https://your-apartment.aptstory.com"
export APTSTORY_USERNAME="your-id"
export APTSTORY_PASSWORD="your-password"
# optional: cp .env.example .env
```

Typical commands:

```bash
python3 scripts/aptstory_web_cli.py settings
python3 scripts/aptstory_web_cli.py list-visits --limit 5 --format text
python3 scripts/aptstory_web_cli.py create-visit --car-no 12가3456 --start-date 내일 --end-date 내일
python3 scripts/aptstory_web_cli.py update-visit 123456 --car-no 12가3456 --start-date 모레 --end-date 모레
python3 scripts/aptstory_web_cli.py delete-visit 123456
python3 scripts/aptstory_web_cli.py list-bookmarks --format text
python3 scripts/aptstory_web_cli.py create-bookmark --car-no 12가3456 --title "부모님"
python3 scripts/aptstory_web_cli.py update-bookmark 42 --car-no 12가3456 --title "부모님차"
python3 scripts/aptstory_web_cli.py delete-bookmark 42
```

## Implementation Rules

- Prefer web-session automation over app UI automation.
- Treat `dong` and `ho` as server-derived session fields unless evidence shows otherwise.
- Always send explicit `visitStartDate` / `visitEndDate` (relative dates OK after CLI resolution).
- Validate `end-date >= start-date` before create/update.
- Prefer env vars / `.env` over `--password` so credentials stay out of shell history.
- Prefer `--format text` for human replies; keep `json` for machine parsing.
- If working on a different AptStory apartment, re-check domain, login action, and parking endpoints.
