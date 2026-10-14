# Implementation Plan: Multiple RS-485 Buses and Devices

**Branch**: `002-multi-bus-devices` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

## Summary

Bus and device configuration in two new tables, edited in the Settings tab (editable tables).
The single Modbus thread becomes a supervisor that runs one poller thread per enabled bus and
restarts only buses whose configuration changed; one writer thread batches inserts. Measurement
tables get a `device_id` column. The dashboard gets a device selector with a combined view.

## Technical Context

**Language/Version**: Python 3.10-3.13
**Primary Dependencies**: existing only (Dash/dash_table, minimalmodbus, pyserial incl. `serial.tools.list_ports`)
**Storage**: SQLite: new tables `buses`, `devices`; `device_id` column in `measurements_YYYYMMDD`
**Testing**: `test_app.py` (config validation, migration, poller with a fake instrument, queries)
**Constraints**: a bus never blocks another bus; upgrade must not rewrite existing rows

## Constitution Check

| Principle | Status |
|-----------|--------|
| I. Unattended edge reliability | PASS — per-bus threads, back-off retry, missing port at startup no longer kills the reader |
| II. Browser-first configuration | PASS — completes moving `.env` Modbus settings to the browser |
| III. Secure by default | PASS — Modbus section only for logged-in admin; server-side validation |
| IV. Every string translated | PASS — nl/en/de/fr/es |
| V. Simplicity | PASS — threads + queue from stdlib, dash_table already installed |

## Design

- `devices.py` (new): schema/validation for buses and devices, `load_config()`, `save_config(buses, devices)` (all-or-nothing, returns per-row errors), migration from `.env`, runtime status (`report_ok/report_error/status()`), config version.
- `modbus_reader.py` (rewrite): `start_modbus_thread()` keeps its name; starts `Supervisor` (checks config version every 2 s; starts/stops `BusPoller` per bus by comparing bus+device config) and `Writer` (queue → batched inserts, day rollover).
- `database.py`: `device_id` column + index, migration via `ALTER TABLE ADD COLUMN device_id INTEGER NOT NULL DEFAULT 1`; `build_union_query(..., device_id=None)`.
- `callbacks.py` / `layout.py`: device selector (`0` = all), combined figure, per-device overview cards, Mollier with all devices, historical replay per device.
- `settings_ui.py`: Modbus section with two `dash_table.DataTable`s (buses, devices), live status column, port suggestions; poll interval setting in `settings.SCHEMA`.

## Complexity Tracking

No violations.
