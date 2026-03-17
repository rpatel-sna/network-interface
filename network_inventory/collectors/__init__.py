"""Collector registry — maps device_type strings to BaseCollector subclasses.

To add a new device type (FR-014):
1. Create network_inventory/collectors/<vendor_platform>.py
2. Subclass BaseCollector and implement get_serial_number() + get_firmware_version()
3. Import your class here and add one entry to COLLECTOR_REGISTRY
No other files require changes.
"""
from __future__ import annotations

import logging

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

# Registry populated by individual collector modules (WP05 + WP06 add entries below)
COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {}

# --- Cisco (WP05) ---
try:
    from network_inventory.collectors.cisco_ios import CiscoIOSCollector
    COLLECTOR_REGISTRY.update({"cisco_ios": CiscoIOSCollector, "cisco_xe": CiscoIOSCollector})
except ImportError:
    pass

try:
    from network_inventory.collectors.cisco_nxos import CiscoNXOSCollector
    COLLECTOR_REGISTRY["cisco_nxos"] = CiscoNXOSCollector
except ImportError:
    pass

# --- HP / Aruba / Ruckus (WP06) ---
try:
    from network_inventory.collectors.hp_procurve import HPProCurveCollector
    COLLECTOR_REGISTRY["hp_procurve"] = HPProCurveCollector
except ImportError:
    pass

try:
    from network_inventory.collectors.aruba import ArubaCollector
    COLLECTOR_REGISTRY["aruba_procurve"] = ArubaCollector
except ImportError:
    pass

try:
    from network_inventory.collectors.ruckus_icx import RuckusICXCollector
    COLLECTOR_REGISTRY["ruckus_fastiron"] = RuckusICXCollector
except ImportError:
    pass

try:
    from network_inventory.collectors.ruckus_wireless import RuckusWirelessCollector
    COLLECTOR_REGISTRY["ruckus_wireless"] = RuckusWirelessCollector
except ImportError:
    pass


def get_collector(device_type: str) -> type[BaseCollector] | None:
    """Look up the collector class for a given device_type string.

    Args:
        device_type: Value from devices.device_type column.

    Returns:
        The collector class, or None if device_type is not registered.
        Logs a WARNING on unknown types so no device is silently dropped (SC-001).
    """
    collector_class = COLLECTOR_REGISTRY.get(device_type)
    if collector_class is None:
        logger.warning(
            "Unknown device_type '%s' — no collector registered. Skipping device.",
            device_type,
        )
    return collector_class


__all__ = ["COLLECTOR_REGISTRY", "get_collector", "BaseCollector"]
