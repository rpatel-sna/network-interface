"""Ruckus ICX / FastIron collector.

Registered device_type values: ruckus_fastiron

SSH commands:
  - Serial:   show version → "Serial  #: <value>"
  - Firmware: show version → "SW: Version <value>"
Both values come from a single command; output is cached to avoid a second round-trip.
"""
from __future__ import annotations

import logging
import re

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

_SERIAL_PATTERN = re.compile(r'Serial\s+#\s*:\s*(\S+)', re.IGNORECASE)
_FIRMWARE_PATTERN = re.compile(r'SW:\s+Version\s+(\S+)', re.IGNORECASE)


class RuckusICXCollector(BaseCollector):
    """Collector for Ruckus ICX / FastIron switches."""

    def _get_show_version(self) -> str:
        """Cache 'show version' output for a single SSH round-trip."""
        if not hasattr(self, '_show_version_output'):
            self._show_version_output = self.connection.send_command("show version")
        return self._show_version_output

    def get_serial_number(self) -> str | None:
        """Extract serial number from 'show version'."""
        output = self._get_show_version()
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Ruckus ICX serial from 'show version'. Excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        """Extract firmware version from 'show version'."""
        output = self._get_show_version()
        match = _FIRMWARE_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Ruckus ICX firmware from 'show version'. Excerpt: %r",
            self.device.hostname,
            output[:200],
        )
        return None
