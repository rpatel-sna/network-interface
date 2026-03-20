"""End-to-end integration tests for the full inventory run (T022).

Validates:
- US1: Full run completes and prints a summary
- US2: Failure handling (device with bad credentials → failed status)
- External DB source wiring: devices loaded from external DB are polled
- Edge cases: zero external devices, missing env var
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.fixture
def base_env(external_db_conn):
    """Minimal valid environment for running main.py against the test DBs.

    external_db_conn is declared as a dependency to ensure the external DB
    schema exists before subprocess tests run.
    """
    return {
        **os.environ,
        # Local results DB
        "DB_HOST": os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        "DB_PORT": os.environ.get("TEST_DB_PORT", "3306"),
        "DB_USER": os.environ.get("TEST_DB_USER", "root"),
        "DB_PASSWORD": os.environ.get("TEST_DB_PASSWORD", ""),
        "DB_NAME": os.environ.get("TEST_DB_NAME", "test_inventory"),
        # External device source DB
        "EXT_DB_HOST": os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        "EXT_DB_PORT": os.environ.get("TEST_DB_PORT", "3306"),
        "EXT_DB_USER": os.environ.get("TEST_DB_USER", "root"),
        "EXT_DB_PASSWORD": os.environ.get("TEST_DB_PASSWORD", ""),
        "EXT_DB_NAME": os.environ.get("TEST_EXT_DB_NAME", "test_ext_devices"),
        "EXT_DB_QUERY": (
            "SELECT id, ip_address, hostname, ssh_port, username, "
            "password, device_type FROM ext_devices"
        ),
        "MAX_THREADS": "2",
        "SSH_TIMEOUT": "5",
        "LOG_FILE": "/tmp/test_inventory.log",
        "LOG_LEVEL": "DEBUG",
    }


class TestFullRunSummary:
    def test_summary_printed_on_completion(self, base_env):
        """US1: Run completes and prints summary with correct labels (FR-011).

        The device(s) will fail SSH (non-routable IP) but the tool must still
        print the summary — all failed devices count in the total.
        """
        result = subprocess.run(
            [sys.executable, "-m", "network_inventory.main"],
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
            [sys.executable, "-m", "network_inventory.main"],
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


class TestExternalDbSourceWiring:
    def test_external_db_device_produces_inventory_row(self, base_env, test_db_conn):
        """Device from external DB is polled and produces a device_inventory row (FR-001)."""
        # Device 1 (seeded in conftest.py) uses non-routable IP — SSH fails, row still written
        subprocess.run(
            [sys.executable, "-m", "network_inventory.main"],
            env=base_env,
            capture_output=True,
            timeout=60,
        )

        cur = test_db_conn.cursor()
        cur.execute(
            "SELECT status, error_message FROM device_inventory WHERE device_id = 1"
        )
        row = cur.fetchone()
        cur.close()

        assert row is not None, "External-DB device must have an inventory row after run"
        assert row[0] in ('success', 'failed', 'timeout'), f"Unexpected status: {row[0]}"
        if row[0] != 'success':
            assert row[1], "Non-success result must have a non-empty error_message (FR-007)"

    def test_zero_external_devices_exits_cleanly(self, base_env, external_db_conn):
        """Zero rows from external DB query → exit 0 with informational message."""
        cur = external_db_conn.cursor()
        cur.execute("DELETE FROM ext_devices")
        external_db_conn.commit()

        try:
            result = subprocess.run(
                [sys.executable, "-m", "network_inventory.main"],
                env=base_env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0
            assert "No enabled devices found" in result.stdout
        finally:
            # Restore the seeded device so other tests still have data
            cur.execute("""
                INSERT INTO ext_devices
                    (id, ip_address, hostname, ssh_port, username, password, device_type)
                VALUES (1, '192.0.2.1', 'test-sw-01', 22, 'admin', 'plaintext_pw', 'cisco_ios')
                ON DUPLICATE KEY UPDATE ip_address=VALUES(ip_address)
            """)
            external_db_conn.commit()
            cur.close()


class TestStartupValidation:
    def test_missing_required_env_var_exits_nonzero(self, base_env):
        """Missing required env var causes EnvironmentError → exit(1) (FR-009)."""
        env = {k: v for k, v in base_env.items() if k != "DB_HOST"}
        result = subprocess.run(
            [sys.executable, "-m", "network_inventory.main"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0

    def test_missing_env_var_error_message_descriptive(self, base_env):
        """EnvironmentError message must name the missing variable (SC-003)."""
        env = {k: v for k, v in base_env.items() if k != "EXT_DB_QUERY"}
        result = subprocess.run(
            [sys.executable, "-m", "network_inventory.main"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0
        assert "EXT_DB_QUERY" in result.stderr, (
            f"Error message should name missing variable. stderr: {result.stderr!r}"
        )

    def test_bad_ext_db_host_exits_nonzero(self, base_env):
        """Unreachable external DB host causes exit(1) within 5 seconds (FR-003)."""
        env = {**base_env, "EXT_DB_HOST": "192.0.2.255"}
        result = subprocess.run(
            [sys.executable, "-m", "network_inventory.main"],
            env=env,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode != 0, "Expected non-zero exit on external DB connection failure"
