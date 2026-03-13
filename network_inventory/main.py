"""Network Device Inventory CLI — entry point.

Usage:
    python network_inventory/main.py

Startup sequence:
    1. Configure logging
    2. Validate config (EnvironmentError → exit 1)
    3. Load and validate Fernet key file
    4. Establish MariaDB connection pool (fail-fast on error → exit 1)
    5. Load enabled devices from DB
    6. Handle zero-devices edge case (exit 0 with message)
    7. Dispatch all devices to ThreadPoolExecutor
    8. Collect results and upsert each to DB
    9. Print completion summary and exit 0
"""
from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Step 1: Configure logging before any other imports that might log
# ---------------------------------------------------------------------------
# Deferred until settings are loaded; see _bootstrap() below.


def main() -> None:
    """Run the inventory collection tool end-to-end."""

    # ------------------------------------------------------------------
    # Step 1: Logging (must come first so all subsequent messages are captured)
    # ------------------------------------------------------------------
    from network_inventory.utils.logger import configure_logging, get_logger

    # Load settings first — needed for log file path and level
    try:
        from network_inventory.config import settings
    except EnvironmentError as exc:
        # Can't log yet (no log file path); print to stderr and exit
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    configure_logging(log_file=settings.log_file, log_level=settings.log_level)
    logger = get_logger(__name__)
    logger.info("Network Device Inventory CLI starting up")

    # ------------------------------------------------------------------
    # Step 2: Validate Fernet key file (FR-010)
    # ------------------------------------------------------------------
    from network_inventory.utils.encryption import load_key

    try:
        key = load_key(settings.encryption_key_file)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        logger.error("Encryption key error: %s", exc)
        sys.exit(1)

    logger.debug("Encryption key loaded from %s", settings.encryption_key_file)

    # ------------------------------------------------------------------
    # Step 3: Establish DB connection pool — exits on failure (FR-013)
    # ------------------------------------------------------------------
    from network_inventory.db import get_connection, get_pool, load_enabled_devices, upsert_inventory_record

    get_pool()  # Calls sys.exit(1) internally on mariadb.Error

    # ------------------------------------------------------------------
    # Step 4: Load enabled devices (FR-001)
    # ------------------------------------------------------------------
    conn = get_connection()
    try:
        devices = load_enabled_devices(conn)
    finally:
        conn.close()

    # ------------------------------------------------------------------
    # Step 5: Zero-devices edge case
    # ------------------------------------------------------------------
    if not devices:
        print("No enabled devices found. Nothing to poll.")
        logger.info("No enabled devices found — exiting cleanly.")
        sys.exit(0)

    logger.info("Starting inventory run for %d device(s)", len(devices))

    # ------------------------------------------------------------------
    # Steps 6-8: Dispatch, collect, and upsert (FR-002, FR-005, FR-006, FR-007, FR-008)
    # ------------------------------------------------------------------
    from network_inventory.collectors import get_collector
    from network_inventory.models.device import CollectionResult
    from network_inventory.utils.error_handler import classify_exception

    counts: dict[str, int] = {'success': 0, 'failed': 0, 'timeout': 0}
    future_to_device: dict[Future[CollectionResult], object] = {}

    with ThreadPoolExecutor(max_workers=settings.max_threads) as executor:
        # Submit all devices with known collectors
        for device in devices:
            collector_class = get_collector(device.device_type)
            if collector_class is None:
                # Warning already emitted by get_collector(); device is skipped
                logger.warning(
                    "Skipping %s (%s) — device_type '%s' has no registered collector",
                    device.hostname,
                    device.ip_address,
                    device.device_type,
                )
                continue

            collector = collector_class(device=device, key=key)
            future = executor.submit(collector.collect)
            future_to_device[future] = device

        # Collect results as they complete
        for future in as_completed(future_to_device):
            device = future_to_device[future]

            try:
                result: CollectionResult = future.result()
            except Exception as exc:
                # BaseCollector.collect() should never propagate exceptions,
                # but guard defensively so no device is silently dropped.
                status, error_message = classify_exception(exc)
                result = CollectionResult(
                    device_id=device.id,
                    status=status,
                    attempted_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    error_message=f"Unexpected orchestrator error: {error_message}",
                )
                logger.error(
                    "%s (%s) — unexpected future error: %s",
                    device.hostname,
                    device.ip_address,
                    exc,
                )

            # Upsert in main thread (thread-safe: fresh connection per write)
            write_conn = get_connection()
            try:
                upsert_inventory_record(write_conn, result)
            finally:
                write_conn.close()

            counts[result.status] += 1
            logger.info(
                "%s (%s) — %s",
                device.hostname,
                device.ip_address,
                result.status,
            )

    # ------------------------------------------------------------------
    # Step 9: Completion summary (FR-011)
    # ------------------------------------------------------------------
    total = sum(counts.values())

    print("\nInventory run complete.")
    print(f"  Total polled : {total}")
    print(f"  Success      : {counts['success']}")
    print(f"  Failed       : {counts['failed']}")
    print(f"  Timeout      : {counts['timeout']}")

    logger.info(
        "Run complete — total=%d success=%d failed=%d timeout=%d",
        total,
        counts['success'],
        counts['failed'],
        counts['timeout'],
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
