# Research: External MariaDB Device Source

**Feature**: 002-external-mariadb-device-source
**Date**: 2026-03-20
**Phase**: 0 — Outline & Research

---

## Decision 1: External DB Connection Approach

**Decision**: Use a direct, single-use `mariadb.connect()` call (no pool) with a 5-second `connect_timeout`.

**Rationale**: The external DB is queried once per run, immediately before SSH polling. A connection pool adds complexity with no benefit for a one-shot read. The `mariadb` package (already a dependency) supports `connect_timeout` directly.

**Alternatives considered**:
- SQLAlchemy: rejected — heavyweight, not already a dependency, no benefit for a single query.
- Separate DB driver (PyMySQL, mysql-connector-python): rejected — `mariadb` is already in `requirements.txt`.

---

## Decision 2: `Device.password` Type Change — `bytes` → `str`

**Decision**: Change `Device.password` from `bytes` to `str`. All call sites updated:
- `base_collector.py`: remove `decrypt_password()` call; pass `self.device.password` directly to `ConnectHandler`.
- `db/queries.py`: `load_enabled_devices()` coerced `bytes(password)` — entire function removed.
- `utils/encryption.py`: entire module removed.

**Rationale**: Plaintext passwords from an external source are strings. Keeping `bytes` would require an artificial `.encode()/.decode()` roundtrip with no benefit.

**Alternatives considered**:
- Keep `bytes` with `.encode()` wrapper: rejected — confusing, no semantic value.
- New `ExternalDevice` model: rejected — unnecessary duplication; `Device` is already minimal.

---

## Decision 3: Row Validation Strategy

**Decision**: Validate each row from the external query for required fields (`ip_address`, `device_type`, `username`, `password`). Skip invalid rows with a `WARNING` log. Accept `hostname` as optional (default to `ip_address` if absent).

**Rationale**: The operator controls the SQL query, so missing fields indicate a schema mapping error. Skipping (not crashing) matches the existing behaviour for unknown device types and keeps the run resilient.

**Alternatives considered**:
- Fail entire run on first invalid row: rejected — too brittle; one bad row should not block hundreds of valid devices.

---

## Decision 4: Deduplication Strategy

**Decision**: Deduplicate by `ip_address` (primary) after row validation. Log a `WARNING` for each duplicate dropped.

**Rationale**: Two rows with the same IP would SSH to the same device twice, potentially causing flaps or duplicate inventory entries. `ip_address` is the most reliable unique key (hostnames may alias).

**Alternatives considered**:
- Deduplicate by `hostname`: rejected — hostnames are not guaranteed unique in all external schemas.
- No deduplication: rejected — FR-010 explicitly requires it.

---

## Decision 5: External DB Configuration — Environment Variable Names

**Decision**: Use the `EXT_DB_` prefix to clearly distinguish from the existing local `DB_*` vars:

| Env Var | Required | Description |
|---|---|---|
| `EXT_DB_HOST` | Yes | External DB hostname or IP |
| `EXT_DB_PORT` | No (default: 3306) | External DB port |
| `EXT_DB_USER` | Yes | External DB username |
| `EXT_DB_PASSWORD` | Yes | External DB password |
| `EXT_DB_NAME` | Yes | External DB database name |
| `EXT_DB_QUERY` | Yes | SQL query returning device rows |

**Rationale**: Prefix prevents collision with local `DB_*` settings. Both databases are active simultaneously (external for device sourcing, local for result storage).

---

## Summary of Files Changed

| File | Change Type | Description |
|---|---|---|
| `network_inventory/config.py` | Modify | Remove `encryption_key_file`; add `EXT_DB_*` fields |
| `network_inventory/models/device.py` | Modify | `password: bytes` → `str`; remove `enabled` field (filtered by SQL) |
| `network_inventory/db/external_source.py` | New | External DB connection + query execution |
| `network_inventory/db/queries.py` | Modify | Remove `load_enabled_devices()`; keep `upsert_inventory_record()` |
| `network_inventory/db/__init__.py` | Modify | Remove `load_enabled_devices` export |
| `network_inventory/collectors/base_collector.py` | Modify | Remove `key` param; use plaintext password directly |
| `network_inventory/utils/encryption.py` | Delete | Entire module removed |
| `network_inventory/main.py` | Modify | Remove Fernet step; call `load_devices_from_external_db()` |
| `network_inventory/.env.example` | Modify | Replace `ENCRYPTION_KEY_FILE` with `EXT_DB_*` vars |
| `tests/integration/` | Modify | Remove encryption tests; add external DB tests |
