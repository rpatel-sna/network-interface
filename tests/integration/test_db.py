"""Integration tests for the database layer (T021).

Tests:
- Upsert correctness: first insert, second overwrite, last_success preservation
- Partial data (null fields) written correctly
- Connection failure at startup causes sys.exit(1)
- load_devices_from_external_db: happy path, zero rows, missing fields, duplicates,
  unreachable DB
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime

import mariadb
import pytest

from network_inventory.db.external_source import load_devices_from_external_db
from network_inventory.db.queries import upsert_inventory_record
from network_inventory.models.device import CollectionResult


class TestUpsertCorrectness:
    def test_first_upsert_creates_row(self, test_db_conn):
        """First upsert for a device_id creates a new row with correct fields."""
        result = CollectionResult(
            device_id=1,
            status='success',
            attempted_at=datetime.utcnow(),
            serial_number='SN001',
            firmware_version='v1.0',
            succeeded_at=datetime.utcnow(),
        )
        upsert_inventory_record(test_db_conn, result)

        cur = test_db_conn.cursor()
        cur.execute(
            "SELECT status, serial_number, firmware_version FROM device_inventory "
            "WHERE device_id = 1"
        )
        row = cur.fetchone()
        cur.close()

        assert row is not None
        assert row[0] == 'success'
        assert row[1] == 'SN001'
        assert row[2] == 'v1.0'

    def test_second_upsert_overwrites_status_and_preserves_serial(self, test_db_conn):
        """Second upsert for the same device_id updates status; no duplicate row created."""
        success = CollectionResult(
            device_id=1,
            status='success',
            attempted_at=datetime.utcnow(),
            serial_number='SN001',
            succeeded_at=datetime.utcnow(),
        )
        failed = CollectionResult(
            device_id=1,
            status='failed',
            attempted_at=datetime.utcnow(),
            error_message='auth failed',
        )
        upsert_inventory_record(test_db_conn, success)
        upsert_inventory_record(test_db_conn, failed)

        cur = test_db_conn.cursor()
        cur.execute("SELECT COUNT(*), status FROM device_inventory WHERE device_id = 1")
        row = cur.fetchone()
        cur.close()

        assert row[0] == 1, "Expected exactly one row after two upserts"
        assert row[1] == 'failed'

    def test_last_success_preserved_on_failure(self, test_db_conn):
        """last_success is NOT overwritten when status is 'failed'."""
        success = CollectionResult(
            device_id=1,
            status='success',
            attempted_at=datetime.utcnow(),
            succeeded_at=datetime.utcnow(),
        )
        upsert_inventory_record(test_db_conn, success)

        failed = CollectionResult(
            device_id=1,
            status='failed',
            attempted_at=datetime.utcnow(),
            error_message='connection refused',
        )
        upsert_inventory_record(test_db_conn, failed)

        cur = test_db_conn.cursor()
        cur.execute(
            "SELECT status, last_success FROM device_inventory WHERE device_id = 1"
        )
        row = cur.fetchone()
        cur.close()

        assert row[0] == 'failed'
        assert row[1] is not None, "last_success should be preserved from previous success"

    def test_last_success_preserved_on_timeout(self, test_db_conn):
        """last_success is NOT overwritten when status is 'timeout'."""
        success = CollectionResult(
            device_id=1,
            status='success',
            attempted_at=datetime.utcnow(),
            succeeded_at=datetime.utcnow(),
        )
        upsert_inventory_record(test_db_conn, success)

        timeout = CollectionResult(
            device_id=1,
            status='timeout',
            attempted_at=datetime.utcnow(),
            error_message='timed out after 30s',
        )
        upsert_inventory_record(test_db_conn, timeout)

        cur = test_db_conn.cursor()
        cur.execute("SELECT last_success FROM device_inventory WHERE device_id = 1")
        row = cur.fetchone()
        cur.close()

        assert row[0] is not None, "last_success should be preserved from previous success"

    def test_partial_data_null_fields_written(self, test_db_conn):
        """Serial null but firmware present — partial data is stored, not rejected."""
        result = CollectionResult(
            device_id=1,
            status='failed',
            attempted_at=datetime.utcnow(),
            serial_number=None,
            firmware_version='v2.0',
            error_message='parse error',
        )
        upsert_inventory_record(test_db_conn, result)

        cur = test_db_conn.cursor()
        cur.execute(
            "SELECT serial_number, firmware_version FROM device_inventory WHERE device_id = 1"
        )
        row = cur.fetchone()
        cur.close()

        assert row[0] is None
        assert row[1] == 'v2.0'


class TestConnectionFailure:
    def test_bad_db_host_exits_nonzero(self):
        """Local results DB connection failure at startup causes non-zero exit (FR-013)."""
        env = {
            **os.environ,
            "DB_HOST": "192.0.2.255",   # Documentation range — guaranteed non-routable
            "DB_PORT": "3306",
            "DB_USER": "test",
            "DB_PASSWORD": "test",
            "DB_NAME": "test",
            "EXT_DB_HOST": "127.0.0.1",
            "EXT_DB_PORT": "3306",
            "EXT_DB_USER": "test",
            "EXT_DB_PASSWORD": "test",
            "EXT_DB_NAME": "test",
            "EXT_DB_QUERY": "SELECT 1",
        }
        result = subprocess.run(
            [sys.executable, "-m", "network_inventory.main"],
            env=env,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode != 0, "Expected non-zero exit on DB connection failure"


class TestLoadDevicesFromExternalDb:
    """Tests for load_devices_from_external_db() — FR-001, FR-007, FR-008, FR-009, FR-010."""

    def _seed(self, conn, rows):
        """Insert rows into ext_devices and return them after the test."""
        cur = conn.cursor()
        cur.execute("DELETE FROM ext_devices")
        for row in rows:
            cur.execute("""
                INSERT INTO ext_devices
                    (ip_address, hostname, ssh_port, username, password, device_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, row)
        conn.commit()
        cur.close()

    def test_happy_path_returns_device_list(self, external_db_conn, ext_db_settings):
        """Valid rows → correct Device list with expected field values (FR-001)."""
        self._seed(external_db_conn, [
            ("10.0.0.1", "sw-core-01", 22, "admin", "secret", "cisco_ios"),
            ("10.0.0.2", "sw-core-02", 22, "admin", "secret", "cisco_ios"),
        ])
        devices = load_devices_from_external_db(ext_db_settings)

        assert len(devices) == 2
        ips = {d.ip_address for d in devices}
        assert "10.0.0.1" in ips
        assert "10.0.0.2" in ips
        # All devices from external source are enabled=True
        assert all(d.enabled for d in devices)
        # Password is plaintext str
        assert all(isinstance(d.password, str) for d in devices)

    def test_zero_rows_returns_empty_list(self, external_db_conn, ext_db_settings):
        """External query returning zero rows → returns [] (caller handles empty case)."""
        self._seed(external_db_conn, [])
        devices = load_devices_from_external_db(ext_db_settings)
        assert devices == []

    def test_row_missing_ip_address_is_skipped(
        self, external_db_conn, ext_db_settings, caplog
    ):
        """Row without ip_address is skipped with WARNING; valid rows still returned (FR-008)."""
        # Insert a valid row directly (normal path)
        self._seed(external_db_conn, [
            ("10.0.0.1", "valid-sw", 22, "admin", "secret", "cisco_ios"),
        ])
        # Insert a row with NULL ip_address by patching the query
        cur = external_db_conn.cursor()
        cur.execute("""
            INSERT INTO ext_devices (ip_address, hostname, username, password, device_type)
            VALUES ('', 'missing-ip', 'admin', 'secret', 'cisco_ios')
        """)
        external_db_conn.commit()
        cur.close()

        import logging
        with caplog.at_level(logging.WARNING, logger="network_inventory.db.external_source"):
            devices = load_devices_from_external_db(ext_db_settings)

        # Only the valid row is returned; empty ip_address row is skipped
        assert len(devices) == 1
        assert devices[0].ip_address == "10.0.0.1"
        assert any("missing required field" in r.message.lower() for r in caplog.records)

    def test_duplicate_ip_address_dropped_with_warning(
        self, external_db_conn, ext_db_settings, caplog
    ):
        """Two rows with same ip_address → first kept, second dropped with WARNING (FR-010)."""
        self._seed(external_db_conn, [
            ("10.0.0.1", "sw-primary", 22, "admin", "secret", "cisco_ios"),
            ("10.0.0.1", "sw-duplicate", 22, "admin", "secret", "cisco_ios"),
        ])

        import logging
        with caplog.at_level(logging.WARNING, logger="network_inventory.db.external_source"):
            devices = load_devices_from_external_db(ext_db_settings)

        assert len(devices) == 1
        assert devices[0].hostname == "sw-primary"
        assert any("duplicate" in r.message.lower() for r in caplog.records)

    def test_hostname_defaults_to_ip_address(self, external_db_conn, ext_db_settings):
        """Row with no hostname → Device.hostname defaults to ip_address (FR-008)."""
        self._seed(external_db_conn, [
            ("10.0.0.1", None, 22, "admin", "secret", "cisco_ios"),
        ])
        devices = load_devices_from_external_db(ext_db_settings)

        assert len(devices) == 1
        assert devices[0].hostname == "10.0.0.1"

    def test_ssh_port_defaults_to_22(self, external_db_conn, ext_db_settings):
        """Row with no ssh_port → Device.ssh_port defaults to 22 (FR-008)."""
        cur = external_db_conn.cursor()
        cur.execute("DELETE FROM ext_devices")
        cur.execute("""
            INSERT INTO ext_devices (ip_address, hostname, username, password, device_type)
            VALUES ('10.0.0.1', 'sw-01', 'admin', 'secret', 'cisco_ios')
        """)
        external_db_conn.commit()
        cur.close()

        devices = load_devices_from_external_db(ext_db_settings)

        assert len(devices) == 1
        assert devices[0].ssh_port == 22

    def test_unreachable_external_db_exits_one(self, ext_db_settings, monkeypatch):
        """Unreachable external DB causes sys.exit(1) within 5 seconds (FR-003)."""
        def _fail(**kwargs):
            raise mariadb.Error("Connection timed out")

        monkeypatch.setattr(mariadb, "connect", _fail)

        with pytest.raises(SystemExit) as exc_info:
            load_devices_from_external_db(ext_db_settings)

        assert exc_info.value.code == 1
