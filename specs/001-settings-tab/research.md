# Research: 001 Settings Tab

## Settings storage
- **Decision**: table `settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER)` in the existing DB; values JSON-encoded; schema defined in code (`settings.SCHEMA`).
- **Rationale**: no new files/services; transactional save of all keys at once (FR edge case: no half-apply).
- **Alternatives**: rewriting `.env` (needs file write rights, no validation, race-prone); separate JSON file (second source of truth).

## Live apply
- **Decision**: modules read settings via `settings.get()` at use time (in-memory cache), instead of module-level constants.
- **Rationale**: no restart or signalling needed; a value saved now is used on the next callback / cleanup run.

## Authentication
- **Decision**: Flask session cookie (signed with a random `secret_key` generated once and stored in `settings`), `werkzeug.security.generate_password_hash`/`check_password_hash`, plain HTML routes `/login`, `/setup`, `/logout`; `before_request` guard for protection level "app"; settings callbacks verify the session themselves.
- **Rationale**: Werkzeug/Flask already installed with Dash; server-rendered forms work even when Dash JS fails to load; guard on `_dash-update-component` makes FR-009 enforceable server-side.
- **Alternatives**: `dash-auth` BasicAuth (no logout, no settings-only mode, new dependency); Flask-Login (new dependency for one user).

## Session revocation
- **Decision**: the signed Flask cookie only carries a random session id; validity lives server-side in memory (`sid -> last_seen, password hash at login`).
- **Rationale**: logout, password change and password reset must invalidate copied cookies, and the inactivity timeout must not be extendable by the client. A restart logs everyone out, which is acceptable.

## Throttling
- **Decision**: in-memory failures per client (IPv4 address, IPv6 /64), 5 failures/5 min → block 5 min. Above 50 failures/5 min across all clients (attack from many addresses) only browsers with a signed 90-day "trusted browser" cookie (set on a successful login, kept after logout, unique id per browser, bound to the current password hash) may still try; each trusted browser has its own limit of 5 failures/5 min regardless of address. Sessions store the hash that was actually verified, so a login racing a password change is not upgraded.
- **Rationale**: per-address limits alone are bypassed with many addresses, a global hard block locks out the admin; the trusted-browser cookie keeps both. Residual: the admin on a new browser during an active attack waits up to 5 minutes (or uses `reset-password` locally).

## Host/port fallback
- **Decision**: try stored host/port; on `OSError` while binding, log and retry with `.env`/defaults (`0.0.0.0:8050`).
- **Rationale**: a typo in the port must not make a remote device unreachable.

## Password reset
- **Decision**: `python settings.py reset-password` deletes the admin hash only.
