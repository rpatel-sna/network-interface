"""Shared fixtures for integration tests."""
from __future__ import annotations

import os

import mariadb
import pytest

from network_inventory.config import Settings


# ---------------------------------------------------------------------------
# Local (results) DB connection
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_db_conn():
    """Provide a MariaDB connection to the test (results) database (session-scoped)."""
    conn = mariadb.connect(
        host=os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("TEST_DB_PORT", "3306")),
        user=os.environ.get("TEST_DB_USER", "root"),
        password=os.environ.get("TEST_DB_PASSWORD", ""),
        database=os.environ.get("TEST_DB_NAME", "test_inventory"),
    )
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# External (device source) DB connection + schema
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def external_db_conn():
    """Provide a MariaDB connection to the test external device source DB.

    Points at the same local MariaDB instance but uses TEST_EXT_DB_NAME
    (default: test_ext_devices) to simulate an external device source without
    requiring a separate database server.
    """
    conn = mariadb.connect(
        host=os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("TEST_DB_PORT", "3306")),
        user=os.environ.get("TEST_DB_USER", "root"),
        password=os.environ.get("TEST_DB_PASSWORD", ""),
        database=os.environ.get("TEST_EXT_DB_NAME", "test_ext_devices"),
    )
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ext_devices (
            id          INT          PRIMARY KEY AUTO_INCREMENT,
            ip_address  VARCHAR(45)  NOT NULL,
            hostname    VARCHAR(255),
            ssh_port    INT          DEFAULT 22,
            username    VARCHAR(255) NOT NULL,
            password    VARCHAR(255) NOT NULL,
            device_type VARCHAR(100) NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    yield conn
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS ext_devices")
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture(scope="session")
def ext_db_settings(external_db_conn):
    """Settings instance with ext_db_* fields pointing to the test external DB."""
    return Settings(
        db_host=os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        db_port=int(os.environ.get("TEST_DB_PORT", "3306")),
        db_user=os.environ.get("TEST_DB_USER", "root"),
        db_password=os.environ.get("TEST_DB_PASSWORD", ""),
        db_name=os.environ.get("TEST_DB_NAME", "test_inventory"),
        ext_db_host=os.environ.get("TEST_DB_HOST", "127.0.0.1"),
        ext_db_port=int(os.environ.get("TEST_DB_PORT", "3306")),
        ext_db_user=os.environ.get("TEST_DB_USER", "root"),
        ext_db_password=os.environ.get("TEST_DB_PASSWORD", ""),
        ext_db_name=os.environ.get("TEST_EXT_DB_NAME", "test_ext_devices"),
        ext_db_query=(
            "SELECT id, ip_address, hostname, ssh_port, username, "
            "password, device_type FROM ext_devices"
        ),
    )


# ---------------------------------------------------------------------------
# Seed external DB with a default test device (used by full-run tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def seed_ext_test_devices(external_db_conn):
    """Insert a test device into ext_devices for use by full-run subprocess tests.

    Device uses a non-routable IP (192.0.2.1) so SSH always fails — the tool
    still writes an inventory row with status=failed, which is what we assert.
    """
    cur = external_db_conn.cursor()
    cur.execute("""
        INSERT INTO ext_devices (id, ip_address, hostname, ssh_port, username,
                                 password, device_type)
        VALUES (1, '192.0.2.1', 'test-sw-01', 22, 'admin', 'plaintext_pw', 'cisco_ios')
        ON DUPLICATE KEY UPDATE
            ip_address=VALUES(ip_address), hostname=VALUES(hostname),
            password=VALUES(password)
    """)
    external_db_conn.commit()
    cur.close()
    yield


# ---------------------------------------------------------------------------
# Per-test cleanup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_device_inventory(test_db_conn):
    """Truncate device_inventory before each test case for isolation."""
    yield
    cur = test_db_conn.cursor()
    cur.execute("DELETE FROM device_inventory")
    test_db_conn.commit()
    cur.close()
