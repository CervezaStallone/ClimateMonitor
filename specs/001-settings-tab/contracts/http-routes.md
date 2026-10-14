# Contract: HTTP Routes and Guard

| Route | Method | Access | Behaviour |
|-------|--------|--------|-----------|
| /setup | GET/POST | only while no admin password exists | form: password + repeat (min 8); on success logs in and redirects to `next` or `/` |
| /login | GET/POST | public | form: password; throttled (5 failures / 5 min per IP → HTTP 429 page); redirects to `next` |
| /logout | GET | public | clears session, redirects to `/` |

Guard (`before_request`):
- auth_mode `app` and not logged in → every request except `/login`, `/setup` and `/logout` is refused: HTML pages redirect to `/login?next=...`, Dash endpoints (`/_dash-*`) return HTTP 401.
- Session expiry: `last_seen` older than `session_timeout_minutes` → treated as logged out.

Settings callbacks:
- render: not logged in → login/setup prompt with link to `/login?next=/` ; logged in → form.
- save: re-checks session server-side; returns per-field error codes (translated in UI).
