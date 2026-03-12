---
work_package_id: WP03
title: Database Layer
lane: planned
dependencies:
- WP01
subtasks:
- T008
- T009
- T010
phase: Phase 0 - Foundation
assignee: ''
agent: ''
shell_pid: ''
review_status: ''
reviewed_by: ''
history:
- timestamp: '2026-03-12T10:45:33Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-001
- FR-008
- FR-013
---

# Work Package Prompt: WP03 – Database Layer

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status` above. If `has_feedback`, read the Review Feedback section first.

---

## Review Feedback

*[Empty initially.]*

---

## Objectives & Success Criteria

- MariaDB connection pool initializes at startup; any `mariadb.Error` causes immediate `sys.exit(1)` with a descriptive message.
- `load_enabled_devices()` returns a `list[Device]` containing only rows where `enabled = 1`.
- `upsert_inventory_record()` performs a correct `INSERT ... ON DUPLICATE KEY UPDATE` keyed by `device_id`; calling it twice for the same device does not create duplicate rows.
- `last_success` is updated only on `status = 'success'`; on failure/timeout, the previous `last_success` value is preserved.

**Done when**:
- With a live MariaDB and correct credentials, `load_enabled_devices()` returns device rows.
- With wrong DB host, importing the module (or calling pool init) triggers `sys.exit(1)`.
- Two upserts for the same `device_id` result in one row in `device_inventory`.

## Context & Constraints

- **Schema**: `kitty-specs/001-network-device-inventory-cli/contracts/schema.sql`
- **Data model**: `kitty-specs/001-network-device-inventory-cli/data-model.md`
- **Spec**: FR-001, FR-008, FR-013
- **Research**: `kitty-specs/001-network-device-inventory-cli/research.md` — `mariadb` connector chosen over `mysql-connector-python`
- **Implement with**: `spec-kitty implement WP03 --base WP01`
- DB credentials come from `settings` (WP01). `Device` + `CollectionResult` dataclasses from WP02.
- Minimal DB privileges: `SELECT` on `devices`, `INSERT/UPDATE` on `device_inventory`.
- `devices.password` column is `VARBINARY(512)` — must be fetched as `bytes`.

## Subtasks & Detailed Guidance

### Subtask T008 – Implement `network_inventory/db/connection.py`

**Purpose**: Provide a MariaDB connection (or pool) that the query layer uses, and enforce fail-fast behaviour on startup as required by FR-013.

**Steps**:

1. Create `network_inventory/db/connection.py`:

```python
"""MariaDB connection management with fail-fast startup validation."""
from __future__ import annotations

import logging
import sys

import mariadb

from network_inventory.config import settings

logger = logging.getLogger(__name__)

_pool: mariadb.ConnectionPool | None = None


def get_pool() -> mariadb.ConnectionPool:
    """Return the application-wide connection pool, creating it on first call.

    Exits the process with code 1 if the database is unreachable.
    """
    global _pool
    if _pool is None:
        _pool = _create_pool()
    return _pool


def _create_pool() -> mariadb.ConnectionPool:
    """Create and return a new MariaDB connection pool."""
    try:
        pool = mariadb.ConnectionPool(
            pool_name="inventory_pool",
            pool_size=settings.max_threads + 2,   # +2 headroom for main thread
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            connect_timeout=10,
        )
        logger.info("MariaDB connection pool established (host=%s, db=%s)", settings.db_host, settings.db_name)
        return pool
    except mariadb.Error as exc:
        logger.error("Failed to connect to database: %s", exc)
        sys.exit(1)


def get_connection() -> mariadb.Connection:
    """Acquire a connection from the pool."""
    return get_pool().get_connection()
```

**Notes**:
- Pool size = `max_threads + 2` — each worker thread needs one connection; +2 for the main thread DB writes.
- `sys.exit(1)` is the correct behaviour per FR-013; do not raise here.
- Connection must NOT be used as a module-level singleton — acquire per operation and release.
- The `password` in `mariadb.ConnectionPool()` is the **DB admin password** from `settings.db_password` (not a device password — do not confuse).

**Files**:
- `network_inventory/db/connection.py`

**Validation**:
- [ ] With correct credentials: `get_pool()` returns a pool object without error.
- [ ] With wrong `DB_HOST`: process exits with code 1 and logs an error message.
- [ ] Pool is a singleton — `get_pool() is get_pool()` returns `True`.

---

### Subtask T009 – Implement `network_inventory/db/queries.py`

**Purpose**: All SQL read and write operations in one place — loading enabled devices and upserting poll results.

**Steps**:

1. Create `network_inventory/db/queries.py`:

```python
"""SQL queries: load enabled devices + upsert inventory results."""
from __future__ import annotations

import logging
from datetime import datetime

import mariadb

from network_inventory.models.device import CollectionResult, Device

logger = logging.getLogger(__name__)

_LOAD_ENABLED_DEVICES_SQL = """
    SELECT id, hostname, ip_address, ssh_port, username, password, device_type, enabled
    FROM devices
    WHERE enabled = 1
"""

_UPSERT_INVENTORY_SQL = """
    INSERT INTO device_inventory
        (device_id, serial_number, firmware_version, last_success, last_attempt, status, error_message)
    VALUES
        (%(device_id)s, %(serial_number)s, %(firmware_version)s, %(last_success)s,
         %(last_attempt)s, %(status)s, %(error_message)s)
    ON DUPLICATE KEY UPDATE
        serial_number    = VALUES(serial_number),
        firmware_version = VALUES(firmware_version),
        last_success     = IF(VALUES(status) = 'success', VALUES(last_success), last_success),
        last_attempt     = VALUES(last_attempt),
        status           = VALUES(status),
        error_message    = VALUES(error_message)
"""


def load_enabled_devices(conn: mariadb.Connection) -> list[Device]:
    """Fetch all enabled devices from the database.

    Args:
        conn: Active MariaDB connection.

    Returns:
        List of Device dataclass instances (may be empty).
    """
    cursor = conn.cursor()
    cursor.execute(_LOAD_ENABLED_DEVICES_SQL)
    rows = cursor.fetchall()
    cursor.close()

    devices = []
    for row in rows:
        id_, hostname, ip_address, ssh_port, username, password, device_type, enabled = row
        devices.append(Device(
            id=id_,
            hostname=hostname,
            ip_address=ip_address,
            ssh_port=ssh_port,
            username=username,
            password=bytes(password),   # VARBINARY comes back as bytearray; coerce to bytes
            device_type=device_type,
            enabled=bool(enabled),
        ))

    logger.info("Loaded %d enabled device(s) from database", len(devices))
    return devices


def upsert_inventory_record(conn: mariadb.Connection, result: CollectionResult) -> None:
    """Insert or update a device_inventory row for the given poll result.

    Args:
        conn: Active MariaDB connection.
        result: CollectionResult from a device poll.
    """
    params = {
        "device_id": result.device_id,
        "serial_number": result.serial_number,
        "firmware_version": result.firmware_version,
        "last_success": result.succeeded_at,
        "last_attempt": result.attempted_at,
        "status": result.status,
        "error_message": result.error_message,
    }

    cursor = conn.cursor()
    cursor.execute(_UPSERT_INVENTORY_SQL, params)
    conn.commit()
    cursor.close()

    logger.debug("Upserted device_inventory for device_id=%d status=%s", result.device_id, result.status)
```

**Key SQL behaviour**:
- `ON DUPLICATE KEY UPDATE` is keyed by the `UNIQUE KEY uq_device_inventory_device_id (device_id)`.
- `last_success = IF(VALUES(status) = 'success', VALUES(last_success), last_success)` — preserves existing `last_success` on failure/timeout.
- `serial_number` and `firmware_version` may be `NULL` (partial data allowed per edge cases in spec).

**Files**:
- `network_inventory/db/queries.py`

**Validation**:
- [ ] Insert a test device, call `upsert_inventory_record()` with `status='success'` → row exists with `last_success` set.
- [ ] Call again with `status='failed'` → `last_success` unchanged, `status` updated to `'failed'`.
- [ ] `load_enabled_devices()` returns only rows with `enabled = 1`.
- [ ] Device with `enabled = 0` does NOT appear in results.

---

### Subtask T010 – Implement `network_inventory/db/__init__.py`

**Purpose**: Expose a clean public API from the `db` package so importers don't need to know internal module layout.

**Steps**:

1. Create `network_inventory/db/__init__.py`:

```python
"""Database layer public API."""
from .connection import get_connection, get_pool
from .queries import load_enabled_devices, upsert_inventory_record

__all__ = [
    "get_connection",
    "get_pool",
    "load_enabled_devices",
    "upsert_inventory_record",
]
```

**Files**:
- `network_inventory/db/__init__.py`

**Validation**:
- [ ] `from network_inventory.db import get_connection, load_enabled_devices, upsert_inventory_record` succeeds.

---

## Risks & Mitigations

- **Thread safety of connections**: Each worker thread must use its own `get_connection()` call. Sharing a single connection across threads causes cursor race conditions. The main orchestrator (WP07) acquires a connection per upsert call in the main thread (not worker threads).
- **`ON DUPLICATE KEY UPDATE` + `last_success` logic**: The `IF(VALUES(status) = 'success', ...)` construct is MariaDB-specific SQL — test this on the actual MariaDB version (10.6+).
- **`VARBINARY` → `bytes` coercion**: MariaDB connector returns `bytearray` for `VARBINARY` columns; wrap with `bytes()` when constructing `Device`.
- **Pool exhaustion**: Pool size = `max_threads + 2`; if the main thread holds connections while all workers are active, pool may block. Acquire + release within each DB call to minimise hold time.

## Review Guidance

- Verify the `ON DUPLICATE KEY UPDATE` clause preserves `last_success` correctly — run a two-upsert integration test.
- Check `VARBINARY` password field is returned as `bytes` (not `str`).
- Confirm `sys.exit(1)` is called on `mariadb.Error` at pool creation (not just logged).
- Verify no plaintext device password appears anywhere in this file (it should only handle DB admin credentials and encrypted device password bytes).

## Activity Log

> **CRITICAL**: Append new entries at the END. Never prepend.

- 2026-03-12T10:45:33Z – system – lane=planned – Prompt created.
