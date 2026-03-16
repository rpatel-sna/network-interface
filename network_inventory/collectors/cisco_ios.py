"""Cisco IOS / IOS-XE collector.

Registered device_type values: cisco_ios, cisco_xe
Both IOS and IOS-XE share this collector — commands and output format are identical.

SSH commands:
  - Serial:   show inventory  → first "SN: <value>" match (chassis entry)
  - Firmware: show version    → "Version <version>" on IOS/IOS-XE preamble line
"""
from __future__ import annotations

import logging
import re

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

# First SN: match = chassis serial; subsequent matches are line cards / modules
_SERIAL_PATTERN = re.compile(r'\bSN:\s*(\S+)', re.IGNORECASE)

# Primary: anchored to known IOS/IOS-XE version line preamble
_FIRMWARE_PATTERN = re.compile(
    r'(?:Cisco IOS Software|IOS-XE Software)[^\n]*Version\s+([\d.()\w]+)',
    re.IGNORECASE,
)
# Fallback: any "Version X.Y" on a line (covers edge-case IOS variants)
_FIRMWARE_FALLBACK = re.compile(r'\bVersion\s+([\d.()\w]+)', re.MULTILINE | re.IGNORECASE)


class CiscoIOSCollector(BaseCollector):
    """Collector for Cisco IOS and IOS-XE devices."""

    def get_serial_number(self) -> str | None:
        """Run 'show inventory' and extract the chassis serial number."""
        output = self.connection.send_command("show inventory")
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse serial from 'show inventory'. Output excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        """Run 'show version' and extract the IOS/IOS-XE version string."""
        output = self.connection.send_command("show version")
        match = _FIRMWARE_PATTERN.search(output)
        if not match:
            match = _FIRMWARE_FALLBACK.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse firmware from 'show version'. Output excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None
