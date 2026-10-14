# XY-MD02 WebApp Constitution

## Core Principles

### I. Unattended Edge Reliability (NON-NEGOTIABLE)
The app runs on remote, headless IoT edge devices without a logged-in user. A failure in
one component (a sensor that does not answer, an unreachable MQTT broker, a failing SMTP
server) MUST NOT stop data collection or the web UI. Errors are logged and retried with
backoff; nothing blocks the Modbus polling loop. The app must survive reboots and start as
a system service.

### II. Browser-First Configuration
Everything a user needs to operate the app is configurable from the web UI. `.env` remains
only as a bootstrap/fallback for first start (port, host, database path). Settings changed
in the UI are persisted in the SQLite database and take effect without editing files.
Changes that require a restart say so explicitly in the UI.

### III. Secure by Default
The Settings tab is always protected by an admin password; the user chooses whether the
dashboard is protected too. Secrets (SMTP password, Telegram token, MQTT password) are
never sent back to the browser in clear text; fields are write-only. Inputs from the
browser are validated server-side before they reach Modbus, SQL, SMTP or MQTT.

### IV. Every String Translated
All user-visible text goes through `translations.py`. A key added to one language is added
to all supported languages in the same change. The translation-validator CI job must stay
green.

### V. Simplicity and Small Footprint
Plain Python + Dash + SQLite, no extra services. Prefer the standard library and already
installed dependencies; a new dependency needs a reason in the plan. No speculative
abstractions. Code, comments and naming follow the existing style of the repo.

## Technical Constraints

- Python 3.10-3.13 on Linux (Raspberry Pi / x86) and Windows.
- Dash + Plotly UI, Waitress WSGI server, SQLite storage (table-per-day partitioning).
- Modbus RTU over one or more RS-485 buses (one serial interface each, e.g. USB dongles); each
  bus carries one or more slaves addressed by slave ID (minimalmodbus). A slow or failing bus
  must not delay the other buses. Sensors report temperature and relative humidity.
- Existing single-sensor installations MUST upgrade without data loss: the current sensor
  becomes the first device.

## Development Workflow

- Spec Kit flow per feature: `/speckit-specify` -> `/speckit-plan` -> `/speckit-tasks` ->
  `/speckit-implement`, one branch and one pull request per feature.
- Non-trivial logic ships with tests in `test_app.py` / `tests/`, run by CI.
- CI (syntax, imports, tests, translations, flake8) must pass before merge.
- Commits and PRs are authored by the repository owner only; no AI attribution.

## Governance

This constitution guides all specs, plans and reviews in this repository. Deviations must be
justified in the plan's complexity section. Amendments are made in this file with a version
bump.

**Version**: 1.0.0 | **Ratified**: 2026-10-14 | **Last Amended**: 2026-10-14
