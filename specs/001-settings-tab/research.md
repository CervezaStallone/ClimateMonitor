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

## Throttling
- **Decision**: in-memory dict `{client_ip: [failure timestamps]}`, 5 failures/5 min → block 5 min.
- **Rationale**: single process; state loss on restart is acceptable.

## Host/port fallback
- **Decision**: try stored host/port; on `OSError` while binding, log and retry with `.env`/defaults (`0.0.0.0:8050`).
- **Rationale**: a typo in the port must not make a remote device unreachable.

## Password reset
- **Decision**: `python settings.py reset-password` deletes the admin hash only.
