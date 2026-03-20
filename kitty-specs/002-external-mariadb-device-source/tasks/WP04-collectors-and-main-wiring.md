---
work_package_id: WP04
title: Update Collectors and main.py Wiring
lane: "for_review"
dependencies:
- WP02
base_branch: 002-external-mariadb-device-source-WP02
base_commit: 58161d63ca33ed412099a8cfc862b42e3d27f9ce
created_at: '2026-03-20T15:37:04.899339+00:00'
subtasks:
- T015
- T016
- T017
- T018
- T019
phase: Phase 2 - Integration
assignee: ''
agent: "claude-sonnet-4-6"
shell_pid: "38292"
review_status: ''
reviewed_by: ''
history:
- timestamp: '2026-03-20T14:42:47Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-001
- FR-002
- FR-005
- FR-006
- FR-007
- FR-008
- FR-011
---

# Work Package Prompt: WP04 – Update Collectors and main.py Wiring

## ⚠️ IMPORTANT: Review Feedback Status

Check `review_status` in frontmatter. If `has_feedback`, read the Review Feedback section below.

---

## Review Feedback

*[Empty — no feedback yet.]*

---

## Objectives & Success Criteria

- `BaseCollector.__init__()` no longer accepts a `key: bytes` parameter.
- `BaseCollector._connect()` uses `self.device.password` (a `str`) directly as the SSH password — no `decrypt_password()` call.
- `main.py` no longer imports or calls `load_key()`.
- `main.py` calls `load_devices_from_external_db(settings)` instead of `load_enabled_devices(conn)`.
- `collector_class(device=device)` — no `key=key` argument.
- Running the tool with `EXT_DB_*` env vars and no `ENCRYPTION_KEY_FILE` succeeds end-to-end.

## Context & Constraints

- **Workspace**: `.worktrees/002-external-mariadb-device-source-WP04/`
- **Depends on**: WP02 (`load_devices_from_external_db` available) AND WP03 (`encryption.py` deleted, `load_enabled_devices` removed)
- **Spec**: FR-001, FR-002, FR-005, FR-006, FR-007, FR-008, FR-011
- The local MariaDB pool (`get_pool()`) is still used for writing results — do not remove it from `main.py`.
- T015 and T016 (`base_collector.py`) can be done in parallel with T017–T019 (`main.py`) since they are different files.

**Run from workspace root:**
```bash
spec-kitty implement WP04 --base WP03
```
(WP03 is the last merged dependency; WP02 is an ancestor of WP03 in this stack.)

---

## Subtasks & Detailed Guidance

### Subtask T015 – Remove `key` parameter from `BaseCollector.__init__()`

**Purpose**: The Fernet key is no longer needed. Removing it from the constructor cleans the public API of `BaseCollector` and all its subclasses.

**File**: `network_inventory/collectors/base_collector.py`

**Steps**:
1. Remove the `key: bytes` parameter from `__init__`:
   ```python
   # BEFORE:
   def __init__(
       self,
       device: Device,
       key: bytes,
       app_settings: Settings | None = None,
   ) -> None:
       self.device = device
       self._key = key
       self._settings = app_settings or default_settings
       self.connection: ConnectHandler | None = None

   # AFTER:
   def __init__(
       self,
       device: Device,
       app_settings: Settings | None = None,
   ) -> None:
       self.device = device
       self._settings = app_settings or default_settings
       self.connection: ConnectHandler | None = None
   ```
2. Remove the `self._key = key` line.
3. Update the class docstring if it references the key parameter.

---

### Subtask T016 – Use plaintext password directly in `BaseCollector._connect()`

**Purpose**: Remove the `decrypt_password()` call — the password on `self.device.password` is already a plaintext `str`. Pass it directly to `ConnectHandler`.

**File**: `network_inventory/collectors/base_collector.py`

**Steps**:
1. Remove the import:
   ```python
   # DELETE:
   from network_inventory.utils.encryption import decrypt_password
   ```
2. Update `_connect()`:
   ```python
   # BEFORE:
   def _connect(self) -> None:
       """Open an SSH session to the device. Sets self.connection."""
       plaintext_password = decrypt_password(self._key, self.device.password)
       try:
           self.connection = ConnectHandler(
               device_type=self.device.device_type,
               host=self.device.ip_address,
               port=self.device.ssh_port,
               username=self.device.username,
               password=plaintext_password,
               timeout=self._settings.ssh_timeout,
               session_log=None,
               global_delay_factor=2,
           )
       finally:
           del plaintext_password

   # AFTER:
   def _connect(self) -> None:
       """Open an SSH session to the device. Sets self.connection."""
       self.connection = ConnectHandler(
           device_type=self.device.device_type,
           host=self.device.ip_address,
           port=self.device.ssh_port,
           username=self.device.username,
           password=self.device.password,
           timeout=self._settings.ssh_timeout,
           session_log=None,
           global_delay_factor=2,
       )
   ```
3. Remove the `try/finally` wrapper (it existed only to `del plaintext_password`).

**Notes**:
- `self.device.password` is now a `str` — Netmiko's `ConnectHandler` accepts `str` natively.
- The `del plaintext_password` pattern is no longer needed since we never extract the password into a local variable; `self.device.password` remains on the `Device` object for the run's lifetime.

---

### Subtask T017 – Remove Fernet key step from `main.py`

**Purpose**: Step 2 of the startup sequence (load and validate Fernet key file) is dead code. Removing it simplifies startup and ensures no `ENCRYPTION_KEY_FILE` error can appear.

**File**: `network_inventory/main.py`

**Steps**:
1. Delete the entire Step 2 block:
   ```python
   # DELETE the entire block:
   # ------------------------------------------------------------------
   # Step 2: Validate Fernet key file (FR-010)
   # ------------------------------------------------------------------
   from network_inventory.utils.encryption import load_key

   try:
       key = load_key(settings.encryption_key_file)
   except (FileNotFoundError, PermissionError, ValueError) as exc:
       logger.error("Encryption key error: %s", exc)
       sys.exit(1)

   logger.debug("Encryption key loaded from %s", settings.encryption_key_file)
   ```
2. Update the module docstring startup sequence at the top of the file — remove the "3. Load and validate Fernet key file" line and renumber the remaining steps:
   ```
   Startup sequence:
       1. Configure logging
       2. Validate config (EnvironmentError → exit 1)
       3. Establish MariaDB connection pool for result writes (fail-fast → exit 1)
       4. Load device list from external MariaDB source (fail-fast → exit 1)
       5. Handle zero-devices edge case (exit 0 with message)
       6. Dispatch all devices to ThreadPoolExecutor
       7. Collect results and upsert each to local DB
       8. Print completion summary and exit 0
   ```

---

### Subtask T018 – Wire `load_devices_from_external_db()` into `main.py`

**Purpose**: Replace the old device-loading step (local `devices` table) with the new external source.

**File**: `network_inventory/main.py`

**Steps**:
1. Update the Step 3 (now Step 3 after renumbering) pool setup — the `get_pool()` call remains for the local results DB.
2. Replace the old Step 4 block:
   ```python
   # BEFORE (Step 4 — load from local DB):
   # ------------------------------------------------------------------
   # Step 4: Load enabled devices (FR-001)
   # ------------------------------------------------------------------
   conn = get_connection()
   try:
       devices = load_enabled_devices(conn)
   finally:
       conn.close()

   # AFTER (Step 4 — load from external DB):
   # ------------------------------------------------------------------
   # Step 4: Load device list from external DB source (FR-001, FR-002)
   # ------------------------------------------------------------------
   from network_inventory.db import load_devices_from_external_db

   devices = load_devices_from_external_db(settings)
   ```
3. Remove the now-unused `load_enabled_devices` import from the Step 3 import line:
   ```python
   # BEFORE:
   from network_inventory.db import get_connection, get_pool, load_enabled_devices, upsert_inventory_record

   # AFTER:
   from network_inventory.db import get_connection, get_pool, load_devices_from_external_db, upsert_inventory_record
   ```
   Wait — `get_connection` is still needed for result writes (step 7). Keep it.

**Notes**:
- `load_devices_from_external_db()` returns `[]` on zero rows (does not exit). The existing zero-devices edge case check in Step 5 handles this correctly — no change needed there.

---

### Subtask T019 – Remove `key=key` from collector instantiation

**Purpose**: `BaseCollector.__init__()` no longer accepts `key` (fixed in T015). Remove the argument at the call site.

**File**: `network_inventory/main.py`

**Steps**:
1. Find the collector instantiation line:
   ```python
   # BEFORE:
   collector = collector_class(device=device, key=key)

   # AFTER:
   collector = collector_class(device=device)
   ```
2. The `key` variable no longer exists (removed in T017) — this change prevents a `NameError`.

---

## Risks & Mitigations

- **`get_connection()` still needed** — don't remove it from imports; it is used in the result-write loop (Step 7).
- **Subclasses of `BaseCollector`** (Cisco, Aruba, etc.) — they call `super().__init__(device=device, key=key, ...)` only if they override `__init__`. A quick grep confirms none of the collector subclasses in this codebase override `__init__`, so no subclass changes are needed.
  ```bash
  grep -n "__init__" network_inventory/collectors/*.py
  ```
  Expected: only `base_collector.py` defines `__init__`.

## Review Guidance

Reviewer checks:
1. `base_collector.py`: no `key` param in `__init__`, no `self._key`, no `decrypt_password` import, `_connect()` uses `self.device.password` directly, no `try/finally` around `ConnectHandler`.
2. `main.py`: no `load_key` import, no `key` variable, no `key=key` at collector instantiation, Step 4 calls `load_devices_from_external_db(settings)`.
3. Module docstring startup sequence is up to date (8 steps, no Fernet step).
4. Running `python -m network_inventory.main` with valid `EXT_DB_*` vars and no `ENCRYPTION_KEY_FILE` starts without error.

## Activity Log

- 2026-03-20T14:42:47Z – system – lane=planned – Prompt created.
- 2026-03-20T15:37:05Z – claude-sonnet-4-6 – shell_pid=38292 – lane=doing – Assigned agent via workflow command
- 2026-03-20T15:40:05Z – claude-sonnet-4-6 – shell_pid=38292 – lane=for_review – Ready for review: base_collector.py and ruckus_wireless.py updated to use plaintext password directly; main.py wired to load_devices_from_external_db(); Fernet key step removed; key=key removed from collector instantiation
