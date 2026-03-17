"""HP ProCurve collector.

Registered device_type values: hp_procurve

SSH commands:
  - Serial:   show system information → "Serial Number      : <value>"
  - Firmware: show system information → "Software revision  : <value>"
Both values come from a single command; output is cached to avoid a second round-trip.
"""
from __future__ import annotations

import logging
import re

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

_SERIAL_PATTERN = re.compile(r'Serial\s+Number\s*:\s*(\S+)', re.IGNORECASE)
_FIRMWARE_PATTERN = re.compile(r'Software\s+[Rr]evision\s*:\s*(\S+)', re.IGNORECASE)


class HPProCurveCollector(BaseCollector):
    """Collector for HP ProCurve switches."""

    def _get_sys_info(self) -> str:
        """Cache 'show system information' output for a single SSH round-trip."""
        if not hasattr(self, '_sys_info_output'):
            self._sys_info_output = self.connection.send_command("show system information")
        return self._sys_info_output

    def get_serial_number(self) -> str | None:
        """Extract serial number from 'show system information'."""
        output = self._get_sys_info()
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse HP serial from 'show system information'. Excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        """Extract firmware version from 'show system information'."""
        output = self._get_sys_info()
        match = _FIRMWARE_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse HP firmware from 'show system information'. Excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None
