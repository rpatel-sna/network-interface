---
work_package_id: WP06
title: HP, Aruba & Ruckus Collectors
lane: planned
dependencies:
- WP04
subtasks:
- T015
- T016
- T017
- T018
phase: Phase 1 - Collectors
assignee: ''
agent: ''
shell_pid: ''
review_status: ''
reviewed_by: ''
history:
- timestamp: '2026-03-12T10:45:33Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-003
- FR-004
---

# Work Package Prompt: WP06 – HP, Aruba & Ruckus Collectors

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status` above. If `has_feedback`, read the Review Feedback section first.

---

## Review Feedback

*[Empty initially.]*

---

## Objectives & Success Criteria

- `HPProCurveCollector`, `ArubaCollector`, `RuckusICXCollector`, and `RuckusWirelessCollector` are implemented and registered.
- All four collectors extract serial number and firmware version using the documented command patterns from `research.md`.
- `RuckusWirelessCollector` attempts `ruckus_wireless` device_type first; falls back gracefully on connection failure; logs the unconfirmed caveat.
- Unknown Ruckus wireless device_type → `status='failed'` with a descriptive error, not an uncaught exception.

**Done when**:
- `get_collector('hp_procurve')`, `get_collector('aruba_procurve')`, `get_collector('ruckus_fastiron')`, `get_collector('ruckus_wireless')` all return the correct class.
- Regex patterns extract correct values from documented sample output.

## Context & Constraints

- **Spec**: FR-003, FR-004
- **Research**: `kitty-specs/001-network-device-inventory-cli/research.md` — SSH commands + regex targets; Ruckus wireless open item documented
- **Implement with**: `spec-kitty implement WP06 --base WP04`
- T015, T016, T017 are fully independent — implement in parallel.
- T018 (Ruckus wireless) should be started after T017 to reference the Ruckus ICX pattern as a baseline.
- HP and Aruba use the same commands (`show system information`) with similar output — if integration tests confirm identical output, consolidation is a follow-up task (out of scope here).
- All collectors subclass `BaseCollector` from WP04.

## Subtasks & Detailed Guidance

### Subtask T015 – Implement `network_inventory/collectors/hp_procurve.py`

**Purpose**: Collect serial number and firmware version from HP ProCurve switches via `show system information`.

**Steps**:

1. Create `network_inventory/collectors/hp_procurve.py`:

```python
"""HP ProCurve collector.

Registered device_type values: hp_procurve
SSH commands:
  - Serial:   show system information → "Serial Number  : <value>"
  - Firmware: show system information → "Software revision : <value>"
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

    def get_serial_number(self) -> str | None:
        output = self.connection.send_command("show system information")
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse HP serial from 'show system information'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        output = self.connection.send_command("show system information")
        match = _FIRMWARE_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse HP firmware from 'show system information'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None
```

**Optimisation note**: Both methods run `show system information` separately. For a single-command device, consider caching the output on first call (`self._sys_info_output`) and reusing in the second call. This is optional for v1 but reduces round-trips.

**Sample matching output**:
```
  Serial Number      : SG12345678    ← match
  Software revision  : WB.16.10.0009 ← match
```

**Files**:
- `network_inventory/collectors/hp_procurve.py`

**Parallel?**: Yes — implement simultaneously with T016 and T017.

**Validation**:
- [ ] `_SERIAL_PATTERN.search("  Serial Number      : SG12345678").group(1)` == `"SG12345678"`.
- [ ] `_FIRMWARE_PATTERN.search("  Software revision  : WB.16.10.0009").group(1)` == `"WB.16.10.0009"`.
- [ ] `get_collector('hp_procurve')` returns `HPProCurveCollector`.

---

### Subtask T016 – Implement `network_inventory/collectors/aruba.py`

**Purpose**: Collect serial number and firmware version from Aruba ArubaOS-Switch devices via `show system information`.

**Steps**:

1. Create `network_inventory/collectors/aruba.py`:

```python
"""Aruba ArubaOS-Switch collector.

Registered device_type values: aruba_procurve
SSH commands:
  - Serial:   show system information → "Serial Number : <value>"
  - Firmware: show version → firmware line
"""
from __future__ import annotations

import logging
import re

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

_SERIAL_PATTERN = re.compile(r'Serial\s+Number\s*:\s*(\S+)', re.IGNORECASE)
# Aruba firmware: "Version" line in show version output
_FIRMWARE_PATTERN = re.compile(r'[Ff]irmware\s+[Vv]ersion\s*:\s*(\S+)', re.IGNORECASE)
_FIRMWARE_FALLBACK = re.compile(r'\bVersion\s+([\d.]+)', re.MULTILINE)


class ArubaCollector(BaseCollector):
    """Collector for Aruba ArubaOS-Switch devices."""

    def get_serial_number(self) -> str | None:
        output = self.connection.send_command("show system information")
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Aruba serial from 'show system information'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        output = self.connection.send_command("show version")
        match = _FIRMWARE_PATTERN.search(output)
        if not match:
            match = _FIRMWARE_FALLBACK.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Aruba firmware from 'show version'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None
```

**Notes**:
- Aruba serial pattern is similar to HP — both use `Serial Number :`. This is intentional; commands are confirmed separate per the spec clarification ("treat as separate collectors for now").
- Aruba firmware uses `show version` (not `show system information`) — consistent with most switch vendors.
- If integration testing reveals HP and Aruba output is identical, document in a follow-up issue and consolidate then.

**Files**:
- `network_inventory/collectors/aruba.py`

**Parallel?**: Yes — implement simultaneously with T015 and T017.

**Validation**:
- [ ] `_SERIAL_PATTERN.search("  Serial Number      : AABBCC112233").group(1)` == `"AABBCC112233"`.
- [ ] Firmware pattern matches `"Firmware Version : ArubaOS-Switch 16.11.0006"`.
- [ ] `get_collector('aruba_procurve')` returns `ArubaCollector`.

---

### Subtask T017 – Implement `network_inventory/collectors/ruckus_icx.py`

**Purpose**: Collect serial number and firmware version from Ruckus ICX (FastIron) switches using `show version`.

**Steps**:

1. Create `network_inventory/collectors/ruckus_icx.py`:

```python
"""Ruckus ICX / FastIron collector.

Registered device_type values: ruckus_fastiron
SSH commands:
  - Serial:   show version → "Serial  #: <value>" or "Serial #:<value>"
  - Firmware: show version → "SW: Version <value>"
Both values come from a single 'show version' call.
"""
from __future__ import annotations

import logging
import re

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

_SERIAL_PATTERN = re.compile(r'Serial\s+#\s*:\s*(\S+)', re.IGNORECASE)
_FIRMWARE_PATTERN = re.compile(r'SW:\s+Version\s+([\S]+)', re.IGNORECASE)


class RuckusICXCollector(BaseCollector):
    """Collector for Ruckus ICX / FastIron switches."""

    def _get_show_version(self) -> str:
        """Cache show version output for a single SSH round-trip."""
        if not hasattr(self, '_show_version_output'):
            self._show_version_output = self.connection.send_command("show version")
        return self._show_version_output

    def get_serial_number(self) -> str | None:
        output = self._get_show_version()
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Ruckus ICX serial from 'show version'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        output = self._get_show_version()
        match = _FIRMWARE_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Ruckus ICX firmware from 'show version'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None
```

**Note**: Both serial and firmware come from `show version`. The `_get_show_version()` cache pattern avoids sending the command twice over SSH.

**Sample matching output**:
```
  Serial  #: BCR3312L00T             ← match group(1) = "BCR3312L00T"
  SW: Version 08.0.92T213            ← match group(1) = "08.0.92T213"
```

**Files**:
- `network_inventory/collectors/ruckus_icx.py`

**Parallel?**: Yes — implement simultaneously with T015 and T016.

**Validation**:
- [ ] `_SERIAL_PATTERN.search("  Serial  #: BCR3312L00T").group(1)` == `"BCR3312L00T"`.
- [ ] `_FIRMWARE_PATTERN.search("  SW: Version 08.0.92T213").group(1)` == `"08.0.92T213"`.
- [ ] `get_collector('ruckus_fastiron')` returns `RuckusICXCollector`.
- [ ] `show version` is sent only once per `collect()` call (cache works).

---

### Subtask T018 – Implement `network_inventory/collectors/ruckus_wireless.py`

**Purpose**: Collect serial number and firmware version from Ruckus wireless controllers (ZoneDirector, SmartZone). The correct Netmiko `device_type` for these devices is unconfirmed — implement with a fallback strategy and document the open item.

**Steps**:

1. Create `network_inventory/collectors/ruckus_wireless.py`:

```python
"""Ruckus Wireless Controller collector.

Registered device_type values: ruckus_wireless

⚠️  OPEN ITEM (research.md): Ruckus wireless controllers do not have a confirmed
    Netmiko device_type. This collector tries:
    1. device_type from the DB field (e.g. 'ruckus_wireless' — may be unsupported)
    2. 'linux' (generic Linux-like SSH)
    3. 'generic_termserver' (last resort)
    If none work, a 'failed' result is returned with an explanatory error message.
    This must be validated against real hardware before v1 sign-off.

SSH commands:
  - Serial:   show version → "Serial Number : <value>"
  - Firmware: show version → "Version : <value>" or "Version <value>"
"""
from __future__ import annotations

import logging
import re

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from network_inventory.collectors.base_collector import BaseCollector
from network_inventory.utils.encryption import decrypt_password

logger = logging.getLogger(__name__)

_SERIAL_PATTERN = re.compile(r'Serial\s+Number\s*:\s*(\S+)', re.IGNORECASE)
_FIRMWARE_PATTERN = re.compile(r'Version\s*:\s*([\S]+)', re.IGNORECASE)

# Fallback device_type options in order of preference
_FALLBACK_DEVICE_TYPES = ['linux', 'generic_termserver']


class RuckusWirelessCollector(BaseCollector):
    """Collector for Ruckus wireless controllers.

    Overrides _connect() to attempt multiple Netmiko device_type values.
    """

    def _connect(self) -> None:
        """Attempt SSH with the configured device_type, then fallbacks."""
        plaintext_password = decrypt_password(self._key, self.device.password)
        device_types_to_try = [self.device.device_type] + [
            dt for dt in _FALLBACK_DEVICE_TYPES if dt != self.device.device_type
        ]

        last_exc: Exception | None = None
        for dtype in device_types_to_try:
            try:
                logger.debug(
                    "%s: attempting Ruckus wireless connection with device_type=%r",
                    self.device.hostname, dtype,
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
                    "%s: Ruckus wireless connected with device_type=%r (⚠️ unconfirmed — validate against hardware)",
                    self.device.hostname, dtype,
                )
                del plaintext_password
                return  # Success
            except NetmikoTimeoutException:
                del plaintext_password
                raise  # Timeout should not trigger fallback — device is unreachable
            except Exception as exc:
                logger.debug(
                    "%s: device_type=%r failed: %s — trying next fallback",
                    self.device.hostname, dtype, exc,
                )
                last_exc = exc
                continue

        del plaintext_password
        if last_exc:
            raise last_exc  # All device_types exhausted

    def get_serial_number(self) -> str | None:
        output = self.connection.send_command("show version")
        match = _SERIAL_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Ruckus wireless serial from 'show version'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        output = self.connection.send_command("show version")
        match = _FIRMWARE_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse Ruckus wireless firmware from 'show version'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None
```

**Open item handling**:
- A `NetmikoTimeoutException` (device unreachable) re-raises immediately — no fallback needed.
- `NetmikoAuthenticationException` or unsupported `device_type` errors trigger the next fallback.
- If all device_type options fail, the final exception propagates up to `BaseCollector.collect()` which returns `status='failed'`.
- Add a prominent `⚠️ OPEN ITEM` comment referencing `research.md` — this must be validated against real Ruckus hardware.

**Files**:
- `network_inventory/collectors/ruckus_wireless.py`

**Validation**:
- [ ] `get_collector('ruckus_wireless')` returns `RuckusWirelessCollector`.
- [ ] If all device_type fallbacks fail, `collect()` returns `status='failed'` with descriptive `error_message` (not an unhandled exception).
- [ ] `NetmikoTimeoutException` is re-raised immediately (not caught as a fallback).
- [ ] Regex patterns match the documented output format from `research.md`.

---

## Risks & Mitigations

- **Ruckus wireless open item**: This is the highest-risk collector. Mark integration tests for this collector with `@pytest.mark.xfail` until real hardware validation is complete. Do not block v1 sign-off on Ruckus wireless alone — escalate to team for hardware access.
- **HP / Aruba command similarity**: If `show system information` output is identical between HP and Aruba, document in a GitHub issue and consolidate in a follow-up PR. Do not premature-consolidate without confirming on real hardware.
- **Ruckus ICX `show version` caching**: The `_show_version_output` attribute is set on the collector instance — this is safe as each `collect()` call creates a new collector instance.
- **Multiple `show version` sends on wireless**: The wireless collector calls `show version` twice (once in `get_serial_number`, once in `get_firmware_version`). Add the same `_get_show_version()` caching pattern from the ICX collector if SSH round-trips are a concern.

## Review Guidance

- Verify all four `device_type` → class mappings are in `COLLECTOR_REGISTRY`.
- Confirm `RuckusWirelessCollector._connect()` re-raises `NetmikoTimeoutException` without trying fallbacks.
- Confirm plaintext password is always `del`-eted even when exceptions occur in `_connect()`.
- Check that the `⚠️ OPEN ITEM` docstring is present and references `research.md`.
- Validate HP and Aruba serial regex against sample output (not just that the pattern compiles).

## Activity Log

> **CRITICAL**: Append new entries at the END. Never prepend.

- 2026-03-12T10:45:33Z – system – lane=planned – Prompt created.
