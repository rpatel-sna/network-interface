---
work_package_id: WP02
title: External DB Source Module
lane: "done"
dependencies: [WP01]
base_branch: 002-external-mariadb-device-source-WP01
base_commit: 8609129f96a6b9bc1e3511b00d861285a304854c
created_at: '2026-03-20T15:01:39.613238+00:00'
subtasks:
- T006
- T007
- T008
- T009
- T010
phase: Phase 1 - Core Implementation
assignee: ''
agent: "claude-sonnet-4-6"
shell_pid: "42447"
review_status: "approved"
reviewed_by: "rpatel-hk"
history:
- timestamp: '2026-03-20T14:42:47Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-007
- FR-008
- FR-009
- FR-010
- FR-012
---

# Work Package Prompt: WP02 – External DB Source Module

## ⚠️ IMPORTANT: Review Feedback Status

Check `review_status` in frontmatter. If `has_feedback`, read the Review Feedback section below.

---

## Review Feedback

*[Empty — no feedback yet.]*

---

## Objectives & Success Criteria

- `network_inventory/db/external_source.py` exists with a `load_devices_from_external_db(settings)` public function.
- Given a reachable external DB and a valid query returning device rows → returns `list[Device]` with `password: str`.
- Given an unreachable DB (bad host/port) → logs an error and calls `sys.exit(1)` within 5 seconds.
- Given a query returning zero rows → returns `[]` (caller handles the zero-device case).
- Given a row missing `ip_address` → that row is skipped with a `WARNING`; others are returned.
- Given two rows with the same `ip_address` → one is kept, the other dropped with a `WARNING`.
- `db/__init__.py` exports `load_devices_from_external_db`.

## Context & Constraints

- **Workspace**: `.worktrees/002-external-mariadb-device-source-WP02/`
- **Depends on**: WP01 (`Settings` has `ext_db_*` fields; `Device.password: str`)
- **Spec**: FR-001, FR-002, FR-003, FR-004, FR-007, FR-008, FR-009, FR-010
- **Data model**: `kitty-specs/002-external-mariadb-device-source/data-model.md`
- Use `mariadb.connect()` directly — no pool needed (single query per run).
- Connection timeout: **exactly 5 seconds** (`connect_timeout=5`).
- Column mapping uses `cursor.description` (name-based) — do NOT rely on positional column order.
- Synthesise `id` via `enumerate()` if the external query doesn't include an `id` column.

**Run from workspace root:**
```bash
spec-kitty implement WP02 --base WP01
```

---

## Subtasks & Detailed Guidance

### Subtask T006 – Create `db/external_source.py` with function signature

**Purpose**: Establish the module file and public function signature that all other subtasks fill in.

**File**: `network_inventory/db/external_source.py` (new file)

**Steps**:
1. Create the file with imports and the public function skeleton:
   ```python
   """External MariaDB device source — fetches device list for SSH polling."""
   from __future__ import annotations

   import logging
   import sys

   import mariadb

   from network_inventory.config import Settings
   from network_inventory.models.device import Device

   logger = logging.getLogger(__name__)


   def load_devices_from_external_db(app_settings: Settings) -> list[Device]:
       """Connect to the external MariaDB, run the configured query, validate
       and deduplicate rows, and return a list of Device instances.

       Exits with sys.exit(1) on connection failure (timeout: 5s) or query error.
       Skips rows missing required fields (ip_address, device_type, username,
       password) with a WARNING log per skipped row.
       Deduplicates by ip_address; logs WARNING for each dropped duplicate.

       Args:
           app_settings: Loaded Settings instance with ext_db_* fields.

       Returns:
           List of Device instances (may be empty if query returns zero rows).
       """
       ...  # Implementation added in T007–T009
   ```

---

### Subtask T007 – Implement external DB connection and query execution

**Purpose**: Connect to the external MariaDB with a 5-second timeout, run the user query, and retrieve all rows. Exit with code 1 on any connection or query error.

**File**: `network_inventory/db/external_source.py`

**Steps**:
1. Replace the `...` stub with the connection and query block:
   ```python
   conn: mariadb.Connection | None = None
   try:
       conn = mariadb.connect(
           host=app_settings.ext_db_host,
           port=app_settings.ext_db_port,
           user=app_settings.ext_db_user,
           password=app_settings.ext_db_password,
           database=app_settings.ext_db_name,
           connect_timeout=5,
       )
   except mariadb.Error as exc:
       logger.error(
           "Failed to connect to external device source DB at %s:%s — %s",
           app_settings.ext_db_host,
           app_settings.ext_db_port,
           exc,
       )
       sys.exit(1)

   try:
       cursor = conn.cursor()
       cursor.execute(app_settings.ext_db_query)
       rows = cursor.fetchall()
       # Map column names from cursor.description for name-based access
       col_names = [desc[0].lower() for desc in cursor.description]
       cursor.close()
   except mariadb.Error as exc:
       logger.error("External device query failed: %s", exc)
       conn.close()
       sys.exit(1)
   finally:
       if conn:
           conn.close()

   logger.info(
       "External DB query returned %d row(s)", len(rows)
   )
   ```

**Notes**:
- `cursor.description` is a sequence of 7-item tuples; index `[0]` is the column name.
- Always close the connection whether the query succeeds or fails.
- The query could theoretically return 0 rows — that is not an error here; return `[]`.

---

### Subtask T008 – Implement row validation

**Purpose**: Validate each row from the external query. Required fields: `ip_address`, `device_type`, `username`, `password`. Optional: `hostname` (defaults to `ip_address`), `ssh_port` (defaults to `22`), `id` (defaults to `enumerate` index).

**File**: `network_inventory/db/external_source.py`

**Steps**:
1. After the query block, add the validation loop:
   ```python
   REQUIRED_COLS = ("ip_address", "device_type", "username", "password")
   validated: list[Device] = []

   for idx, row in enumerate(rows):
       row_dict = dict(zip(col_names, row))

       # Check required fields
       missing = [c for c in REQUIRED_COLS if not row_dict.get(c)]
       if missing:
           logger.warning(
               "External DB row %d skipped — missing required field(s): %s. Row: %s",
               idx,
               ", ".join(missing),
               {k: row_dict.get(k) for k in REQUIRED_COLS},
           )
           continue

       device = Device(
           id=int(row_dict.get("id", idx)),
           hostname=str(row_dict.get("hostname") or row_dict["ip_address"]),
           ip_address=str(row_dict["ip_address"]),
           ssh_port=int(row_dict.get("ssh_port") or 22),
           username=str(row_dict["username"]),
           password=str(row_dict["password"]),
           device_type=str(row_dict["device_type"]),
           enabled=True,
       )
       validated.append(device)

   logger.info("%d valid device row(s) after validation", len(validated))
   ```

**Notes**:
- Use `row_dict.get(c)` (falsy check) rather than `is None` — an empty string `""` is also invalid.
- `hostname` defaults to `ip_address` if absent or `None`.
- `ssh_port` defaults to `22` if absent or `None`.

---

### Subtask T009 – Implement deduplication by `ip_address`

**Purpose**: If the external query returns two rows with the same IP (schema issue or join artifact), only the first is kept. FR-010.

**File**: `network_inventory/db/external_source.py`

**Steps**:
1. After the validation loop, add the deduplication block:
   ```python
   seen_ips: set[str] = set()
   deduped: list[Device] = []

   for device in validated:
       if device.ip_address in seen_ips:
           logger.warning(
               "Duplicate ip_address '%s' (hostname=%r) dropped — keeping first occurrence",
               device.ip_address,
               device.hostname,
           )
           continue
       seen_ips.add(device.ip_address)
       deduped.append(device)

   logger.info(
       "Returning %d device(s) after deduplication (dropped %d duplicate(s))",
       len(deduped),
       len(validated) - len(deduped),
   )
   return deduped
   ```

---

### Subtask T010 – Export `load_devices_from_external_db` from `db/__init__.py`

**Purpose**: Keep the public API of the `db` package consistent — callers import from `network_inventory.db`.

**File**: `network_inventory/db/__init__.py`

**Steps**:
1. Read the current `__init__.py` and add the new import alongside existing exports:
   ```python
   from network_inventory.db.external_source import load_devices_from_external_db

   __all__ = [
       "get_connection",
       "get_pool",
       "load_devices_from_external_db",
       "upsert_inventory_record",
   ]
   ```
   (Remove `load_enabled_devices` if it was already exported — but that is WP03's responsibility; don't touch it here to avoid conflict.)

**Notes**:
- `load_enabled_devices` may still be in `__init__.py` at this point (WP03 removes it). Do not remove it in this WP — focus only on adding `load_devices_from_external_db`.

---

## Risks & Mitigations

- **`cursor.description` column name casing varies** — use `.lower()` on all column names for safe case-insensitive matching.
- **External query returns non-standard types** (e.g. `Decimal` for port) — wrap with `int()` and `str()` when constructing `Device`.
- **`id` field absent from external schema** — use `enumerate()` index as fallback; `id` is used as `device_id` in `CollectionResult` writes.

## Review Guidance

Reviewer checks:
1. `external_source.py` imports: `mariadb`, `Settings`, `Device`, `sys`, `logging`.
2. Connection uses `connect_timeout=5`.
3. Both `mariadb.Error` paths (connect + query) log error and `sys.exit(1)`.
4. Column mapping is name-based via `cursor.description`, not positional.
5. Validation skips rows with missing/empty required fields with a `WARNING`.
6. Deduplication by `ip_address` with `WARNING` per dropped entry.
7. `db/__init__.py` exports `load_devices_from_external_db`.

## Activity Log

- 2026-03-20T14:42:47Z – system – lane=planned – Prompt created.
- 2026-03-20T15:01:40Z – claude-sonnet-4-6 – shell_pid=30738 – lane=doing – Assigned agent via workflow command
- 2026-03-20T15:04:47Z – claude-sonnet-4-6 – shell_pid=30738 – lane=for_review – Ready for review: db/external_source.py with connection, validation, deduplication; db/__init__.py updated
- 2026-03-20T15:53:20Z – claude-sonnet-4-6 – shell_pid=42447 – lane=doing – Started review via workflow command
- 2026-03-20T15:54:00Z – claude-sonnet-4-6 – shell_pid=42447 – lane=done – Review passed: external_source.py correct — connect_timeout=5, name-based column mapping, falsy validation covers empty strings, deduplication with WARNING, id fallback to enumerate index; db/__init__.py minimal change leaving load_enabled_devices for WP03
