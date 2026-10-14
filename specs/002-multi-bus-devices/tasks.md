# Tasks: 002 Multiple Buses and Devices

## Phase 1: Foundation
- [ ] T001 `devices.py`: tables, validation, save_config (all-or-nothing), load_config, migration from .env, status, version
- [ ] T002 `database.py`: device_id column + index + migration of existing tables; device filter in build_union_query
- [ ] T003 [P] tests: validation (duplicates, slave per bus, bus in use), migration, ALTER of existing tables

## Phase 2: US3 + US4 — reader
- [ ] T004 `modbus_reader.py`: Writer (queue, batch, day rollover), BusPoller (signed registers × scale, validation, status, back-off), Supervisor (per-bus restart on config change)
- [ ] T005 [P] tests: poller with fake instrument (signed values, failure isolation), writer inserts device_id

## Phase 3: US1 — settings
- [ ] T006 `settings.py`: poll_interval_seconds; `settings_ui.py`: Modbus section with bus/device tables, port suggestions, live status, save

## Phase 4: US2 — dashboard
- [ ] T007 `layout.py`/`callbacks.py`: device selector, combined figure, overview cards, Mollier for all devices, historical replay per device

## Phase 5: Polish
- [ ] T008 translations nl/en/de/fr/es
- [ ] T009 README/.env.example (MODBUS_* = initial values only), CI compile/import list
- [ ] T010 End-to-end run with simulated devices
