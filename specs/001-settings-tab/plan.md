# Implementation Plan: Settings Tab with Browser Configuration and Optional Login

**Branch**: `001-settings-tab` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

## Summary

Move all `.env` configuration into a validated key/value settings store in the existing SQLite
database, expose it in a new Settings tab, apply changes live where possible, and protect the
app with a single admin password using Flask sessions (Dash already runs on Flask). The admin
chooses protection level "settings" (default) or "app".

## Technical Context

**Language/Version**: Python 3.10-3.13
**Primary Dependencies**: Dash 3.3 (Flask 3.1, Werkzeug 3.1), Plotly, minimalmodbus, python-dotenv, Waitress — no new dependencies
**Storage**: SQLite (existing DB file), new table `settings`
**Testing**: `test_app.py` (plain asserts, runnable as `python test_app.py`, executed by CI)
**Target Platform**: Linux (Raspberry Pi/x86) and Windows, headless
**Project Type**: single-process web application
**Performance Goals**: settings read from an in-memory cache; no extra DB reads per Modbus poll
**Constraints**: Modbus loop never blocks on UI; a failed save never half-applies
**Scale/Scope**: one admin, ~8 settings (Modbus buses/devices follow in 002)

## Constitution Check

| Principle | Status |
|-----------|--------|
| I. Unattended edge reliability | PASS — bind failure falls back to env/default host+port; reader untouched |
| II. Browser-first configuration | PASS (partial by design) — non-Modbus `.env` keys now; Modbus in 002; `DATABASE_FILE` stays bootstrap |
| III. Secure by default | PASS — settings always behind password; salted scrypt/pbkdf2 hash; secrets write-only; login throttling |
| IV. Every string translated | PASS — new keys added to nl/en/de/fr/es; translation validator stays green |
| V. Simplicity | PASS — stdlib + Werkzeug/Flask already installed; one new module `settings.py`, one `auth.py` |

## Project Structure

### Documentation (this feature)

```text
specs/001-settings-tab/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── settings-keys.md
│   └── http-routes.md
└── tasks.md
```

### Source Code (repository root)

```text
settings.py        # NEW: schema, validation, cache, .env migration, CLI reset
auth.py            # NEW: password hash, sessions, throttling, Flask routes + guard
app.py             # read host/port from settings, init auth, callable layout
database.py        # retention read from settings
layout.py          # Tabs (Dashboard | Settings), settings form container
callbacks.py       # settings form render/save callbacks, timezone/debug from settings
translations.py    # new keys in all languages
test_app.py        # NEW: tests for settings + auth
README.md, .env.example  # docs: settings tab, password reset, bootstrap-only env keys
```

**Structure Decision**: keep the flat module layout of the repo; add two modules.

## Complexity Tracking

No violations.
