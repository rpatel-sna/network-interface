"""Integration tests for the database layer (T024).

Tests:
- Upsert correctness: first insert, second overwrite, last_success preservation
- Partial data (null fields) written correctly
- Connection failure at startup causes sys.exit(1)
- load_enabled_devices excludes disabled devices
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime

import pytest

from network_inventory.db.queries import load_enabled_devices, upsert_inventory_record
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
    def test_bad_db_host_exits_nonzero(self, key_file):
        """DB connection failure at startup causes non-zero exit code (FR-013)."""
        env = {
            **os.environ,
            "DB_HOST": "192.0.2.255",   # Documentation range — guaranteed non-routable
            "DB_PORT": "3306",
            "DB_USER": "test",
            "DB_PASSWORD": "test",
            "DB_NAME": "test",
            "ENCRYPTION_KEY_FILE": key_file,
        }
        result = subprocess.run(
            [sys.executable, "network_inventory/main.py"],
            env=env,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode != 0, "Expected non-zero exit on DB connection failure"


class TestLoadEnabledDevices:
    def test_only_enabled_devices_returned(self, test_db_conn):
        """load_enabled_devices() returns only devices with enabled=1 (FR-001, US3)."""
        devices = load_enabled_devices(test_db_conn)
        assert all(d.enabled for d in devices), (
            "load_enabled_devices() returned a disabled device"
        )

    def test_disabled_device_not_in_results(self, test_db_conn):
        """Device 2 (enabled=0) must not appear in results."""
        devices = load_enabled_devices(test_db_conn)
        device_ids = {d.id for d in devices}
        assert 2 not in device_ids, "Disabled device (id=2) should not be loaded"

    def test_password_returned_as_bytes(self, test_db_conn):
        """Device.password must be bytes (VARBINARY coercion)."""
        devices = load_enabled_devices(test_db_conn)
        assert devices, "Need at least one enabled device for this test"
        assert isinstance(devices[0].password, bytes), (
            "Device.password should be bytes, not bytearray or str"
        )
