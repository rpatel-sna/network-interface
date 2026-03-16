"""Cisco NX-OS collector.

Registered device_type values: cisco_nxos
NX-OS output format differs significantly from IOS/IOS-XE.

SSH commands:
  - Serial:   show inventory  → "serialnum : <value>"
  - Firmware: show version    → "NXOS: version <value>"
"""
from __future__ import annotations

import logging
import re

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

# NX-OS inventory uses "serialnum :" (note colon spacing varies)
_SERIAL_PATTERN = re.compile(r'serialnum\s*:\s*(\S+)', re.IGNORECASE)

# NX-OS version line: "  NXOS: version 9.3(10)"
_FIRMWARE_PATTERN = re.compile(r'NXOS:\s+version\s+(\S+)', re.IGNORECASE)


class CiscoNXOSCollector(BaseCollector):
    """Collector for Cisco NX-OS devices."""

    def get_serial_number(self) -> str | None:
        """Run 'show inventory' and extract the NX-OS chassis serial number."""
        output = self.connection.send_command("show inventory")
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse NX-OS serial from 'show inventory'. Output excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        """Run 'show version' and extract the NX-OS version string."""
        output = self.connection.send_command("show version")
        match = _FIRMWARE_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse NX-OS firmware from 'show version'. Output excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None
