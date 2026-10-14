# Contract: Settings Keys

| Key | Type | Default | .env name | Validation | Apply |
|-----|------|---------|-----------|------------|-------|
| data_retention_days | int | 0 | DATA_RETENTION_DAYS | 0–3650 (0 = forever) | live (next cleanup) |
| timezone | str | Europe/Amsterdam | TIMEZONE | valid IANA name | live |
| default_language | str | en | DEFAULT_LANGUAGE | nl, en, de, fr, es | live (next page load) |
| debug_logging | bool | false | DEBUG_LOGGING | bool | live |
| app_host | str | 0.0.0.0 | APP_HOST | valid IP or hostname | restart |
| app_port | int | 8050 | APP_PORT | 1–65535 | restart |
| auth_mode | str | settings | — | settings, app | live |
| session_timeout_minutes | int | 60 | — | 5–1440 | live |

Modbus keys (`MODBUS_*`) are not part of this feature; feature 002 replaces them with buses and
devices and migrates the `.env` values.

Bootstrap only (not stored, shown read-only): `DATABASE_FILE`.
