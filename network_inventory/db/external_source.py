"""External MariaDB device source — fetches device list for SSH polling."""
from __future__ import annotations

import logging
import sys

import mariadb

from network_inventory.config import Settings
from network_inventory.models.device import Device

logger = logging.getLogger(__name__)

_REQUIRED_COLS = ("ip_address", "device_type", "username", "password")


def load_devices_from_external_db(app_settings: Settings) -> list[Device]:
    """Connect to the external MariaDB, run the configured query, validate
    and deduplicate rows, and return a list of Device instances.

    Exits with sys.exit(1) on connection failure (timeout: 5s) or query error.
    Skips rows missing required fields (ip_address, device_type, username,
    password) with a WARNING log per skipped row.
    Deduplicates by ip_address; logs WARNING for each dropped duplicate.

    Args:
        app_settings: Loaded Settings instance with ext_db_* fields.

    Returns:
        List of Device instances (may be empty if query returns zero rows).
    """
    # --- Connect ---
    conn: mariadb.Connection | None = None
    try:
        conn = mariadb.connect(
            host=app_settings.ext_db_host,
            port=app_settings.ext_db_port,
            user=app_settings.ext_db_user,
            password=app_settings.ext_db_password,
            database=app_settings.ext_db_name,
            connect_timeout=5,
        )
    except mariadb.Error as exc:
        logger.error(
            "Failed to connect to external device source DB at %s:%s — %s",
            app_settings.ext_db_host,
            app_settings.ext_db_port,
            exc,
        )
        sys.exit(1)

    # --- Query ---
    try:
        cursor = conn.cursor()
        cursor.execute(app_settings.ext_db_query)
        rows = cursor.fetchall()
        col_names = [desc[0].lower() for desc in cursor.description]
        cursor.close()
    except mariadb.Error as exc:
        logger.error("External device query failed: %s", exc)
        sys.exit(1)
    finally:
        conn.close()

    logger.info("External DB query returned %d row(s)", len(rows))

    # --- Validate rows ---
    validated: list[Device] = []

    for idx, row in enumerate(rows):
        row_dict = dict(zip(col_names, row))

        missing = [c for c in _REQUIRED_COLS if not row_dict.get(c)]
        if missing:
            logger.warning(
                "External DB row %d skipped — missing required field(s): %s. "
                "Row data: %s",
                idx,
                ", ".join(missing),
                {k: row_dict.get(k) for k in _REQUIRED_COLS},
            )
            continue

        device = Device(
            id=int(row_dict.get("id") or idx),
            hostname=str(row_dict.get("hostname") or row_dict["ip_address"]),
            ip_address=str(row_dict["ip_address"]),
            ssh_port=int(row_dict.get("ssh_port") or 22),
            username=str(row_dict["username"]),
            password=str(row_dict["password"]),
            device_type=str(row_dict["device_type"]),
            enabled=True,
        )
        validated.append(device)

    logger.info("%d valid device row(s) after validation", len(validated))

    # --- Deduplicate by ip_address ---
    seen_ips: set[str] = set()
    deduped: list[Device] = []

    for device in validated:
        if device.ip_address in seen_ips:
            logger.warning(
                "Duplicate ip_address '%s' (hostname=%r) dropped — "
                "keeping first occurrence",
                device.ip_address,
                device.hostname,
            )
            continue
        seen_ips.add(device.ip_address)
        deduped.append(device)

    logger.info(
        "Returning %d device(s) after deduplication (dropped %d duplicate(s))",
        len(deduped),
        len(validated) - len(deduped),
    )
    return deduped
