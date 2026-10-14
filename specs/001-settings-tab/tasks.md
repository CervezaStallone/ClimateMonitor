# Tasks: 001 Settings Tab

**Input**: spec.md, plan.md, data-model.md, contracts/
**Tests**: included (constitution: non-trivial logic ships with tests)

## Phase 1: Foundation (blocks all stories)

- [x] T001 Create `settings.py`: SCHEMA from contracts/settings-keys.md, validators, JSON (de)serialisation
- [x] T002 `settings.py`: table creation, `.env` migration on load, in-memory cache, `get()`, `save()` (all-or-nothing), group versions
- [x] T003 `settings.py`: CLI `python settings.py reset-password`
- [x] T004 [P] `test_app.py`: tests for validation, migration from env, all-or-nothing save, reset

## Phase 2: User Story 1 — change configuration from the browser (P1)

- [x] T005 `modbus_reader.py`: retention from settings (Modbus config stays `.env` until 002)
- [x] T006 [P] `database.py`: retention + debug from settings (functions instead of module constants); update callers in `app.py`/`modbus_reader.py`
- [x] T007 [P] `callbacks.py`: timezone + debug from settings at call time
- [x] T008 `layout.py`: Tabs (Dashboard | Settings); callable layout so default language is read per page load
- [x] T009 `callbacks.py`: Settings tab render (form pre-filled, restart badges, read-only DB path) and save (validate, per-field errors, success message)
- [x] T010 `app.py`: host/port from settings with bind-failure fallback

## Phase 3: User Story 2 — admin password and protection level (P1)

- [x] T011 `auth.py`: hash/verify, session login/logout/expiry, throttling, `/setup` `/login` `/logout` routes (translated HTML), `before_request` guard for auth_mode `app`
- [x] T012 Settings callbacks require login; protection level + session timeout fields; change-password form
- [x] T013 [P] `test_app.py`: tests for setup/login/throttle/guard via Flask test client

## Phase 4: User Story 3/4 — upgrade + recovery (P2/P3)

- [x] T014 Verify migration path with existing `.env` (covered by T004) and document reset command

## Phase 5: Polish

- [x] T015 `translations.py`: all new keys in nl/en/de/fr/es
- [x] T016 README + `.env.example`: Settings tab, protection, reset command, bootstrap-only keys
- [x] T017 CI: add `settings.py`/`auth.py` to syntax + import checks
- [x] T018 Manual check: run app with test DB, exercise settings + login flows
