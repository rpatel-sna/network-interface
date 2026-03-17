"""Aruba ArubaOS-Switch collector.

Registered device_type values: aruba_procurve

SSH commands:
  - Serial:   show system information → "Serial Number : <value>"
  - Firmware: show version            → firmware version line

Note: HP and Aruba are implemented as separate collectors per spec clarification.
If integration testing confirms identical output, consolidation is a follow-up task.
"""
from __future__ import annotations

import logging
import re

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

_SERIAL_PATTERN = re.compile(r'Serial\s+Number\s*:\s*(\S+)', re.IGNORECASE)
# Primary: explicit "Firmware Version" label
_FIRMWARE_PATTERN = re.compile(r'[Ff]irmware\s+[Vv]ersion\s*:\s*(\S+)', re.IGNORECASE)
# Fallback: any "Version X.Y" (covers ArubaOS-Switch variants)
_FIRMWARE_FALLBACK = re.compile(r'\bVersion\s+([\d.]+\S*)', re.MULTILINE | re.IGNORECASE)


class ArubaCollector(BaseCollector):
    """Collector for Aruba ArubaOS-Switch devices."""

    def get_serial_number(self) -> str | None:
        """Extract serial number from 'show system information'."""
        output = self.connection.send_command("show system information")
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Aruba serial from 'show system information'. Excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        """Extract firmware version from 'show version'."""
        output = self.connection.send_command("show version")
        match = _FIRMWARE_PATTERN.search(output)
        if not match:
            match = _FIRMWARE_FALLBACK.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Aruba firmware from 'show version'. Excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None
