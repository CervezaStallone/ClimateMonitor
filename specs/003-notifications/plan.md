# Implementation Plan: Threshold Notifications via Telegram and E-mail

**Branch**: `003-notifications` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

## Summary
Channel settings and alarm options are new keys in `settings.SCHEMA` (secrets write-only). Rules
live in table `alert_rules`. `alerts.py` evaluates each measurement in the poller thread (pure
in-memory state machine, no I/O) and queues messages; a `Notifier` thread sends them with retries
and checks for offline sensors every 30 s.

## Technical Context
**Dependencies**: existing only — `requests` (Telegram Bot API), stdlib `smtplib`/`ssl`/`email`
**Storage**: SQLite table `alert_rules(id, device_id NULL = all, metric, min_value, max_value, enabled)`
**Testing**: `test_app.py` with fake channels; end-to-end with a local SMTP sink and simulated buses

## Constitution Check
| Principle | Status |
|-----------|--------|
| I. Unattended edge reliability | PASS — evaluation never raises; sending in its own thread with back-off (max 1 h) |
| II. Browser-first configuration | PASS — channels, limits and options in Settings; test buttons |
| III. Secure by default | PASS — token/password write-only, never logged (redacted in errors), login required for all callbacks |
| IV. Every string translated | PASS |
| V. Simplicity | PASS — no new dependencies |

## Design decisions
- Override: a sensor rule replaces the global rule for the same quantity; a disabled sensor rule switches the global rule off for that sensor.
- State machine per (sensor, quantity): normal → pending (delay) → alarm → normal (hysteresis). Saving rules resets the state.
- Offline: no valid reading for N minutes, measured from the last reading or, for sensors without readings, from the moment they are first seen.
- Rules can only reference saved sensors (the scope dropdown lists saved sensors).
