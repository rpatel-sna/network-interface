---
work_package_id: WP08
title: Integration Tests
lane: "doing"
dependencies:
- WP07
base_branch: 001-network-device-inventory-cli-WP07
base_commit: cf5fe12eacba8af2cfca573a1d165bd6860e4799
created_at: '2026-03-13T16:41:31.552420+00:00'
subtasks:
- T024
- T025
- T026
phase: Phase 2 - Integration
assignee: ''
agent: ''
shell_pid: "82440"
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
- FR-002
- FR-005
- FR-006
- FR-007
- FR-008
---

# Work Package Prompt: WP08 – Integration Tests

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status` above. If `has_feedback`, read the Review Feedback section first.

---

## Review Feedback

*[Empty initially.]*

---

## Objectives & Success Criteria

- `pytest tests/integration/ -v` passes against a test MariaDB with seeded data.
- Tests that require real device SSH access are skipped automatically in CI via `@pytest.mark.real_device` + `pytest -m "not real_device"`.
- US1, US2, and US3 acceptance scenarios from `spec.md` are exercised and pass.
- DB connection failure at startup causes `sys.exit(1)` — validated by subprocess test.

**Done when**:
- All non-`real_device` tests pass in CI with a test MariaDB available.
- Real-device tests are clearly annotated and skippable.
- Test fixtures clean up `device_inventory` between test cases.

## Context & Constraints

- **Spec**: `kitty-specs/001-network-device-inventory-cli/spec.md` — US1, US2, US3 acceptance scenarios; all edge cases; FR-001, FR-002, FR-005, FR-006, FR-007, FR-008
- **Plan**: `kitty-specs/001-network-device-inventory-cli/plan.md` — pytest, integration tests only, no mocked unit tests in v1
- **Quickstart**: `kitty-specs/001-network-device-inventory-cli/quickstart.md` — test invocation: `pytest tests/integration/ -v`
- **Implement with**: `spec-kitty implement WP08 --base WP07`
- Tests load config from `.env.test` or `TEST_` prefixed env vars (e.g. `TEST_DB_HOST`) — never production credentials.
- `pytest.ini` or `pyproject.toml` [tool.pytest.ini_options] should register the `real_device` mark to suppress unknown-mark warnings.

## Subtasks & Detailed Guidance

### Subtask T024 – `tests/integration/test_db.py`

**Purpose**: Validate the database layer: upsert correctness, connection failure handling, and minimal-privilege constraints.

**Steps**:

1. Create `tests/integration/conftest.py` with shared fixtures:

```python
"""Shared fixtures for integration tests."""
import os
import pytest
import mariadb
from cryptography.fernet import Fernet

@pytest.fixture(scope="session")
def test_db_conn():
    """Provide a MariaDB connection to the test database."""
    conn = mariadb.connect(
        host=os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("TEST_DB_PORT", "3306")),
        user=os.environ.get("TEST_DB_USER", "root"),
        password=os.environ.get("TEST_DB_PASSWORD", ""),
        database=os.environ.get("TEST_DB_NAME", "test_inventory"),
    )
    yield conn
    conn.close()

@pytest.fixture
def fernet_key() -> bytes:
    """Generate a fresh Fernet key for each test."""
    return Fernet.generate_key()

@pytest.fixture(autouse=True)
def clean_device_inventory(test_db_conn):
    """Truncate device_inventory before each test case."""
    yield
    cur = test_db_conn.cursor()
    cur.execute("DELETE FROM device_inventory")
    test_db_conn.commit()
    cur.close()
```

2. Create `tests/integration/test_db.py`:

```python
"""Integration tests for the database layer."""
import sys
import subprocess
import os
import pytest
from datetime import datetime

from network_inventory.db.queries import load_enabled_devices, upsert_inventory_record
from network_inventory.models.device import CollectionResult


class TestUpsertCorrectness:
    def test_first_upsert_creates_row(self, test_db_conn):
        """First upsert for a device_id creates a new row."""
        result = CollectionResult(
            device_id=1,  # Must exist in test devices table
            status='success',
            attempted_at=datetime.utcnow(),
            serial_number='SN001',
            firmware_version='v1.0',
            succeeded_at=datetime.utcnow(),
        )
        upsert_inventory_record(test_db_conn, result)
        cursor = test_db_conn.cursor()
        cursor.execute("SELECT status, serial_number FROM device_inventory WHERE device_id = 1")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 'success'
        assert row[1] == 'SN001'

    def test_second_upsert_overwrites_row(self, test_db_conn):
        """Second upsert for same device_id overwrites the existing row."""
        success_result = CollectionResult(
            device_id=1, status='success', attempted_at=datetime.utcnow(),
            serial_number='SN001', succeeded_at=datetime.utcnow(),
        )
        failed_result = CollectionResult(
            device_id=1, status='failed', attempted_at=datetime.utcnow(),
            error_message='auth failed',
        )
        upsert_inventory_record(test_db_conn, success_result)
        upsert_inventory_record(test_db_conn, failed_result)

        cursor = test_db_conn.cursor()
        cursor.execute("SELECT status, serial_number, last_success FROM device_inventory WHERE device_id = 1")
        row = cursor.fetchone()
        assert row[0] == 'failed'               # Status updated
        assert row[1] == 'SN001'               # Serial preserved from success
        assert row[2] is not None              # last_success preserved from previous success

    def test_last_success_preserved_on_failure(self, test_db_conn):
        """last_success is not overwritten when status is 'failed' or 'timeout'."""
        success = CollectionResult(
            device_id=1, status='success', attempted_at=datetime.utcnow(),
            succeeded_at=datetime.utcnow(),
        )
        upsert_inventory_record(test_db_conn, success)

        timeout = CollectionResult(
            device_id=1, status='timeout', attempted_at=datetime.utcnow(),
            error_message='timed out',
        )
        upsert_inventory_record(test_db_conn, timeout)

        cursor = test_db_conn.cursor()
        cursor.execute("SELECT last_success, status FROM device_inventory WHERE device_id = 1")
        row = cursor.fetchone()
        assert row[1] == 'timeout'
        assert row[0] is not None  # last_success unchanged

    def test_partial_data_written(self, test_db_conn):
        """Serial null but firmware present is written correctly (partial data)."""
        result = CollectionResult(
            device_id=1, status='failed', attempted_at=datetime.utcnow(),
            serial_number=None, firmware_version='v2.0',
        )
        upsert_inventory_record(test_db_conn, result)
        cursor = test_db_conn.cursor()
        cursor.execute("SELECT serial_number, firmware_version FROM device_inventory WHERE device_id = 1")
        row = cursor.fetchone()
        assert row[0] is None
        assert row[1] == 'v2.0'


class TestConnectionFailure:
    def test_bad_db_host_exits_nonzero(self):
        """DB connection failure at startup causes sys.exit(1)."""
        env = {**os.environ, "DB_HOST": "192.0.2.1", "DB_PORT": "3306"}  # Non-routable IP
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=env,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode != 0, "Expected non-zero exit code on DB failure"


class TestLoadEnabledDevices:
    def test_disabled_device_not_loaded(self, test_db_conn):
        """Devices with enabled=0 are not returned by load_enabled_devices()."""
        devices = load_enabled_devices(test_db_conn)
        for device in devices:
            assert device.enabled is True, f"Disabled device {device.id} should not be loaded"
```

**Test DB setup note**: The test DB must have a `devices` table with at least one row (`id=1`, `enabled=1`) pre-seeded by a fixture or migration. Add a `pytest.fixture` that inserts a test device and deletes it after the session.

**Files**:
- `tests/integration/conftest.py`
- `tests/integration/test_db.py`

**Parallel?**: Yes — T024, T025, T026 can be implemented simultaneously.

**Validation**:
- [ ] All `TestUpsertCorrectness` tests pass with a live test DB.
- [ ] `TestConnectionFailure` verifies exit code is non-zero (requires `DB_HOST` to be unreachable — use a non-routable IP or stop MariaDB temporarily).
- [ ] `TestLoadEnabledDevices` confirms disabled device exclusion.

---

### Subtask T025 – `tests/integration/test_full_run.py`

**Purpose**: End-to-end integration tests exercising the full `main()` function against a test DB — validating US1 (full run), US2 (failure handling), and US3 (disabled device exclusion).

**Steps**:

1. Create `tests/integration/test_full_run.py`:

```python
"""End-to-end integration tests for the full inventory run.

These tests invoke main() directly or as a subprocess against a test MariaDB.
Real device SSH is NOT required — these tests use pre-seeded DB state and
validate the orchestration logic, not collector output.
"""
import os
import sys
import subprocess
import pytest

from network_inventory.db.queries import load_enabled_devices


@pytest.fixture
def test_env(tmp_path, fernet_key):
    """Set up a minimal test environment with a valid Fernet key file."""
    key_file = tmp_path / "test.key"
    key_file.write_bytes(fernet_key)
    env = {
        **os.environ,
        "ENCRYPTION_KEY_FILE": str(key_file),
        # Inherit TEST_DB_* from environment
        "DB_HOST": os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        "DB_PORT": os.environ.get("TEST_DB_PORT", "3306"),
        "DB_USER": os.environ.get("TEST_DB_USER", "root"),
        "DB_PASSWORD": os.environ.get("TEST_DB_PASSWORD", ""),
        "DB_NAME": os.environ.get("TEST_DB_NAME", "test_inventory"),
        "MAX_THREADS": "2",
        "SSH_TIMEOUT": "5",
    }
    return env


class TestFullRun:
    def test_summary_printed_on_completion(self, test_env, test_db_conn):
        """US1: Run completes and prints a summary with correct labels."""
        # Requires at least one enabled device in the test DB
        # (device may fail SSH — we just check the summary is printed and exit is 0 or >0)
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=test_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "Inventory run complete." in result.stdout
        assert "Total polled" in result.stdout
        assert "Success" in result.stdout
        assert "Failed" in result.stdout
        assert "Timeout" in result.stdout

    def test_no_enabled_devices_exits_cleanly(self, test_env, test_db_conn):
        """Edge case: zero enabled devices → clean exit with message."""
        # Temporarily disable all devices
        cur = test_db_conn.cursor()
        cur.execute("UPDATE devices SET enabled = 0")
        test_db_conn.commit()

        try:
            result = subprocess.run(
                [sys.executable, "network_inventory/main.py"],
                env=test_env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0
            assert "No enabled devices found" in result.stdout
        finally:
            cur.execute("UPDATE devices SET enabled = 1")
            test_db_conn.commit()
            cur.close()

    def test_disabled_device_has_no_inventory_row(self, test_env, test_db_conn):
        """US3: Disabled device (enabled=0) does not get a device_inventory row after a run."""
        # Disable device with id=2 (must exist in test DB with enabled=0)
        cur = test_db_conn.cursor()
        cur.execute("DELETE FROM device_inventory WHERE device_id = 2")
        test_db_conn.commit()
        cur.close()

        subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=test_env,
            capture_output=True,
            timeout=60,
        )

        cur = test_db_conn.cursor()
        cur.execute("SELECT id FROM device_inventory WHERE device_id = 2")
        row = cur.fetchone()
        cur.close()
        assert row is None, "Disabled device should have no inventory row"

    def test_missing_key_file_exits_nonzero(self, test_env):
        """Startup validation: missing key file causes exit(1)."""
        test_env["ENCRYPTION_KEY_FILE"] = "/nonexistent/path/key.file"
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=test_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0

    def test_missing_required_env_var_exits_nonzero(self, test_env):
        """Startup validation: missing required env var causes exit(1)."""
        del test_env["DB_HOST"]
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=test_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0
```

**Files**:
- `tests/integration/test_full_run.py`

**Parallel?**: Yes — implement simultaneously with T024 and T026.

**Validation**:
- [ ] Summary test passes (device may fail SSH — we test structure, not SSH success).
- [ ] Zero-devices test passes.
- [ ] Disabled device test confirms no row created.
- [ ] Startup validation tests confirm exit code != 0 on bad config.

---

### Subtask T026 – `tests/integration/test_collectors.py`

**Purpose**: Per-collector tests that validate parsing logic and, for those with real hardware access, SSH connectivity and data collection.

**Steps**:

1. Create `tests/integration/test_collectors.py`:

```python
"""Per-collector integration tests.

Parsing tests: no real device required — validate regex against sample output.
Real-device tests: require live hardware + @pytest.mark.real_device annotation.
Run without real devices: pytest -m "not real_device" tests/integration/test_collectors.py
"""
import re
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from network_inventory.collectors.cisco_ios import CiscoIOSCollector, _SERIAL_PATTERN, _FIRMWARE_PATTERN
from network_inventory.collectors.cisco_nxos import CiscoNXOSCollector
from network_inventory.collectors.hp_procurve import HPProCurveCollector
from network_inventory.collectors.aruba import ArubaCollector
from network_inventory.collectors.ruckus_icx import RuckusICXCollector
from network_inventory.collectors.ruckus_wireless import RuckusWirelessCollector
from network_inventory.models.device import Device


# ---------------------------------------------------------------------------
# Sample device factory
# ---------------------------------------------------------------------------

def make_device(device_type: str) -> Device:
    return Device(
        id=99,
        hostname="test-device",
        ip_address="192.0.2.1",
        ssh_port=22,
        username="admin",
        password=b"encrypted_placeholder",
        device_type=device_type,
        enabled=True,
    )


FERNET_KEY = b"placeholder"  # Not used in parsing tests (no real SSH)


# ---------------------------------------------------------------------------
# Cisco IOS parsing tests (no real device)
# ---------------------------------------------------------------------------

class TestCiscoIOSParsing:
    INVENTORY_OUTPUT = """
NAME: "Chassis", DESCR: "Cisco 2911 Chassis"
PID: CISCO2911/K9   , VID: V06  , SN: FGL1234ABCD
NAME: "module 0", DESCR: "C2911 Mother board Port adapter, 3 ports"
PID: CISCO2911/K9   , VID: V06  , SN: FGL5678XYZ
"""
    VERSION_OUTPUT = "Cisco IOS Software, Version 15.7(3)M8, RELEASE SOFTWARE (fc2)"

    def test_serial_extraction(self):
        match = _SERIAL_PATTERN.search(self.INVENTORY_OUTPUT)
        assert match and match.group(1) == "FGL1234ABCD"

    def test_firmware_extraction(self):
        match = _FIRMWARE_PATTERN.search(self.VERSION_OUTPUT)
        assert match and match.group(1) == "15.7(3)M8"

    def test_no_match_returns_none(self):
        from network_inventory.collectors.cisco_ios import _SERIAL_PATTERN as SP
        assert SP.search("no serial here") is None


class TestCiscoNXOSParsing:
    def test_serial_extraction(self):
        from network_inventory.collectors.cisco_nxos import _SERIAL_PATTERN
        output = "  serialnum : TME123456789"
        m = _SERIAL_PATTERN.search(output)
        assert m and m.group(1) == "TME123456789"

    def test_firmware_extraction(self):
        from network_inventory.collectors.cisco_nxos import _FIRMWARE_PATTERN
        output = "  NXOS: version 9.3(10)"
        m = _FIRMWARE_PATTERN.search(output)
        assert m and m.group(1) == "9.3(10)"


class TestHPProCurveParsing:
    def test_serial_extraction(self):
        from network_inventory.collectors.hp_procurve import _SERIAL_PATTERN
        output = "  Serial Number      : SG12345678"
        m = _SERIAL_PATTERN.search(output)
        assert m and m.group(1) == "SG12345678"

    def test_firmware_extraction(self):
        from network_inventory.collectors.hp_procurve import _FIRMWARE_PATTERN
        output = "  Software revision  : WB.16.10.0009"
        m = _FIRMWARE_PATTERN.search(output)
        assert m and m.group(1) == "WB.16.10.0009"


class TestRuckusICXParsing:
    def test_serial_extraction(self):
        from network_inventory.collectors.ruckus_icx import _SERIAL_PATTERN
        output = "  Serial  #: BCR3312L00T"
        m = _SERIAL_PATTERN.search(output)
        assert m and m.group(1) == "BCR3312L00T"

    def test_firmware_extraction(self):
        from network_inventory.collectors.ruckus_icx import _FIRMWARE_PATTERN
        output = "  SW: Version 08.0.92T213"
        m = _FIRMWARE_PATTERN.search(output)
        assert m and m.group(1) == "08.0.92T213"


# ---------------------------------------------------------------------------
# Registry coverage test
# ---------------------------------------------------------------------------

class TestCollectorRegistry:
    def test_all_device_types_registered(self):
        from network_inventory.collectors import COLLECTOR_REGISTRY
        expected = {
            'cisco_ios', 'cisco_xe', 'cisco_nxos',
            'hp_procurve', 'aruba_procurve',
            'ruckus_fastiron', 'ruckus_wireless',
        }
        missing = expected - set(COLLECTOR_REGISTRY.keys())
        assert not missing, f"Missing registry entries: {missing}"

    def test_unknown_type_returns_none(self):
        from network_inventory.collectors import get_collector
        assert get_collector('does_not_exist') is None


# ---------------------------------------------------------------------------
# Real-device tests (skipped unless @pytest.mark.real_device)
# ---------------------------------------------------------------------------

@pytest.mark.real_device
class TestRealDeviceCiscoIOS:
    """Requires a live Cisco IOS device reachable from the test host.
    Configure via TEST_CISCO_IOS_* environment variables.
    """

    def test_collect_returns_success(self, real_cisco_ios_device):
        """collect() returns status='success' with non-None serial and firmware."""
        from network_inventory.utils.encryption import load_key
        from network_inventory.config import settings
        key = load_key(settings.encryption_key_file)
        collector = CiscoIOSCollector(device=real_cisco_ios_device, key=key)
        result = collector.collect()
        assert result.status == 'success'
        assert result.serial_number is not None
        assert result.firmware_version is not None


@pytest.mark.real_device
class TestRealDeviceRuckusWireless:
    """⚠️  Ruckus wireless device_type is unconfirmed (see research.md open item).
    This test validates the fallback device_type logic against real hardware.
    """

    def test_collect_does_not_raise(self, real_ruckus_wireless_device):
        """collect() returns a CollectionResult (success or failed) — never raises."""
        from network_inventory.utils.encryption import load_key
        from network_inventory.config import settings
        key = load_key(settings.encryption_key_file)
        collector = RuckusWirelessCollector(device=real_ruckus_wireless_device, key=key)
        result = collector.collect()
        assert result.status in ('success', 'failed', 'timeout')
        assert result.device_id == real_ruckus_wireless_device.id
```

2. Register the pytest mark in `pytest.ini` (create at repo root):

```ini
[pytest]
markers =
    real_device: mark test as requiring a real network device (skipped in CI)
testpaths = tests
```

**Files**:
- `tests/integration/test_collectors.py`
- `pytest.ini`

**Parallel?**: Yes — implement simultaneously with T024 and T025.

**Validation**:
- [ ] All parsing tests pass without any SSH connection.
- [ ] `TestCollectorRegistry.test_all_device_types_registered` passes after WP05 + WP06 are merged.
- [ ] `pytest -m "not real_device"` runs without requiring network access.
- [ ] Real-device tests are skipped by default in CI (`pytest -m "not real_device"`).

---

## Test Strategy

**Running non-device tests** (CI-safe):
```bash
pytest tests/integration/ -v -m "not real_device"
```

**Running real-device tests** (requires hardware + env vars):
```bash
export TEST_CISCO_IOS_HOST=10.0.0.1
export TEST_CISCO_IOS_USERNAME=admin
# ... etc.
pytest tests/integration/ -v -m "real_device"
```

**Test DB setup**: The test MariaDB must have the schema from `contracts/schema.sql` applied and at least two test devices inserted:
- Device ID 1: `enabled=1`, any `device_type` (may fail SSH — that's OK for DB tests)
- Device ID 2: `enabled=0` (for disabled exclusion test)

## Risks & Mitigations

- **Test DB teardown**: `autouse` fixture truncates `device_inventory` before each test — ensures isolation even if prior test fails mid-way.
- **Subprocess tests and `sys.exit()`**: Subprocess-based tests capture exit code correctly. Direct function call tests that expect `sys.exit()` should use `pytest.raises(SystemExit)`.
- **Fernet key fixture**: `fernet_key` fixture generates a new key each time — encrypted device passwords in test DB must be encrypted with the matching key. For DB-layer tests (T024) that don't decrypt passwords, any `bytes` value in the `password` column is fine.
- **Ruckus wireless open item**: `TestRealDeviceRuckusWireless` is annotated `@pytest.mark.xfail(reason="device_type unconfirmed")` until hardware validation is complete.

## Review Guidance

- Verify all parsing tests use actual sample output strings (not synthetic invented strings).
- Confirm `pytest.ini` registers the `real_device` mark to suppress PytestUnknownMarkWarning.
- Check `autouse` `clean_device_inventory` fixture is scoped correctly (function scope, not session).
- Verify that `TestFullRun.test_summary_printed_on_completion` does not require real SSH — it should pass even when all devices fail to connect (SSH failure → `status='failed'` row + count in summary).

## Activity Log

> **CRITICAL**: Append new entries at the END. Never prepend.

- 2026-03-12T10:45:33Z – system – lane=planned – Prompt created.
