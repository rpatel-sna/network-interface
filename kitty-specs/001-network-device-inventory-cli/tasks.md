# Work Packages: Network Device Inventory CLI

**Inputs**: Design documents from `kitty-specs/001-network-device-inventory-cli/`
**Prerequisites**: spec.md, plan.md, data-model.md, research.md, contracts/schema.sql, quickstart.md

**Tests**: Integration tests explicitly required by plan.md (real devices + MariaDB, pytest, no mocked units in v1).

**Organization**: 26 fine-grained subtasks (T001–T026) rolled up into 8 work packages (WP01–WP08).
Each work package is independently deliverable and testable.

**Prompt Files**: Each work package has a matching prompt in `kitty-specs/001-network-device-inventory-cli/tasks/`.

---

## Work Package WP01: Project Setup & Configuration (Priority: P0)

**Goal**: Establish the project skeleton, dependency manifest, and configuration layer so all downstream WPs can start with a stable foundation.
**Independent Test**: `python -c "from network_inventory.config import Settings; s = Settings()"` raises a clear `EnvironmentError` when required env vars are absent, and succeeds when `.env` is populated.
**Prompt**: `tasks/WP01-project-setup-and-configuration.md`

### Included Subtasks
- [ ] T001 Create project directory structure and `requirements.txt`
- [ ] T002 Implement `network_inventory/config.py` — Settings dataclass + env/dotenv loading + startup validation
- [ ] T003 Create `network_inventory/.env.example` template with all required and optional env vars documented

### Implementation Notes
- Use `python-dotenv` to load `.env` at import time. Settings is a simple dataclass (not Pydantic) to keep dependencies lean.
- Validate at import: if `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, or `ENCRYPTION_KEY_FILE` is absent, raise `EnvironmentError` with a clear message listing the missing variable.
- Required env vars: `DB_HOST`, `DB_PORT` (default 3306), `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `ENCRYPTION_KEY_FILE`.
- Optional env vars: `MAX_THREADS` (default 10), `SSH_TIMEOUT` (default 30), `LOG_FILE` (default `inventory.log`), `LOG_LEVEL` (default `INFO`).

### Parallel Opportunities
- T001 (directory structure) can be done first; T002 and T003 can proceed in parallel once structure exists.

### Dependencies
- None (starting package).

### Risks & Mitigations
- Missing env var at startup should give a precise error, not a cryptic `KeyError`.
- `requirements.txt` should pin major versions to avoid compatibility drift.

**Requirements Refs**: FR-009, FR-010, FR-012, FR-013

---

## Work Package WP02: Foundation Utilities & Models (Priority: P0)

**Goal**: Deliver shared data structures and utility helpers (models, encryption, logging, error classification) that all other WPs depend on.
**Independent Test**: `from network_inventory.models.device import Device, CollectionResult` imports cleanly; `from network_inventory.utils.encryption import load_key, decrypt_password` can round-trip a test value; `from network_inventory.utils.logger import get_logger` returns a logger with both handlers.
**Prompt**: `tasks/WP02-foundation-utilities-and-models.md`

### Included Subtasks
- [ ] T004 [P] Implement `network_inventory/models/device.py` — `Device` + `CollectionResult` dataclasses
- [ ] T005 [P] Implement `network_inventory/utils/encryption.py` — Fernet key file load + in-memory decrypt helper
- [ ] T006 [P] Implement `network_inventory/utils/logger.py` — `RotatingFileHandler` + stdout dual logging
- [ ] T007 [P] Implement `network_inventory/utils/error_handler.py` — exception → `(status, error_message)` mapping

### Implementation Notes
- `Device` mirrors `devices` table fields; `password` field holds the encrypted `bytes` from the DB.
- `CollectionResult` is a transient dataclass — `status: Literal['success','failed','timeout']`, `attempted_at`, `succeeded_at: datetime | None`.
- `encrypt.py`: key loaded from `ENCRYPTION_KEY_FILE` path; `decrypt_password(key, encrypted_bytes) -> str` — never logs plaintext.
- Logger: `RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)` + `StreamHandler(sys.stdout)`. Format: `%(asctime)s | %(levelname)s | %(name)s | %(message)s`.
- `error_handler.py`: maps `netmiko.exceptions.NetmikoTimeoutException` → `timeout`, `netmiko.exceptions.NetmikoAuthenticationException` → `failed`, all other exceptions → `failed` with `str(e)`.

### Parallel Opportunities
- T004, T005, T006, T007 are independent and can be implemented simultaneously.

### Dependencies
- Depends on WP01 (config import + env vars present).

### Risks & Mitigations
- Fernet key file permissions: warn at load time if file is world-readable (`stat.S_IROTH`).
- Never pass decrypted passwords to `logger.debug()`.

**Requirements Refs**: FR-006, FR-007, FR-009, FR-010, FR-012

---

## Work Package WP03: Database Layer (Priority: P0)

**Goal**: Implement the MariaDB connection pool (with fail-fast startup) and all SQL operations (device loading + upsert) that the orchestrator uses.
**Independent Test**: With a live MariaDB and correct env vars, `load_enabled_devices()` returns a list of `Device` objects; with wrong DB host, calling `get_connection_pool()` raises immediately with a non-zero exit message.
**Prompt**: `tasks/WP03-database-layer.md`

### Included Subtasks
- [ ] T008 Implement `network_inventory/db/connection.py` — MariaDB connection pool + fail-fast startup check
- [ ] T009 Implement `network_inventory/db/queries.py` — `load_enabled_devices()` + `upsert_inventory_record()`
- [ ] T010 Implement `network_inventory/db/__init__.py` — package init + public exports

### Implementation Notes
- `connection.py`: create pool via `mariadb.connect()` at startup; any `mariadb.Error` at pool creation → log error, `sys.exit(1)` (FR-013).
- `queries.py`: `load_enabled_devices()` → `SELECT ... FROM devices WHERE enabled = 1`; return `list[Device]`.
- `upsert_inventory_record(conn, result: CollectionResult)` → `INSERT INTO device_inventory (...) VALUES (...) ON DUPLICATE KEY UPDATE ...` keyed by `device_id` (FR-008).
- `last_success` is only updated when `status = 'success'`; on failure/timeout, preserve existing `last_success` or set NULL if first attempt.
- `password` column is `VARBINARY(512)` — fetch as bytes.

### Parallel Opportunities
- T008 and T009 can proceed in parallel once WP01 Settings are importable.

### Dependencies
- Depends on WP01 (Settings), WP02 (Device + CollectionResult dataclasses).

### Risks & Mitigations
- Connection pool exhaustion under high concurrency: use one connection per thread worker or acquire/release from pool per write.
- `ON DUPLICATE KEY UPDATE` must not overwrite `last_success` when new status is failed/timeout.

**Requirements Refs**: FR-001, FR-008, FR-013

---

## Work Package WP04: Collector Architecture (Priority: P0)

**Goal**: Establish the pluggable collector base class and registry so that all individual collector WPs (WP05, WP06) have a stable contract to implement against, and adding a new device type requires only one new file (FR-014, SC-004).
**Independent Test**: `from network_inventory.collectors import get_collector; get_collector('unknown_type')` returns `None` and logs a warning; `get_collector('cisco_ios')` returns the `CiscoIOSCollector` class (after WP05 is merged).
**Prompt**: `tasks/WP04-collector-architecture.md`

### Included Subtasks
- [ ] T011 Implement `network_inventory/collectors/base_collector.py` — `BaseCollector` abstract class with Netmiko SSH + abstract `get_serial_number()` + `get_firmware_version()`
- [ ] T012 Implement `network_inventory/collectors/__init__.py` — `COLLECTOR_REGISTRY` dict + `get_collector(device_type)` factory + unknown type warning

### Implementation Notes
- `BaseCollector.__init__(device: Device, settings: Settings)` — stores device + settings; does not open SSH yet.
- `BaseCollector.connect()` → `Netmiko.ConnectHandler(device_type=..., host=..., port=..., username=..., password=plaintext, timeout=settings.ssh_timeout)`. Call `decrypt_password()` inside `connect()` only.
- Abstract methods: `get_serial_number(self) -> str | None` and `get_firmware_version(self) -> str | None`.
- `collect(self) -> CollectionResult` — concrete template method: calls `connect()`, calls both abstract methods, disconnects, returns `CollectionResult(status='success', ...)`. `NetmikoTimeoutException` → `timeout` result; all others → `failed` result via `error_handler`.
- `COLLECTOR_REGISTRY: dict[str, type[BaseCollector]]` populated by individual collector modules. `get_collector(device_type)` looks up registry; logs `WARNING: Unknown device_type '{device_type}' — skipping` and returns `None` if not found.
- Extensibility check: adding a new collector must only require (1) creating one file and (2) adding one entry to `COLLECTOR_REGISTRY`. No other files change.

### Parallel Opportunities
- T011 and T012 are tightly coupled (T012 imports from T011); implement T011 first.

### Dependencies
- Depends on WP01 (Settings), WP02 (Device, CollectionResult, encryption, error_handler).

### Risks & Mitigations
- Netmiko SSH connection must be closed in a `finally` block to avoid leaking connections.
- Ruckus wireless `device_type` is unconfirmed — base class must tolerate `ConnectHandler` raising on unknown types.

**Requirements Refs**: FR-003, FR-004, FR-006, FR-007, FR-014

---

## Work Package WP05: Cisco Collectors (Priority: P1)

**Goal**: Implement Cisco IOS/IOS-XE and Cisco NX-OS collectors, register them in the COLLECTOR_REGISTRY, and validate regex parsing against documented command output formats.
**Independent Test**: Instantiate `CiscoIOSCollector` with a `Device(device_type='cisco_ios', ...)` and a mock connection; verify `get_serial_number()` returns the value after `SN:` in sample `show inventory` output, and `get_firmware_version()` returns the version string from `show version` output.
**Prompt**: `tasks/WP05-cisco-collectors.md`

### Included Subtasks
- [ ] T013 [P] Implement `network_inventory/collectors/cisco_ios.py` — IOS + IOS-XE: `show inventory` → serial, `show version` → firmware; register `cisco_ios` and `cisco_xe`
- [ ] T014 [P] Implement `network_inventory/collectors/cisco_nxos.py` — NX-OS: `show inventory` → serialnum field, `show version` → `NXOS:` version line; register `cisco_nxos`

### Implementation Notes
- Cisco IOS/IOS-XE serial: regex `r'SN:\s*(\S+)'` on `show inventory` output (first match for chassis).
- Cisco IOS/IOS-XE firmware: regex `r'(?:Cisco IOS Software|IOS-XE).*Version\s+([\d.()A-Za-z]+)'` on `show version`.
- NX-OS serial: `r'serialnum\s*:\s*(\S+)'` (case-insensitive) on `show inventory`.
- NX-OS firmware: `r'NXOS:\s+version\s+([\S]+)'` on `show version`.
- If regex returns no match: log DEBUG with raw output excerpt, return `None` for that field.
- Both `CiscoIOSCollector` and `CiscoNXOSCollector` use `device_type` from `Device.device_type` when calling Netmiko `ConnectHandler`.
- Register in `COLLECTOR_REGISTRY`: `{'cisco_ios': CiscoIOSCollector, 'cisco_xe': CiscoIOSCollector, 'cisco_nxos': CiscoNXOSCollector}`.

### Parallel Opportunities
- T013 and T014 are fully independent — implement simultaneously.

### Dependencies
- Depends on WP04 (BaseCollector + registry).

### Risks & Mitigations
- Cisco IOS `show inventory` may return multiple chassis entries on modular devices — use first `SN:` match for top-level chassis.
- Version string formats differ between IOS and IOS-XE; test against both patterns.

**Requirements Refs**: FR-003, FR-004

---

## Work Package WP06: HP, Aruba & Ruckus Collectors (Priority: P1)

**Goal**: Implement the remaining four collectors (HP ProCurve, Aruba, Ruckus ICX, Ruckus wireless) and register them in COLLECTOR_REGISTRY, including handling the unconfirmed Ruckus wireless device_type.
**Independent Test**: Each collector's `get_serial_number()` and `get_firmware_version()` return the expected string from sample command output; Ruckus wireless collector attempts `generic_termserver` and falls back gracefully.
**Prompt**: `tasks/WP06-hp-aruba-ruckus-collectors.md`

### Included Subtasks
- [ ] T015 [P] Implement `network_inventory/collectors/hp_procurve.py` — `show system information` → serial + firmware; register `hp_procurve`
- [ ] T016 [P] Implement `network_inventory/collectors/aruba.py` — `show system information` → serial + firmware; register `aruba_procurve`
- [ ] T017 [P] Implement `network_inventory/collectors/ruckus_icx.py` — `show version` → serial + firmware; register `ruckus_fastiron`
- [ ] T018 Implement `network_inventory/collectors/ruckus_wireless.py` — `show version` with `generic_termserver` / `linux` fallback + caveat note; register `ruckus_wireless`

### Implementation Notes
- HP ProCurve serial: `r'Serial Number\s*:\s*(\S+)'`; firmware: `r'Software revision\s*:\s*(\S+)'` on `show system information`.
- Aruba serial: same pattern as HP on `show system information`; firmware: `r'[Ff]irmware[: ]+(\S+)'` or vendor-specific line.
- Ruckus ICX serial: `r'Serial #\s*:\s*(\S+)'`; firmware: `r'SW:\s+Version\s+([\S]+)'` on `show version`.
- Ruckus wireless: first try `device_type='ruckus_wireless'`; on `NetmikoAuthenticationException` or unsupported type, retry with `linux`, then `generic_termserver`. Log caveat: "Ruckus wireless device_type is unconfirmed — see research.md open item."
- Ruckus wireless serial: `r'Serial Number\s*:\s*(\S+)'`; firmware: `r'Version\s+([\S]+)'` (first match).

### Parallel Opportunities
- T015, T016, T017 are fully independent — implement simultaneously. T018 depends on T017's Ruckus command patterns.

### Dependencies
- Depends on WP04 (BaseCollector + registry).

### Risks & Mitigations
- Ruckus wireless: if all device_type options fail, store error in `error_message` and return `status='failed'` — do not crash.
- Aruba and HP may share identical command output; if confirmed during integration testing, consider consolidating (out of scope for this WP — document as follow-up).

**Requirements Refs**: FR-003, FR-004

---

## Work Package WP07: Core Orchestration (Priority: P1) 🎯 MVP

**Goal**: Implement `main.py` — the entry point that ties all layers together: startup validation, device loading, concurrent polling via ThreadPoolExecutor, result persistence, and completion summary.
**Independent Test**: Populate `devices` table with ≥1 enabled device, run `python network_inventory/main.py`, verify a row in `device_inventory` with `status='success'`, non-null `serial_number`, non-null `firmware_version`, and a printed summary showing counts.
**Prompt**: `tasks/WP07-core-orchestration.md`

### Included Subtasks
- [ ] T019 Startup validation — config load, key file existence/readability check, DB connection test; exit(1) on any failure
- [ ] T020 Device loading — call `load_enabled_devices()`; handle zero-devices case with clean exit message
- [ ] T021 Collector dispatch — for each device, look up collector via `get_collector()`; skip unknown types with warning; submit `device.collect()` to `ThreadPoolExecutor`
- [ ] T022 Result collection + DB upsert — iterate `as_completed()`, catch per-future exceptions, upsert each `CollectionResult` immediately; accumulate counts
- [ ] T023 Completion summary — print total polled / success / failed / timeout to stdout; exit 0

### Implementation Notes
- Startup order: (1) load Settings, (2) verify `ENCRYPTION_KEY_FILE` exists and is readable, (3) establish DB pool (exits on failure per FR-013), (4) load enabled devices, (5) check for zero devices.
- Zero enabled devices: print "No enabled devices found. Nothing to poll." and exit 0.
- `ThreadPoolExecutor(max_workers=settings.max_threads)` with `future_to_device: dict[Future, Device]`.
- Submit: for each device with a known collector, `executor.submit(collector_instance.collect)`. Skip unknown device_types silently after warning.
- `as_completed()` loop: on `result()` success — upsert, increment success; on exception caught at future level — build `CollectionResult(status='failed', error_message=str(exc))`, upsert, increment failed.
- `last_success` timestamp: set to `datetime.utcnow()` only when `status='success'`.
- Summary format (matches quickstart.md):
  ```
  Inventory run complete.
    Total polled : {n}
    Success      : {s}
    Failed       : {f}
    Timeout      : {t}
  ```
- Log each poll result at INFO level: `{hostname} ({ip}) — {status}`.

### Parallel Opportunities
- T019, T020 are sequential (startup must complete before loading). T021–T023 are the main loop — sequential in logic but internally concurrent.

### Dependencies
- Depends on WP02 (models, utils), WP03 (DB layer), WP04 (collector registry), WP05 (Cisco collectors registered), WP06 (HP/Aruba/Ruckus collectors registered).

### Risks & Mitigations
- Thread safety: `upsert_inventory_record()` must be called inside the main thread (after future.result()) or with a per-thread connection, not a shared connection.
- A future that raises an unexpected exception must not silently drop the device — always write a `failed` record.
- `max_workers` set too high may exhaust MariaDB connections or SSH sessions.

**Requirements Refs**: FR-001, FR-002, FR-005, FR-006, FR-007, FR-008, FR-011, FR-012, FR-013

---

## Work Package WP08: Integration Tests (Priority: P2)

**Goal**: Write the integration test suite (pytest) that validates end-to-end behaviour against a live MariaDB and real (or test) network devices.
**Independent Test**: `pytest tests/integration/ -v` passes when configured against a test DB with seeded data; tests that require live devices are skipped automatically if `TEST_DEVICE_AVAILABLE=false`.
**Prompt**: `tasks/WP08-integration-tests.md`

### Included Subtasks
- [ ] T024 [P] `tests/integration/test_db.py` — upsert correctness, connection failure at startup, minimal-privilege check
- [ ] T025 [P] `tests/integration/test_full_run.py` — full run happy path (US1), disabled device exclusion (US3), partial-failure run (US2)
- [ ] T026 [P] `tests/integration/test_collectors.py` — per-collector SSH tests with real device annotation; skip markers for unavailable hardware

### Implementation Notes
- All tests load config from `.env.test` (or `TEST_` prefixed env vars) — never use production credentials.
- `test_db.py`: seed a test device, run `upsert_inventory_record()` twice, assert second write overwrites correctly; test that missing DB host causes `sys.exit(1)`.
- `test_full_run.py`: invoke `main.py` as subprocess or call orchestrator function directly; assert `device_inventory` row has correct status + timestamps; assert disabled device has no new row.
- `test_collectors.py`: annotate real-device tests with `@pytest.mark.real_device` and use `pytest -m "not real_device"` for CI; test the collect() template method with a mock SSH connection for unit coverage.
- Confirm spec acceptance scenarios from US1, US2, US3 pass via integration tests.

### Parallel Opportunities
- T024, T025, T026 are independent — implement simultaneously.

### Dependencies
- Depends on WP07 (all implementation complete and importable).

### Risks & Mitigations
- Real device tests must not be required for CI to pass — use skip markers.
- Test DB cleanup: truncate `device_inventory` between test cases with fixtures.

**Requirements Refs**: FR-001, FR-002, FR-005, FR-006, FR-007, FR-008

---

## Dependency & Execution Summary

```
WP01 (Setup)
  └── WP02 (Foundation Utilities)
        ├── WP03 (Database Layer)
        └── WP04 (Collector Architecture)
              ├── WP05 (Cisco Collectors)
              └── WP06 (HP/Aruba/Ruckus Collectors)
                    └── WP07 (Core Orchestration) ← requires WP02, WP03, WP04, WP05, WP06
                          └── WP08 (Integration Tests)
```

- **WP01 → WP02 → WP03**: Strictly sequential foundation chain.
- **WP04 parallel with WP03**: Collector base can be built while DB layer is being implemented.
- **WP05 parallel with WP06**: All individual collectors are independent of each other.
- **WP07**: Requires all prior WPs; is the integration point.
- **WP08**: Can begin once WP07 is importable (even if some collectors aren't yet on real hardware).
- **MVP Scope**: WP01 + WP02 + WP03 + WP04 + WP05 (Cisco only) + WP07 = minimal working tool for Cisco devices.

---

## Subtask Index (Reference)

| Subtask ID | Summary | Work Package | Priority | Parallel? |
|---|---|---|---|---|
| T001 | Create project structure + requirements.txt | WP01 | P0 | No |
| T002 | config.py — Settings + env validation | WP01 | P0 | No |
| T003 | .env.example template | WP01 | P0 | Yes |
| T004 | models/device.py — Device + CollectionResult | WP02 | P0 | Yes |
| T005 | utils/encryption.py — Fernet key load + decrypt | WP02 | P0 | Yes |
| T006 | utils/logger.py — dual logging | WP02 | P0 | Yes |
| T007 | utils/error_handler.py — exception → status | WP02 | P0 | Yes |
| T008 | db/connection.py — pool + fail-fast | WP03 | P0 | Yes |
| T009 | db/queries.py — load + upsert | WP03 | P0 | Yes |
| T010 | db/__init__.py | WP03 | P0 | No |
| T011 | collectors/base_collector.py — BaseCollector + Netmiko | WP04 | P0 | No |
| T012 | collectors/__init__.py — registry + factory | WP04 | P0 | No |
| T013 | collectors/cisco_ios.py — IOS + IOS-XE | WP05 | P1 | Yes |
| T014 | collectors/cisco_nxos.py — NX-OS | WP05 | P1 | Yes |
| T015 | collectors/hp_procurve.py | WP06 | P1 | Yes |
| T016 | collectors/aruba.py | WP06 | P1 | Yes |
| T017 | collectors/ruckus_icx.py | WP06 | P1 | Yes |
| T018 | collectors/ruckus_wireless.py — with fallback | WP06 | P1 | No |
| T019 | main.py — startup validation | WP07 | P1 | No |
| T020 | main.py — device loading + zero-devices | WP07 | P1 | No |
| T021 | main.py — ThreadPoolExecutor dispatch | WP07 | P1 | No |
| T022 | main.py — result collection + DB upsert | WP07 | P1 | No |
| T023 | main.py — completion summary + exit | WP07 | P1 | No |
| T024 | tests/integration/test_db.py | WP08 | P2 | Yes |
| T025 | tests/integration/test_full_run.py | WP08 | P2 | Yes |
| T026 | tests/integration/test_collectors.py | WP08 | P2 | Yes |

---

> This file is the high-level checklist. Deep implementation detail lives inside each `tasks/WPxx-*.md` prompt file.
