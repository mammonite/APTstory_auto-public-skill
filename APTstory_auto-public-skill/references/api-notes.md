# AptStory Web Parking Notes

## Confirmed apartment pattern

- Domain pattern: `https://your-apartment.aptstory.com`
- Unit-specific resident context was server-derived from the logged-in session and is intentionally omitted from this public skill.

## Login flow

1. `GET /`
2. `POST /comExec/procLogin.php`
   - form fields:
     - `tbID`
     - `tbPWD`
3. Success marker on subsequent `GET /`:
   - `/member/logout.apt`

## Session model

- Authentication is cookie-based.
- Relevant cookies observed:
  - `PHPSESSID`
  - `x-app-refresh`
- No bearer token was required for the web v2 parking APIs.

## API base

- `/comExec/api/index.php?api_path=/v2`

## Confirmed endpoints

### Settings

- `GET /parking/settings`

### Visitor reservation

- `GET /parking/visit?page=1&limit=10`
- `GET /parking/visit/{visitId}`
- `POST /parking/visit`
- `PUT /parking/visit/{visitId}`
- `DELETE /parking/visit/{visitId}`

Confirmed request payload shape:

```json
{
  "carNo": "12가3456",
  "visitorPhoneNo": "",
  "visitStartDate": "2026-03-09",
  "visitEndDate": "2026-03-09",
  "memo": ""
}
```

Observed response fields:

- `visitId`
- `carNo`
- `dong`
- `ho`
- `visitorPhoneNo`
- `residentsPhoneNo`
- `visitStartDate`
- `visitEndDate`
- `memo`
- `registrationDatetime`
- `updateDatetime`
- `isVisitToday`
- `isBookmark`
- `bookmarkId`
- `bookmarkTitle`

### Bookmark

- `GET /parking/bookmark?page=1&limit=10`
- `POST /parking/bookmark`
- `PUT /parking/bookmark/{bookmarkId}`
- `DELETE /parking/bookmark/{bookmarkId}`

### Other parking APIs observed in frontend bundles

- `GET /parking/unit-info`
- `GET /parking/balance`
- `GET /parking/whitelist`
- `POST /parking/whitelist`
- `PUT /parking/whitelist/{whitelistId}`
- `DELETE /parking/whitelist/{whitelistId}`
- `GET /parking/accesses`
- `GET /parking/blacklist/logs`
- `POST /parking/blacklist`
- `GET /parking/ticket`

## Safety caveat

The server accepted `POST /parking/visit` with only `carNo` and created a same-day reservation automatically. Do not rely on that behavior in user-facing tooling. Always send explicit `visitStartDate` and `visitEndDate`.

## Reverse engineering guidance for another AptStory apartment

1. Confirm the apartment-specific domain.
2. Inspect `/` for the actual login action.
3. Log in manually once.
4. Open the parking menu pages.
5. Check whether the page loads a modern frontend bundle under `resource.aptstory.com/v3/pages/...`.
6. Extract API paths from that bundle or call the v2 endpoints directly with the active web session.
