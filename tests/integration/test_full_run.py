"""End-to-end integration tests for the full inventory run (T025).

Validates:
- US1: Full run completes and prints a summary
- US2: Failure handling (device with bad credentials → failed status)
- US3: Disabled device exclusion
- Edge cases: zero enabled devices, missing key file, missing env var
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.fixture
def base_env(key_file):
    """Minimal valid environment for running main.py against the test DB."""
    return {
        **os.environ,
        "DB_HOST": os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        "DB_PORT": os.environ.get("TEST_DB_PORT", "3306"),
        "DB_USER": os.environ.get("TEST_DB_USER", "root"),
        "DB_PASSWORD": os.environ.get("TEST_DB_PASSWORD", ""),
        "DB_NAME": os.environ.get("TEST_DB_NAME", "test_inventory"),
        "ENCRYPTION_KEY_FILE": key_file,
        "MAX_THREADS": "2",
        "SSH_TIMEOUT": "5",
        "LOG_FILE": "/tmp/test_inventory.log",
        "LOG_LEVEL": "DEBUG",
    }


class TestFullRunSummary:
    def test_summary_printed_on_completion(self, base_env):
        """US1: Run completes and prints summary with correct labels (FR-011).

        The device(s) will likely fail SSH (no real devices) but the tool must
        still print the summary — all failed devices count in the total.
        """
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=base_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "Inventory run complete." in result.stdout
        assert "Total polled" in result.stdout
        assert "Success" in result.stdout
        assert "Failed" in result.stdout
        assert "Timeout" in result.stdout

    def test_summary_counts_are_consistent(self, base_env):
        """Total polled = Success + Failed + Timeout."""
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=base_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        lines = {
            line.split(":")[0].strip(): line.split(":")[-1].strip()
            for line in result.stdout.splitlines()
            if ":" in line
        }
        if "Total polled" in lines:
            total = int(lines["Total polled"])
            success = int(lines.get("Success", 0))
            failed = int(lines.get("Failed", 0))
            timeout = int(lines.get("Timeout", 0))
            assert total == success + failed + timeout


class TestDisabledDeviceExclusion:
    def test_disabled_device_has_no_inventory_row(self, base_env, test_db_conn):
        """US3: Device with enabled=0 must not produce a device_inventory row."""
        # Ensure device 2 has no pre-existing row
        cur = test_db_conn.cursor()
        cur.execute("DELETE FROM device_inventory WHERE device_id = 2")
        test_db_conn.commit()
        cur.close()

        subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=base_env,
            capture_output=True,
            timeout=60,
        )

        cur = test_db_conn.cursor()
        cur.execute("SELECT id FROM device_inventory WHERE device_id = 2")
        row = cur.fetchone()
        cur.close()

        assert row is None, "Disabled device (id=2) must not have an inventory row"

    def test_no_enabled_devices_exits_cleanly(self, base_env, test_db_conn):
        """Edge case: zero enabled devices → exit 0 with informational message."""
        cur = test_db_conn.cursor()
        cur.execute("UPDATE devices SET enabled = 0")
        test_db_conn.commit()

        try:
            result = subprocess.run(
                [sys.executable, "network_inventory/main.py"],
                env=base_env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0
            assert "No enabled devices found" in result.stdout
        finally:
            cur.execute("UPDATE devices SET enabled = 1 WHERE id = 1")
            test_db_conn.commit()
            cur.close()


class TestStartupValidation:
    def test_missing_key_file_exits_nonzero(self, base_env):
        """Missing ENCRYPTION_KEY_FILE causes exit(1) before any polling (FR-010)."""
        env = {**base_env, "ENCRYPTION_KEY_FILE": "/nonexistent/path/key.file"}
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0

    def test_missing_required_env_var_exits_nonzero(self, base_env):
        """Missing required env var causes EnvironmentError → exit(1) (FR-009)."""
        env = {k: v for k, v in base_env.items() if k != "DB_HOST"}
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0

    def test_missing_env_var_error_message_descriptive(self, base_env):
        """EnvironmentError message must name the missing variable (SC-003)."""
        env = {k: v for k, v in base_env.items() if k != "DB_NAME"}
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0
        # Error goes to stderr
        assert "DB_NAME" in result.stderr, (
            f"Error message should name missing variable. stderr: {result.stderr!r}"
        )


class TestFailureHandling:
    def test_failed_device_produces_inventory_row(self, base_env, test_db_conn):
        """US2: A device that fails SSH still gets a device_inventory row with status=failed."""
        # Device 1 uses a non-routable IP (192.0.2.1) — will timeout or fail
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=base_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Check that a row was written for device 1 regardless of SSH outcome
        cur = test_db_conn.cursor()
        cur.execute(
            "SELECT status, error_message FROM device_inventory WHERE device_id = 1"
        )
        row = cur.fetchone()
        cur.close()

        assert row is not None, "Enabled device must have an inventory row after run (FR-005)"
        assert row[0] in ('success', 'failed', 'timeout'), f"Unexpected status: {row[0]}"
        if row[0] != 'success':
            assert row[1], "Non-success result must have a non-empty error_message (FR-007)"
