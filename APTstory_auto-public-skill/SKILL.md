---
name: aptstory-web-reservation
description: Automate AptStory apartment-specific web parking flows through the official website session, not the mobile app. Use when Codex needs to log in to an AptStory site such as `https://subdomain.aptstory.com`, inspect confirmed parking APIs, list visitor reservations, create or delete visitor reservations, build bulk reservation tooling, or reverse engineer a new apartment AptStory parking workflow from the web UI.
---

# AptStory Web Reservation

Use the apartment-specific AptStory website as the primary automation target. Prefer the web flow over the Android app when both expose the same parking features because the web flow is simpler: form login plus session cookies.

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

Typical commands:

```bash
python3 scripts/aptstory_web_cli.py settings
python3 scripts/aptstory_web_cli.py list-visits --limit 5
python3 scripts/aptstory_web_cli.py create-visit --car-no 12가3456 --start-date 2026-03-10 --end-date 2026-03-10
python3 scripts/aptstory_web_cli.py delete-visit 123456
```

## Implementation Rules

- Prefer web-session automation over app UI automation.
- Treat `dong` and `ho` as server-derived session fields unless evidence shows otherwise for a different apartment.
- Require explicit reservation dates in user-facing tooling even if the API accepts less, because the server may create same-day reservations from partial payloads.
- Verify create and delete operations against live responses when changing payload shape.
- If working on a different AptStory apartment, re-check the domain, login form action, and parking endpoints before assuming they match this one exactly.
