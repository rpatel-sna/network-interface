"""Per-collector integration tests (T026).

Structure:
- Parsing tests: validate regex against documented sample output (no SSH required).
- Registry tests: confirm all 7 device_types are registered after WP05+WP06 merge.
- Real-device tests: annotated @pytest.mark.real_device — skipped in CI.

Run without real devices (CI-safe):
    pytest tests/integration/test_collectors.py -v -m "not real_device"
"""
from __future__ import annotations

import pytest

from network_inventory.collectors import COLLECTOR_REGISTRY, get_collector
from network_inventory.collectors.cisco_ios import (
    CiscoIOSCollector,
    _FIRMWARE_FALLBACK,
    _FIRMWARE_PATTERN,
    _SERIAL_PATTERN,
)
from network_inventory.collectors.cisco_nxos import CiscoNXOSCollector
from network_inventory.collectors.hp_procurve import HPProCurveCollector
from network_inventory.collectors.aruba import ArubaCollector
from network_inventory.collectors.ruckus_icx import RuckusICXCollector
from network_inventory.collectors.ruckus_wireless import RuckusWirelessCollector


# ---------------------------------------------------------------------------
# Cisco IOS / IOS-XE parsing (sample output from research.md)
# ---------------------------------------------------------------------------

class TestCiscoIOSParsing:
    INVENTORY_OUTPUT = (
        'NAME: "Chassis", DESCR: "Cisco 2911 Chassis"\n'
        "PID: CISCO2911/K9   , VID: V06  , SN: FGL1234ABCD\n"
        'NAME: "module 0", DESCR: "C2911 Mother board"\n'
        "PID: CISCO2911/K9   , VID: V06  , SN: FGL5678XYZ\n"
    )
    VERSION_OUTPUT = (
        "Cisco IOS Software, Version 15.7(3)M8, RELEASE SOFTWARE (fc2)\n"
        "Technical Support: http://www.cisco.com/techsupport\n"
    )
    VERSION_XE_OUTPUT = (
        "Cisco IOS XE Software, Version 17.3.4a\n"
    )

    def test_serial_first_chassis_match(self):
        """First SN: match is the chassis (not a line card)."""
        m = _SERIAL_PATTERN.search(self.INVENTORY_OUTPUT)
        assert m and m.group(1) == "FGL1234ABCD"

    def test_firmware_ios(self):
        m = _FIRMWARE_PATTERN.search(self.VERSION_OUTPUT)
        assert m and m.group(1) == "15.7(3)M8"

    def test_firmware_ios_xe(self):
        m = _FIRMWARE_PATTERN.search(self.VERSION_XE_OUTPUT)
        assert m and m.group(1) == "17.3.4a"

    def test_firmware_fallback_pattern(self):
        output = "  Version 16.12.04a\n"
        m = _FIRMWARE_FALLBACK.search(output)
        assert m and m.group(1) == "16.12.04a"

    def test_no_serial_match_returns_none(self):
        assert _SERIAL_PATTERN.search("no serial number here") is None

    def test_no_firmware_match_returns_none(self):
        assert _FIRMWARE_PATTERN.search("no version string here") is None


# ---------------------------------------------------------------------------
# Cisco NX-OS parsing
# ---------------------------------------------------------------------------

class TestCiscoNXOSParsing:
    def test_serial_extraction(self):
        from network_inventory.collectors.cisco_nxos import _SERIAL_PATTERN
        m = _SERIAL_PATTERN.search("  serialnum : TME123456789")
        assert m and m.group(1) == "TME123456789"

    def test_serial_case_insensitive(self):
        from network_inventory.collectors.cisco_nxos import _SERIAL_PATTERN
        m = _SERIAL_PATTERN.search("  SerialNum : ABC987")
        assert m and m.group(1) == "ABC987"

    def test_firmware_extraction(self):
        from network_inventory.collectors.cisco_nxos import _FIRMWARE_PATTERN
        m = _FIRMWARE_PATTERN.search("  NXOS: version 9.3(10)")
        assert m and m.group(1) == "9.3(10)"

    def test_firmware_no_match(self):
        from network_inventory.collectors.cisco_nxos import _FIRMWARE_PATTERN
        assert _FIRMWARE_PATTERN.search("  NX-OS version 9.3") is None


# ---------------------------------------------------------------------------
# HP ProCurve parsing
# ---------------------------------------------------------------------------

class TestHPProCurveParsing:
    def test_serial_extraction(self):
        from network_inventory.collectors.hp_procurve import _SERIAL_PATTERN
        m = _SERIAL_PATTERN.search("  Serial Number      : SG12345678")
        assert m and m.group(1) == "SG12345678"

    def test_firmware_extraction(self):
        from network_inventory.collectors.hp_procurve import _FIRMWARE_PATTERN
        m = _FIRMWARE_PATTERN.search("  Software revision  : WB.16.10.0009")
        assert m and m.group(1) == "WB.16.10.0009"

    def test_firmware_alternate_casing(self):
        from network_inventory.collectors.hp_procurve import _FIRMWARE_PATTERN
        m = _FIRMWARE_PATTERN.search("  software Revision : WB.16.10.0009")
        assert m and m.group(1) == "WB.16.10.0009"


# ---------------------------------------------------------------------------
# Aruba parsing
# ---------------------------------------------------------------------------

class TestArubaParsing:
    def test_serial_extraction(self):
        from network_inventory.collectors.aruba import _SERIAL_PATTERN
        m = _SERIAL_PATTERN.search("  Serial Number      : AABBCC112233")
        assert m and m.group(1) == "AABBCC112233"

    def test_firmware_primary_pattern(self):
        from network_inventory.collectors.aruba import _FIRMWARE_PATTERN
        m = _FIRMWARE_PATTERN.search("  Firmware Version : ArubaOS-Switch 16.11.0006")
        assert m and m.group(1) == "ArubaOS-Switch"

    def test_firmware_fallback_pattern(self):
        from network_inventory.collectors.aruba import _FIRMWARE_FALLBACK
        m = _FIRMWARE_FALLBACK.search("  Version 16.11.0006\n")
        assert m and m.group(1) == "16.11.0006"


# ---------------------------------------------------------------------------
# Ruckus ICX parsing
# ---------------------------------------------------------------------------

class TestRuckusICXParsing:
    def test_serial_extraction(self):
        from network_inventory.collectors.ruckus_icx import _SERIAL_PATTERN
        m = _SERIAL_PATTERN.search("  Serial  #: BCR3312L00T")
        assert m and m.group(1) == "BCR3312L00T"

    def test_serial_compact_format(self):
        from network_inventory.collectors.ruckus_icx import _SERIAL_PATTERN
        m = _SERIAL_PATTERN.search("  Serial #: BCR3312L00T")
        assert m and m.group(1) == "BCR3312L00T"

    def test_firmware_extraction(self):
        from network_inventory.collectors.ruckus_icx import _FIRMWARE_PATTERN
        m = _FIRMWARE_PATTERN.search("  SW: Version 08.0.92T213")
        assert m and m.group(1) == "08.0.92T213"


# ---------------------------------------------------------------------------
# Ruckus wireless parsing
# ---------------------------------------------------------------------------

class TestRuckusWirelessParsing:
    def test_serial_extraction(self):
        from network_inventory.collectors.ruckus_wireless import _SERIAL_PATTERN
        m = _SERIAL_PATTERN.search("  Serial Number : RCK1234ABCD")
        assert m and m.group(1) == "RCK1234ABCD"

    def test_firmware_extraction(self):
        from network_inventory.collectors.ruckus_wireless import _FIRMWARE_PATTERN
        m = _FIRMWARE_PATTERN.search("  Version : 5.2.1.0.100")
        assert m and m.group(1) == "5.2.1.0.100"


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

class TestCollectorRegistry:
    EXPECTED_DEVICE_TYPES = {
        'cisco_ios', 'cisco_xe', 'cisco_nxos',
        'hp_procurve', 'aruba_procurve',
        'ruckus_fastiron', 'ruckus_wireless',
    }

    def test_all_device_types_registered(self):
        """All 7 device_type values from data-model.md are in COLLECTOR_REGISTRY."""
        missing = self.EXPECTED_DEVICE_TYPES - set(COLLECTOR_REGISTRY.keys())
        assert not missing, f"Missing registry entries: {missing}"

    def test_cisco_ios_and_xe_share_class(self):
        """cisco_ios and cisco_xe map to the same CiscoIOSCollector class."""
        assert get_collector('cisco_ios') is get_collector('cisco_xe')
        assert get_collector('cisco_ios') is CiscoIOSCollector

    def test_unknown_type_returns_none(self):
        """Unknown device_type returns None (and logs WARNING — not tested here)."""
        assert get_collector('does_not_exist') is None

    def test_registry_values_are_base_collector_subclasses(self):
        """Every registered class is a subclass of BaseCollector."""
        from network_inventory.collectors.base_collector import BaseCollector
        for dtype, cls in COLLECTOR_REGISTRY.items():
            assert issubclass(cls, BaseCollector), (
                f"COLLECTOR_REGISTRY['{dtype}'] = {cls} is not a BaseCollector subclass"
            )


# ---------------------------------------------------------------------------
# Real-device tests (skipped in CI — require live hardware)
# ---------------------------------------------------------------------------

@pytest.mark.real_device
class TestRealDeviceCiscoIOS:
    """Requires a live Cisco IOS device.
    Configure: TEST_CISCO_IOS_HOST, TEST_CISCO_IOS_USER, TEST_CISCO_IOS_PASS env vars.
    """

    @pytest.fixture
    def cisco_ios_device(self):
        import os
        from network_inventory.models.device import Device

        host = os.environ["TEST_CISCO_IOS_HOST"]
        user = os.environ.get("TEST_CISCO_IOS_USER", "admin")
        password = os.environ["TEST_CISCO_IOS_PASS"]

        return Device(
            id=99, hostname="test-cisco-ios", ip_address=host, ssh_port=22,
            username=user, password=password, device_type="cisco_ios", enabled=True,
        )

    def test_collect_returns_success(self, cisco_ios_device):
        collector = CiscoIOSCollector(device=cisco_ios_device)
        result = collector.collect()
        assert result.status == 'success'
        assert result.serial_number is not None
        assert result.firmware_version is not None


@pytest.mark.real_device
@pytest.mark.xfail(reason="Ruckus wireless device_type unconfirmed — see research.md open item")
class TestRealDeviceRuckusWireless:
    """Requires a live Ruckus wireless controller.
    Configure: TEST_RUCKUS_WIRELESS_HOST, TEST_RUCKUS_WIRELESS_USER, TEST_RUCKUS_WIRELESS_PASS
    """

    @pytest.fixture
    def ruckus_wireless_device(self):
        import os
        from network_inventory.models.device import Device

        host = os.environ["TEST_RUCKUS_WIRELESS_HOST"]
        user = os.environ.get("TEST_RUCKUS_WIRELESS_USER", "admin")
        password = os.environ["TEST_RUCKUS_WIRELESS_PASS"]

        return Device(
            id=98, hostname="test-ruckus-wireless", ip_address=host, ssh_port=22,
            username=user, password=password, device_type="ruckus_wireless", enabled=True,
        )

    def test_collect_does_not_raise(self, ruckus_wireless_device):
        """collect() returns a CollectionResult regardless of outcome — never raises."""
        collector = RuckusWirelessCollector(device=ruckus_wireless_device)
        result = collector.collect()
        assert result.status in ('success', 'failed', 'timeout')
        assert result.device_id == ruckus_wireless_device.id
