# Work Packages: External MariaDB Device Source

**Inputs**: Design documents from `kitty-specs/002-external-mariadb-device-source/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓

**Feature**: 002-external-mariadb-device-source | **Branch**: master

---

## Work Package WP01: Config & Model Changes (Priority: P0) 🎯 MVP Start

**Goal**: Establish the new configuration surface (`EXT_DB_*` vars) and update the `Device` model to use plaintext passwords. All downstream WPs depend on this foundation.
**Independent Test**: `Settings` resolves all `EXT_DB_*` fields from env; `Device(password="plaintext")` instantiates without error; `.env.example` contains new vars.
**Prompt**: `tasks/WP01-config-and-model-changes.md`
**Estimated size**: ~280 lines

### Included Subtasks
- [x] T001 Remove `encryption_key_file` field and `ENCRYPTION_KEY_FILE` from `network_inventory/config.py`
- [x] T002 Add `ext_db_host`, `ext_db_port`, `ext_db_user`, `ext_db_password`, `ext_db_name`, `ext_db_query` fields to `Settings` in `config.py`
- [x] T003 Update `_load_settings()` required-var check to use new `EXT_DB_*` vars instead of `ENCRYPTION_KEY_FILE`
- [x] T004 Change `Device.password: bytes` → `str` in `network_inventory/models/device.py`; update docstring
- [x] T005 [P] Update `network_inventory/.env.example` — replace `ENCRYPTION_KEY_FILE` block with `EXT_DB_*` entries

### Implementation Notes
- `EXT_DB_PORT` defaults to `3306`; all other `EXT_DB_*` vars are required.
- `Device.enabled` field is retained (defaulted to `True` by the new external source).
- No other files change in this WP.

### Parallel Opportunities
- T005 (`.env.example` update) can be done at any point — it is documentation only.

### Dependencies
- None (foundation WP).

**Requirements Refs**: FR-003, FR-004, FR-005, FR-006, FR-012

### Risks & Mitigations
- `Device.password` type change will cause type errors in `base_collector.py` until WP04 lands — acceptable since WPs are in isolated worktrees.

---

## Work Package WP02: External DB Source Module (Priority: P0)

**Goal**: Implement `network_inventory/db/external_source.py` — the new device-sourcing module that connects to an external MariaDB, runs the user-supplied query, validates rows, deduplicates, and returns `list[Device]`.
**Independent Test**: Given a test external DB and a valid query → returns correct `Device` list. Given unreachable DB → exits code 1 within 5s. Given zero rows → returns `[]`.
**Prompt**: `tasks/WP02-external-db-source-module.md`
**Estimated size**: ~380 lines

### Included Subtasks
- [ ] T006 Create `network_inventory/db/external_source.py` with `load_devices_from_external_db(settings)` signature
- [ ] T007 Implement external MariaDB connection with `connect_timeout=5`; `sys.exit(1)` on `mariadb.Error`
- [ ] T008 Implement row validation — skip + `WARNING` on missing `ip_address`, `device_type`, `username`, `password`; default `hostname` to `ip_address`, `ssh_port` to `22`
- [ ] T009 Implement deduplication by `ip_address`; `WARNING` per dropped duplicate
- [ ] T010 [P] Update `network_inventory/db/__init__.py` to export `load_devices_from_external_db`

### Implementation Notes
- Connect with `mariadb.connect(host=..., port=..., user=..., password=..., database=..., connect_timeout=5)`.
- Use `cursor.fetchall()` + `cursor.description` to map column names (external query may return columns in any order).
- Assign synthetic `id` values (e.g., enumerate index) since external rows may not have an `id` column.
- `Device.enabled = True` always (filtering is the operator's responsibility via their SQL).

### Parallel Opportunities
- T010 (`__init__.py` export) can be done after T006 stub is created.

### Dependencies
- Depends on WP01 (needs updated `Settings` fields and `Device.password: str`).

**Requirements Refs**: FR-001, FR-002, FR-003, FR-004, FR-007, FR-008, FR-009, FR-010, FR-012

### Risks & Mitigations
- External query column order unknown → use `cursor.description` for column name mapping, not positional indexing.
- `id` may not exist in external schema → synthesise with `enumerate()`.

---

## Work Package WP03: Remove Encryption + Trim DB Layer (Priority: P0)

**Goal**: Delete `utils/encryption.py` entirely, remove `load_enabled_devices()` from `db/queries.py`, and clean up `db/__init__.py`. This is a pure deletion/trimming WP with no new functionality.
**Independent Test**: `from network_inventory.utils.encryption import decrypt_password` raises `ModuleNotFoundError`; `from network_inventory.db import load_enabled_devices` raises `ImportError`; `upsert_inventory_record` still importable.
**Prompt**: `tasks/WP03-remove-encryption-and-trim-db.md`
**Estimated size**: ~220 lines

### Included Subtasks
- [ ] T011 Delete `network_inventory/utils/encryption.py` entirely
- [ ] T012 Remove `load_enabled_devices()` function and `_LOAD_ENABLED_DEVICES_SQL` constant from `network_inventory/db/queries.py`
- [ ] T013 Remove `load_enabled_devices` from imports and exports in `network_inventory/db/__init__.py`
- [ ] T014 [P] Check `requirements.txt` — remove `cryptography` package if `encryption.py` was its only consumer

### Implementation Notes
- `upsert_inventory_record()` in `queries.py` is unchanged — leave it intact.
- After deleting `encryption.py`, verify no other file in `network_inventory/` imports from it (grep for `from network_inventory.utils.encryption`).
- If any collector imports `decrypt_password`, that will be fixed in WP04; do not touch collectors here.

### Parallel Opportunities
- T014 (`requirements.txt` check) is independent.

### Dependencies
- Depends on WP01 (confirms encryption is fully replaced before deleting).

**Requirements Refs**: FR-005, FR-006, FR-011

### Risks & Mitigations
- `cryptography` may be used elsewhere — grep before removing from `requirements.txt`.

---

## Work Package WP04: Update Collectors + main.py Wiring (Priority: P1)

**Goal**: Update `base_collector.py` to use plaintext passwords directly, and update `main.py` to remove the Fernet key step and wire in `load_devices_from_external_db()`. This completes the full end-to-end pipeline change.
**Independent Test**: Tool starts with `EXT_DB_*` env vars and no `ENCRYPTION_KEY_FILE`; devices are loaded from external DB; SSH polling proceeds; no encryption-related errors.
**Prompt**: `tasks/WP04-collectors-and-main-wiring.md`
**Estimated size**: ~350 lines

### Included Subtasks
- [ ] T015 Remove `key: bytes` parameter from `BaseCollector.__init__()` in `network_inventory/collectors/base_collector.py`; remove `self._key` attribute
- [ ] T016 Remove `decrypt_password()` import and call from `BaseCollector._connect()`; use `self.device.password` directly as the `password` arg to `ConnectHandler`
- [ ] T017 Remove Step 2 (Fernet key load) from `network_inventory/main.py` — remove `load_key()` import, key validation block, and `sys.exit(1)` on key error
- [ ] T018 Replace Step 4 (`load_enabled_devices(conn)`) with `load_devices_from_external_db(settings)` in `main.py`; update imports; remove now-unused `get_connection()` call at step 4
- [ ] T019 Remove `key=key` from collector instantiation in `main.py` (`collector_class(device=device, key=key)` → `collector_class(device=device)`)

### Implementation Notes
- In `main.py`, the local MariaDB pool (`get_pool()`) is still needed for result writes (step 3 stays).
- Update `main.py` module docstring startup sequence: remove "3. Load and validate Fernet key file"; renumber steps.
- `BaseCollector._connect()` still calls `del plaintext_password` — adjust to delete after `ConnectHandler()` call since password is now a local variable reference to `self.device.password`. Consider just removing the `del` since plaintext is already in the `Device` object.

### Parallel Opportunities
- T015+T016 (`base_collector.py`) and T017+T018+T019 (`main.py`) can proceed in parallel as they touch different files.

### Dependencies
- Depends on WP02 (needs `load_devices_from_external_db`) and WP03 (encryption removed).

**Requirements Refs**: FR-001, FR-002, FR-005, FR-006, FR-007, FR-008, FR-011

### Risks & Mitigations
- Netmiko `ConnectHandler` accepts `str` for password natively — no conversion needed.
- `del plaintext_password` in `_connect()` needs reconsideration since password is now plaintext in `Device` — document the security tradeoff.

---

## Work Package WP05: Integration Tests (Priority: P2)

**Goal**: Update the integration test suite to cover the new external DB source flow and remove all encryption-related test infrastructure.
**Independent Test**: `pytest tests/integration/` passes with zero encryption-related imports or fixtures; `test_load_devices_from_external_db` covers happy path, zero rows, missing fields, and duplicates.
**Prompt**: `tasks/WP05-integration-tests.md`
**Estimated size**: ~300 lines

### Included Subtasks
- [ ] T020 Update `tests/integration/conftest.py` — remove Fernet/encryption fixtures; add `external_db_conn` fixture and `ext_db_settings` fixture pointing to a test external DB
- [ ] T021 Update `tests/integration/test_db.py` — remove encryption tests; add `test_load_devices_from_external_db` covering: happy path, zero-row result, row with missing `ip_address`, duplicate rows, unreachable DB (mocked/monkeypatched)
- [ ] T022 Update `tests/integration/test_full_run.py` — replace local device table sourcing with external DB fixture; verify full run completes with external device list

### Implementation Notes
- For unreachable DB test: monkeypatch `mariadb.connect` to raise `mariadb.Error`; verify `SystemExit` with code 1.
- The `external_db_conn` fixture can point at the same local MariaDB test instance with a separate test database/schema to avoid a real external DB dependency.
- Remove all references to `ENCRYPTION_KEY_FILE`, `fernet_key`, `load_key`, `decrypt_password` from test files.

### Parallel Opportunities
- T021 and T022 can proceed in parallel once T020 fixtures are available.

### Dependencies
- Depends on WP04 (full pipeline wired before tests can pass end-to-end).

**Requirements Refs**: FR-001, FR-002, FR-007, FR-008, FR-009, FR-010, SC-001, SC-002, SC-003, SC-005

### Risks & Mitigations
- Integration tests require a live MariaDB instance — ensure CI/Docker setup supports two DB connections (local results + external source).

---

## Dependency & Execution Summary

```
WP01 (config + model)
  ├── WP02 (external source module)
  │     └── WP04 (collectors + main wiring)
  │           └── WP05 (integration tests)
  └── WP03 (remove encryption + trim DB)
        └── WP04
```

- **Parallel start**: WP01 has no dependencies — start immediately.
- **After WP01**: WP02 and WP03 can proceed in parallel.
- **After WP02 + WP03**: WP04 can start.
- **After WP04**: WP05 can start.

**MVP Scope**: WP01 + WP02 + WP03 + WP04 constitute a fully working pipeline. WP05 is test hardening.

---

## Subtask Index

| Subtask ID | Summary | Work Package | Parallel? |
|------------|---------|--------------|-----------|
| T001 | Remove `encryption_key_file` from `config.py` | WP01 | No |
| T002 | Add `EXT_DB_*` fields to `Settings` | WP01 | No |
| T003 | Update `_load_settings()` required-var check | WP01 | No |
| T004 | `Device.password: bytes` → `str` | WP01 | No |
| T005 | Update `.env.example` | WP01 | Yes |
| T006 | Create `db/external_source.py` skeleton | WP02 | No |
| T007 | Implement external DB connection with timeout | WP02 | No |
| T008 | Implement row validation + skip logic | WP02 | No |
| T009 | Implement deduplication by `ip_address` | WP02 | No |
| T010 | Export `load_devices_from_external_db` from `db/__init__.py` | WP02 | Yes |
| T011 | Delete `utils/encryption.py` | WP03 | No |
| T012 | Remove `load_enabled_devices()` from `db/queries.py` | WP03 | No |
| T013 | Remove `load_enabled_devices` from `db/__init__.py` | WP03 | No |
| T014 | Check/remove `cryptography` from `requirements.txt` | WP03 | Yes |
| T015 | Remove `key` param from `BaseCollector.__init__()` | WP04 | Yes |
| T016 | Use plaintext password directly in `BaseCollector._connect()` | WP04 | Yes |
| T017 | Remove Fernet key step from `main.py` | WP04 | No |
| T018 | Wire `load_devices_from_external_db()` into `main.py` | WP04 | No |
| T019 | Remove `key=key` from collector instantiation in `main.py` | WP04 | No |
| T020 | Update `conftest.py` with external DB fixtures | WP05 | No |
| T021 | Add `test_load_devices_from_external_db` tests | WP05 | Yes |
| T022 | Update `test_full_run.py` for external DB source | WP05 | Yes |
