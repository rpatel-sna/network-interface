"""Ruckus Wireless Controller collector.

Registered device_type values: ruckus_wireless

⚠️  OPEN ITEM (research.md): Ruckus wireless controllers do not have a confirmed
    Netmiko device_type. This collector attempts connection using, in order:
    1. The device_type value stored in the DB (e.g. 'ruckus_wireless')
    2. 'linux'
    3. 'generic_termserver'
    A NetmikoTimeoutException (device unreachable) is re-raised immediately without
    trying fallbacks. All other connection failures trigger the next fallback.
    If all options are exhausted, the final exception propagates to BaseCollector.collect()
    which returns status='failed' with a descriptive error_message.

    Must be validated against real Ruckus ZoneDirector / SmartZone hardware before
    v1 sign-off.

SSH commands:
  - Serial:   show version → "Serial Number : <value>"
  - Firmware: show version → "Version : <value>"
"""
from __future__ import annotations

import logging
import re

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException

from network_inventory.collectors.base_collector import BaseCollector
from network_inventory.utils.encryption import decrypt_password

logger = logging.getLogger(__name__)

_SERIAL_PATTERN = re.compile(r'Serial\s+Number\s*:\s*(\S+)', re.IGNORECASE)
_FIRMWARE_PATTERN = re.compile(r'\bVersion\s*:\s*(\S+)', re.IGNORECASE)

# Fallback device_type values tried in order after the primary
_FALLBACK_DEVICE_TYPES = ['linux', 'generic_termserver']


class RuckusWirelessCollector(BaseCollector):
    """Collector for Ruckus wireless controllers (ZoneDirector, SmartZone).

    Overrides _connect() to attempt multiple Netmiko device_type values.
    """

    def _connect(self) -> None:
        """Attempt SSH with the configured device_type, then fallbacks.

        Re-raises NetmikoTimeoutException immediately (device unreachable —
        fallback to a different device_type won't help).
        """
        plaintext_password = decrypt_password(self._key, self.device.password)

        device_types_to_try = [self.device.device_type] + [
            dt for dt in _FALLBACK_DEVICE_TYPES if dt != self.device.device_type
        ]

        last_exc: Exception | None = None
        try:
            for dtype in device_types_to_try:
                try:
                    logger.debug(
                        "%s: attempting Ruckus wireless connection with device_type=%r",
                        self.device.hostname,
                        dtype,
                    )
                    self.connection = ConnectHandler(
                        device_type=dtype,
                        host=self.device.ip_address,
                        port=self.device.ssh_port,
                        username=self.device.username,
                        password=plaintext_password,
                        timeout=self._settings.ssh_timeout,
                        session_log=None,
                        global_delay_factor=2,
                    )
                    logger.info(
                        "%s: Ruckus wireless connected with device_type=%r "
                        "(⚠️ unconfirmed device_type — validate against hardware)",
                        self.device.hostname,
                        dtype,
                    )
                    return  # Success — exit before del to ensure cleanup in finally
                except NetmikoTimeoutException:
                    raise  # Device unreachable; no point trying other device_types
                except Exception as exc:
                    logger.debug(
                        "%s: device_type=%r failed (%s: %s) — trying next fallback",
                        self.device.hostname,
                        dtype,
                        type(exc).__name__,
                        exc,
                    )
                    last_exc = exc
                    continue
        finally:
            del plaintext_password  # Always wipe plaintext from scope

        if last_exc:
            raise last_exc  # All device_types exhausted

    def get_serial_number(self) -> str | None:
        """Extract serial number from 'show version'."""
        output = self.connection.send_command("show version")
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Ruckus wireless serial from 'show version'. Excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        """Extract firmware version from 'show version'."""
        output = self.connection.send_command("show version")
        match = _FIRMWARE_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Ruckus wireless firmware from 'show version'. Excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None
