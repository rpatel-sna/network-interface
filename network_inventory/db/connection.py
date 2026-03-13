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

    Exits the process with code 1 if the database is unreachable (FR-013).
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
            pool_size=settings.max_threads + 2,  # +2 headroom for main thread writes
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            connect_timeout=10,
        )
        logger.info(
            "MariaDB connection pool established (host=%s, db=%s)",
            settings.db_host,
            settings.db_name,
        )
        return pool
    except mariadb.Error as exc:
        logger.error("Failed to connect to database: %s", exc)
        sys.exit(1)


def get_connection() -> mariadb.Connection:
    """Acquire a connection from the pool.

    Each caller is responsible for closing the connection after use to return
    it to the pool. Do NOT share a single connection across threads.
    """
    return get_pool().get_connection()
