"""Abstract base collector — SSH connection + collect() template method."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from network_inventory.config import Settings, settings as default_settings
from network_inventory.models.device import CollectionResult, Device
from network_inventory.utils.error_handler import classify_exception

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Subclass this to implement a new device type collector.

    Subclasses must implement:
        get_serial_number(self) -> str | None
        get_firmware_version(self) -> str | None

    The SSH connection is available as self.connection during those calls.

    Extension protocol (FR-014):
        1. Create network_inventory/collectors/<vendor_platform>.py
        2. Subclass BaseCollector and implement the two abstract methods
        3. Register in COLLECTOR_REGISTRY in network_inventory/collectors/__init__.py
        No other files require changes.
    """

    def __init__(
        self,
        device: Device,
        app_settings: Settings | None = None,
    ) -> None:
        self.device = device
        self._settings = app_settings or default_settings
        self.connection: ConnectHandler | None = None

    def _connect(self) -> None:
        """Open an SSH session to the device. Sets self.connection."""
        self.connection = ConnectHandler(
            device_type=self.device.device_type,
            host=self.device.ip_address,
            port=self.device.ssh_port,
            username=self.device.username,
            password=self.device.password,
            timeout=self._settings.ssh_timeout,
            session_log=None,       # Never log session data (may contain credentials)
            global_delay_factor=2,  # Slightly generous timing for slow devices
        )

    def _disconnect(self) -> None:
        """Close the SSH session if open (best-effort)."""
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception:
                pass  # Best-effort; do not mask the original error
            self.connection = None

    @abstractmethod
    def get_serial_number(self) -> str | None:
        """Return the device serial number, or None if not parseable.

        self.connection is open and ready when this is called.
        """
        ...

    @abstractmethod
    def get_firmware_version(self) -> str | None:
        """Return the firmware/OS version string, or None if not parseable.

        self.connection is open and ready when this is called.
        """
        ...

    def collect(self) -> CollectionResult:
        """Template method: connect → collect data → disconnect → return result.

        Always returns a CollectionResult — never raises. Status will be
        'success', 'failed', or 'timeout' depending on the outcome.

        Returns:
            CollectionResult with appropriate status and fields populated.
        """
        attempted_at = datetime.now(timezone.utc).replace(tzinfo=None)  # Naive UTC for MariaDB

        try:
            self._connect()
            serial_number = self.get_serial_number()
            firmware_version = self.get_firmware_version()

            logger.info(
                "%s (%s) — polled successfully: serial=%r firmware=%r",
                self.device.hostname,
                self.device.ip_address,
                serial_number,
                firmware_version,
            )

            return CollectionResult(
                device_id=self.device.id,
                status='success',
                attempted_at=attempted_at,
                serial_number=serial_number,
                firmware_version=firmware_version,
                succeeded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )

        except (NetmikoTimeoutException, NetmikoAuthenticationException, Exception) as exc:
            status, error_message = classify_exception(exc)
            logger.warning(
                "%s (%s) — %s: %s",
                self.device.hostname,
                self.device.ip_address,
                status,
                error_message,
            )
            return CollectionResult(
                device_id=self.device.id,
                status=status,
                attempted_at=attempted_at,
                error_message=error_message,
            )

        finally:
            self._disconnect()
