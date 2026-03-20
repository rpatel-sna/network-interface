---
work_package_id: WP05
title: Integration Tests
lane: "doing"
dependencies: [WP04]
base_branch: 002-external-mariadb-device-source-WP04
base_commit: 801c2434b1bc10642e83d2c2a536b9063ebdfddb
created_at: '2026-03-20T15:41:17.819254+00:00'
subtasks:
- T020
- T021
- T022
phase: Phase 3 - Verification
assignee: ''
agent: ''
shell_pid: "39492"
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
- FR-007
- FR-008
- FR-009
- FR-010
---

# Work Package Prompt: WP05 – Integration Tests

## ⚠️ IMPORTANT: Review Feedback Status

Check `review_status` in frontmatter. If `has_feedback`, read the Review Feedback section below.

---

## Review Feedback

*[Empty — no feedback yet.]*

---

## Objectives & Success Criteria

- `pytest tests/integration/` passes with no encryption-related imports, fixtures, or test functions.
- `test_load_devices_from_external_db` covers: happy path, zero rows, row with missing `ip_address`, duplicate `ip_address` rows, unreachable DB.
- `test_full_run.py` uses the external DB fixture (not local `devices` table) as its device source.
- No references to `encryption`, `load_key`, `decrypt_password`, `fernet_key`, or `ENCRYPTION_KEY_FILE` remain in any test file.

## Context & Constraints

- **Workspace**: `.worktrees/002-external-mariadb-device-source-WP05/`
- **Depends on**: WP04 (full pipeline wired; all imports resolved)
- **Spec**: FR-001, FR-002, FR-007, FR-008, FR-009, FR-010, SC-001, SC-002, SC-003, SC-005
- For unreachable-DB tests: use `monkeypatch` to patch `mariadb.connect` — do not require a broken network.
- The `external_db_conn` fixture can point at the same local test MariaDB with a separate test schema — no second real DB server required.
- Read the existing test files first to understand existing fixture patterns before modifying.

**Run from workspace root:**
```bash
spec-kitty implement WP05 --base WP04
```

---

## Subtasks & Detailed Guidance

### Subtask T020 – Update `conftest.py` with external DB fixtures

**Purpose**: Replace encryption fixtures with external DB fixtures that the new test functions in T021 and T022 will use.

**File**: `tests/integration/conftest.py`

**Steps**:
1. Read the current `conftest.py` to understand existing fixtures.
2. Remove all Fernet/encryption-related fixtures (e.g., `fernet_key`, `encrypted_password`, `encryption_key_file`, any fixture that calls `load_key` or `Fernet`).
3. Add two new fixtures:

   **`ext_db_settings` fixture** — returns a `Settings`-like object (or override `settings` singleton) pointing at a test external DB schema:
   ```python
   @pytest.fixture
   def ext_db_settings(test_db_connection):
       """Settings pointing the external DB vars at the test MariaDB instance."""
       import os
       os.environ.setdefault("EXT_DB_HOST", "127.0.0.1")
       os.environ.setdefault("EXT_DB_PORT", "3306")
       os.environ.setdefault("EXT_DB_USER", os.environ["DB_USER"])
       os.environ.setdefault("EXT_DB_PASSWORD", os.environ["DB_PASSWORD"])
       os.environ.setdefault("EXT_DB_NAME", os.environ["DB_NAME"])
       os.environ.setdefault(
           "EXT_DB_QUERY",
           "SELECT id, hostname, ip_address, ssh_port, username, password, device_type FROM test_external_devices"
       )
       from network_inventory.config import Settings
       return Settings()
   ```

   **`setup_external_devices_table` fixture** — creates a `test_external_devices` table in the test DB and seeds test rows:
   ```python
   @pytest.fixture
   def setup_external_devices_table(test_db_connection):
       """Create and seed a test_external_devices table for external source tests."""
       conn = test_db_connection
       cursor = conn.cursor()
       cursor.execute("""
           CREATE TABLE IF NOT EXISTS test_external_devices (
               id INT AUTO_INCREMENT PRIMARY KEY,
               hostname VARCHAR(255),
               ip_address VARCHAR(45) NOT NULL,
               ssh_port INT DEFAULT 22,
               username VARCHAR(255) NOT NULL,
               password VARCHAR(255) NOT NULL,
               device_type VARCHAR(100) NOT NULL
           )
       """)
       cursor.execute("TRUNCATE TABLE test_external_devices")
       conn.commit()
       cursor.close()
       yield conn
       # Cleanup
       cursor = conn.cursor()
       cursor.execute("DROP TABLE IF EXISTS test_external_devices")
       conn.commit()
       cursor.close()
   ```

4. Keep all other existing fixtures (e.g., `test_db_connection`, `sample_device`, `sample_result`) unchanged.

---

### Subtask T021 – Add `test_load_devices_from_external_db` tests

**Purpose**: Cover all specified behaviours of `load_devices_from_external_db`: happy path, zero rows, missing required fields, duplicate IPs, and unreachable DB.

**File**: `tests/integration/test_db.py`

**Steps**:
1. Read the current `test_db.py` and remove any test functions that reference `load_enabled_devices`, encryption, or Fernet.
2. Add the following test functions (import `load_devices_from_external_db` from `network_inventory.db`):

   ```python
   def test_load_devices_from_external_db_happy_path(
       setup_external_devices_table, ext_db_settings
   ):
       """Query returns valid rows → Device list with correct fields."""
       conn = setup_external_devices_table
       cursor = conn.cursor()
       cursor.execute("""
           INSERT INTO test_external_devices
               (hostname, ip_address, ssh_port, username, password, device_type)
           VALUES ('sw1', '10.0.0.1', 22, 'admin', 'secret', 'cisco_ios')
       """)
       conn.commit()
       cursor.close()

       devices = load_devices_from_external_db(ext_db_settings)
       assert len(devices) == 1
       assert devices[0].ip_address == "10.0.0.1"
       assert devices[0].password == "secret"   # str, not bytes
       assert devices[0].enabled is True

   def test_load_devices_zero_rows(setup_external_devices_table, ext_db_settings):
       """Empty query result → empty list (no sys.exit)."""
       devices = load_devices_from_external_db(ext_db_settings)
       assert devices == []

   def test_load_devices_skips_missing_ip(
       setup_external_devices_table, ext_db_settings, caplog
   ):
       """Row missing ip_address → skipped with WARNING, valid rows still returned."""
       conn = setup_external_devices_table
       cursor = conn.cursor()
       # Row with NULL ip_address
       cursor.execute("""
           INSERT INTO test_external_devices
               (hostname, ip_address, ssh_port, username, password, device_type)
           VALUES ('bad', NULL, 22, 'admin', 'pass', 'cisco_ios')
       """)
       # Valid row
       cursor.execute("""
           INSERT INTO test_external_devices
               (hostname, ip_address, ssh_port, username, password, device_type)
           VALUES ('sw1', '10.0.0.1', 22, 'admin', 'pass', 'cisco_ios')
       """)
       conn.commit()
       cursor.close()

       with caplog.at_level(logging.WARNING, logger="network_inventory.db.external_source"):
           devices = load_devices_from_external_db(ext_db_settings)

       assert len(devices) == 1
       assert devices[0].ip_address == "10.0.0.1"
       assert any("skipped" in r.message.lower() for r in caplog.records)

   def test_load_devices_deduplicates_ip(
       setup_external_devices_table, ext_db_settings, caplog
   ):
       """Duplicate ip_address → second entry dropped with WARNING."""
       conn = setup_external_devices_table
       cursor = conn.cursor()
       for hostname in ("sw1", "sw1-duplicate"):
           cursor.execute("""
               INSERT INTO test_external_devices
                   (hostname, ip_address, ssh_port, username, password, device_type)
               VALUES (%s, '10.0.0.1', 22, 'admin', 'pass', 'cisco_ios')
           """, (hostname,))
       conn.commit()
       cursor.close()

       with caplog.at_level(logging.WARNING, logger="network_inventory.db.external_source"):
           devices = load_devices_from_external_db(ext_db_settings)

       assert len(devices) == 1
       assert any("duplicate" in r.message.lower() for r in caplog.records)

   def test_load_devices_unreachable_db(ext_db_settings, monkeypatch):
       """Unreachable external DB → sys.exit(1)."""
       import mariadb

       def mock_connect(**kwargs):
           raise mariadb.Error("Connection refused")

       monkeypatch.setattr(mariadb, "connect", mock_connect)

       with pytest.raises(SystemExit) as exc_info:
           load_devices_from_external_db(ext_db_settings)

       assert exc_info.value.code == 1
   ```

---

### Subtask T022 – Update `test_full_run.py` for external DB source

**Purpose**: The full-run test previously seeded the local `devices` table. Update it to seed the external devices fixture instead.

**File**: `tests/integration/test_full_run.py`

**Steps**:
1. Read the current `test_full_run.py`.
2. Remove any test setup that inserts into the local `devices` table.
3. Replace with setup that inserts into `test_external_devices` via the `setup_external_devices_table` fixture.
4. Remove any `ENCRYPTION_KEY_FILE` env var setup or `fernet_key` fixture usage.
5. Ensure `@pytest.mark.real_device` (if present) tests remain appropriately gated.

**Key assertion to add/verify**:
```python
def test_full_run_no_encryption_key_required(monkeypatch, ...):
    """Tool runs without ENCRYPTION_KEY_FILE set."""
    monkeypatch.delenv("ENCRYPTION_KEY_FILE", raising=False)
    # ... run main() or invoke via subprocess
    # Assert exit code 0
```

---

## Risks & Mitigations

- **`NULL` vs empty string in test DB**: MariaDB allows `NULL` for `ip_address` if the column is nullable — ensure the test table schema allows `NULL` for the missing-field test.
- **Test isolation**: Use `TRUNCATE TABLE test_external_devices` in the fixture setup (not just teardown) to clear data from previous test runs.
- **`settings` singleton is module-level**: Patching env vars after import won't update the singleton. Pass `ext_db_settings` directly to `load_devices_from_external_db()` rather than relying on the global `settings`.

## Review Guidance

Reviewer checks:
1. No imports of `encryption`, `load_key`, `decrypt_password`, `Fernet`, or `InvalidToken` in any test file.
2. Five new test functions present in `test_db.py` covering all listed scenarios.
3. `test_full_run.py` seeds `test_external_devices`, not the local `devices` table.
4. `pytest tests/integration/` passes (may require a live MariaDB; skip gracefully if unavailable).

## Activity Log

- 2026-03-20T14:42:47Z – system – lane=planned – Prompt created.
