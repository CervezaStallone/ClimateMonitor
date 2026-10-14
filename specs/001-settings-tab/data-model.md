# Data Model: 001 Settings Tab

## Table `settings`

| Column | Type | Notes |
|--------|------|-------|
| key | TEXT PK | setting name, see contracts/settings-keys.md |
| value | TEXT NOT NULL | JSON-encoded value |
| updated_at | INTEGER | unix timestamp of last save |

Reserved internal keys (never rendered to the browser): `admin_password_hash`, `secret_key`.

## Lifecycle

1. Startup: `settings.load()` creates the table if missing. For each schema key without a row:
   value = parsed `.env` value if present and valid, else default; rows are inserted (migration).
2. Save: `settings.save(dict)` validates every key first; if any error → nothing is written and
   `{key: error_code}` is returned. Otherwise all rows are written in one transaction, the cache
   is updated and group versions are bumped.
3. Reset password: delete row `admin_password_hash`.
