"""Shared fixtures for integration tests."""
from __future__ import annotations

import os
from datetime import datetime

import mariadb
import pytest
from cryptography.fernet import Fernet


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_db_conn():
    """Provide a MariaDB connection to the test database (session-scoped)."""
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
# Fernet key
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fernet_key() -> bytes:
    """Generate a fresh Fernet key (session-scoped — shared across tests)."""
    return Fernet.generate_key()


@pytest.fixture(scope="session")
def key_file(tmp_path_factory, fernet_key):
    """Write the Fernet key to a temp file and return its path."""
    key_path = tmp_path_factory.mktemp("keys") / "test.key"
    key_path.write_bytes(fernet_key)
    return str(key_path)


# ---------------------------------------------------------------------------
# Test device seeding
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def seed_test_devices(test_db_conn, fernet_key):
    """Insert test devices used across the integration suite.

    Device 1: enabled=1  (will be polled)
    Device 2: enabled=0  (must be excluded from polling — US3)
    Passwords are Fernet-encrypted with the session key.
    """
    from cryptography.fernet import Fernet as F
    enc_password = F(fernet_key).encrypt(b"test_password")

    cur = test_db_conn.cursor()

    # Upsert to be idempotent across test runs
    cur.execute("""
        INSERT INTO devices (id, hostname, ip_address, ssh_port, username, password,
                             device_type, enabled)
        VALUES (1, 'test-sw-enabled', '192.0.2.1', 22, 'admin', ?, 'cisco_ios', 1)
        ON DUPLICATE KEY UPDATE
            hostname=VALUES(hostname), ip_address=VALUES(ip_address),
            password=VALUES(password), enabled=VALUES(enabled)
    """, (enc_password,))

    cur.execute("""
        INSERT INTO devices (id, hostname, ip_address, ssh_port, username, password,
                             device_type, enabled)
        VALUES (2, 'test-sw-disabled', '192.0.2.2', 22, 'admin', ?, 'cisco_ios', 0)
        ON DUPLICATE KEY UPDATE
            hostname=VALUES(hostname), ip_address=VALUES(ip_address),
            password=VALUES(password), enabled=VALUES(enabled)
    """, (enc_password,))

    test_db_conn.commit()
    cur.close()
    yield
    # Leave devices in DB — truncated by clean_device_inventory between tests


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
