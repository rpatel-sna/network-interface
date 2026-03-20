"""SQL queries: upsert inventory results."""
from __future__ import annotations

import logging

import mariadb

from network_inventory.models.device import CollectionResult

logger = logging.getLogger(__name__)

# ON DUPLICATE KEY UPDATE is keyed by the UNIQUE constraint on device_id.
# last_success is preserved (not overwritten) on non-success results — MariaDB IF() expression.
_UPSERT_INVENTORY_SQL = """
    INSERT INTO device_inventory
        (device_id, serial_number, firmware_version, last_success, last_attempt,
         status, error_message)
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


def upsert_inventory_record(conn: mariadb.Connection, result: CollectionResult) -> None:
    """Insert or update a device_inventory row for the given poll result.

    Keyed by device_id (UNIQUE constraint). Preserves last_success when status
    is 'failed' or 'timeout' — only updates it on 'success'.

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

    logger.debug(
        "Upserted device_inventory for device_id=%d status=%s",
        result.device_id,
        result.status,
    )
