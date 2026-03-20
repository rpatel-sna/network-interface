# Implementation Plan: External MariaDB Device Source

**Branch**: `002-external-mariadb-device-source` | **Date**: 2026-03-20
**Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md) | **Data Model**: [data-model.md](data-model.md)

---

## Summary

Replace the local MariaDB device source with an external MariaDB database queried via a user-supplied SQL query. Device SSH credentials are delivered as plaintext — the Fernet encryption module is removed entirely. The `Device.password` field changes from `bytes` to `str`. A new `db/external_source.py` module handles the external connection (5-second timeout, plain TCP). All other pipeline components (SSH polling, local result storage, reporting) are unchanged.

---

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `mariadb>=1.1`, `netmiko>=4.3`, `python-dotenv>=1.0` (unchanged). `cryptography` package removed if `utils/encryption.py` is the only consumer.
**Storage**: External MariaDB (read-only, device source) + local MariaDB (write, inventory results)
**Testing**: pytest, existing integration test suite extended
**Target Platform**: Linux/macOS, Docker
**Performance Goals**: Device list retrieved and SSH polling started within 10 seconds of startup
**Constraints**: External DB connection timeout fixed at 5 seconds; single connection per run (no pool)
**Scale/Scope**: Same as feature 001 — bounded by `MAX_THREADS` workers

---

## Constitution Check

Constitution requires: Python 3.11+, pytest. Both satisfied. No violations.

---

## Project Structure

### Documentation (this feature)

```
kitty-specs/002-external-mariadb-device-source/
├── plan.md              ← this file
├── research.md          ← Phase 0 complete
├── data-model.md        ← Phase 1 complete
└── tasks.md             ← Phase 2 output (/spec-kitty.tasks)
```

### Source Code Changes

```
network_inventory/
├── config.py                        # MODIFY — remove encryption_key_file, add EXT_DB_* fields
├── models/
│   └── device.py                    # MODIFY — password: bytes → str
├── db/
│   ├── external_source.py           # NEW — load_devices_from_external_db()
│   ├── queries.py                   # MODIFY — remove load_enabled_devices()
│   └── __init__.py                  # MODIFY — remove load_enabled_devices export
├── collectors/
│   └── base_collector.py            # MODIFY — remove key param, use plaintext password
├── utils/
│   └── encryption.py                # DELETE — entire module removed
└── main.py                          # MODIFY — remove Fernet step, call external source

network_inventory/.env.example       # MODIFY — replace ENCRYPTION_KEY_FILE with EXT_DB_* vars

tests/integration/
├── conftest.py                      # MODIFY — remove encryption fixtures, add external DB fixtures
├── test_db.py                       # MODIFY — remove encryption-related tests
└── test_full_run.py                 # MODIFY — update to use external DB source
```

---

## Work Package Breakdown

### WP01 — Config & Model Changes
**Dependencies**: none
**Deliverables**:
- `network_inventory/config.py`: remove `encryption_key_file`; add `ext_db_host`, `ext_db_port`, `ext_db_user`, `ext_db_password`, `ext_db_name`, `ext_db_query` fields; update `_load_settings()` required-var check.
- `network_inventory/models/device.py`: `password: bytes` → `str`; update docstring.
- `network_inventory/.env.example`: replace `ENCRYPTION_KEY_FILE=...` with `EXT_DB_HOST`, `EXT_DB_PORT`, `EXT_DB_USER`, `EXT_DB_PASSWORD`, `EXT_DB_NAME`, `EXT_DB_QUERY` entries.

**Acceptance**: `settings.ext_db_host` resolves from env; `Device(password="plaintext")` instantiates without error.

---

### WP02 — External DB Source Module
**Dependencies**: WP01
**Deliverables**:
- `network_inventory/db/external_source.py` (new):
  - `load_devices_from_external_db(app_settings: Settings) -> list[Device]`
  - `mariadb.connect()` with `connect_timeout=5`; `sys.exit(1)` on `mariadb.Error`
  - Execute `app_settings.ext_db_query`
  - Validate each row: skip + `WARNING` on missing `ip_address`, `device_type`, `username`, `password`
  - Deduplicate by `ip_address`; `WARNING` per dropped duplicate
  - Return `list[Device]` (password as `str`)

**Acceptance**: Given valid external DB + query → returns correct device list. Given unreachable DB → exits with code 1 within 5 seconds. Given zero rows → returns empty list.

---

### WP03 — Remove Encryption + Update DB Layer
**Dependencies**: WP01
**Deliverables**:
- `network_inventory/utils/encryption.py`: **delete** entire file
- `network_inventory/db/queries.py`: remove `load_enabled_devices()` function and `_LOAD_ENABLED_DEVICES_SQL` constant; keep `upsert_inventory_record()` unchanged
- `network_inventory/db/__init__.py`: remove `load_enabled_devices` from imports and `__all__`

**Acceptance**: `from network_inventory.db import upsert_inventory_record` works; `load_enabled_devices` import raises `ImportError`; `from network_inventory.utils.encryption import decrypt_password` raises `ImportError`.

---

### WP04 — Update BaseCollector + main.py
**Dependencies**: WP02, WP03
**Deliverables**:
- `network_inventory/collectors/base_collector.py`:
  - Remove `key: bytes` parameter from `__init__`; remove `self._key` attribute
  - Remove `from network_inventory.utils.encryption import decrypt_password` import
  - In `_connect()`: use `self.device.password` directly as password string (no decrypt call)
- `network_inventory/main.py`:
  - Remove Step 2 (Fernet key load — `load_key()` call, key validation, `sys.exit(1)` on key error)
  - Replace Step 4 (`load_enabled_devices(conn)`) with `load_devices_from_external_db(settings)`
  - Remove `key=key` from `collector_class(device=device, key=key)` → `collector_class(device=device)`
  - Update module docstring startup sequence (remove step 3: "Load and validate Fernet key file")

**Acceptance**: Tool starts with external DB configured; no Fernet key file required; SSH polling proceeds with plaintext credentials.

---

### WP05 — Integration Tests
**Dependencies**: WP04
**Deliverables**:
- `tests/integration/conftest.py`: remove `fernet_key` / encryption fixtures; add `external_db_conn` fixture pointing to a test external DB
- `tests/integration/test_db.py`: remove `test_load_enabled_devices` and encryption-related tests; add `test_load_devices_from_external_db` covering happy path, zero rows, missing fields, duplicates, unreachable DB
- `tests/integration/test_full_run.py`: update to source devices from external DB fixture instead of local devices table

**Acceptance**: `pytest tests/integration/` passes; no references to `encryption`, `load_key`, or `decrypt_password` remain in test files.

---

## Dependency Graph

```
WP01 (config + model)
  ├── WP02 (external_source.py)
  │     └── WP04 (collectors + main)
  └── WP03 (delete encryption + update db layer)
        └── WP04
              └── WP05 (integration tests)
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| External DB query returns unexpected column names | Medium | High | Row validator skips + warns; operator fixes SQL alias |
| `cryptography` package still used elsewhere | Low | Low | Check imports before removing from requirements.txt |
| `Device.enabled` field used in downstream code | Low | Medium | Keep field, default to `True` in `load_devices_from_external_db()` |
| Netmiko rejects `str` password where `bytes` expected | Low | High | Netmiko `ConnectHandler` accepts `str` natively — confirmed by library docs |

---

## Environment Variables Reference

```dotenv
# External device source (new in feature 002)
EXT_DB_HOST=external-db.example.com
EXT_DB_PORT=3306
EXT_DB_USER=readonly_user
EXT_DB_PASSWORD=change_me
EXT_DB_NAME=network_management
EXT_DB_QUERY=SELECT ip_address, device_type, username, password, hostname, ssh_port FROM managed_devices WHERE active = 1

# Local result storage (unchanged from feature 001)
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=inventory_user
DB_PASSWORD=change_me
DB_NAME=network_inventory

# Removed in feature 002
# ENCRYPTION_KEY_FILE=...
```
