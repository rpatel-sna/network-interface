---
work_package_id: WP05
title: Cisco Collectors
lane: "doing"
dependencies:
- WP04
base_branch: 001-network-device-inventory-cli-WP04
base_commit: 17318a1ff61212e6950b85e0e3b1a947655fe75a
created_at: '2026-03-13T01:15:51.000557+00:00'
subtasks:
- T013
- T014
phase: Phase 1 - Collectors
assignee: ''
agent: "claude-sonnet-4-6"
shell_pid: "58642"
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

# Work Package Prompt: WP05 – Cisco Collectors

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status` above. If `has_feedback`, read the Review Feedback section first.

---

## Review Feedback

*[Empty initially.]*

---

## Objectives & Success Criteria

- `CiscoIOSCollector` extracts serial number from `show inventory` and firmware from `show version` for both IOS and IOS-XE device types.
- `CiscoNXOSCollector` extracts serial and firmware from NX-OS command output.
- Both collectors are registered in `COLLECTOR_REGISTRY` under the correct `device_type` keys.
- When a regex does not match, the collector returns `None` for that field (not an empty string) and logs at DEBUG level with an excerpt of raw output.

**Done when**:
- `get_collector('cisco_ios')` and `get_collector('cisco_xe')` both return `CiscoIOSCollector`.
- `get_collector('cisco_nxos')` returns `CiscoNXOSCollector`.
- Parsing functions return correct values for the documented sample output patterns from `research.md`.

## Context & Constraints

- **Spec**: FR-003, FR-004
- **Research**: `kitty-specs/001-network-device-inventory-cli/research.md` — SSH commands and regex targets per device family
- **Plan**: `kitty-specs/001-network-device-inventory-cli/plan.md`
- **Implement with**: `spec-kitty implement WP05 --base WP04`
- Both collectors subclass `BaseCollector` (WP04). Registry entries added in `collectors/__init__.py` (already scaffolded with `try/except ImportError` in WP04).
- Cisco IOS/IOS-XE share a collector class; `device_type` is passed to Netmiko from `self.device.device_type` (already handled by `BaseCollector._connect()`).
- All parsing uses line-by-line regex — no TextFSM in v1.

## Subtasks & Detailed Guidance

### Subtask T013 – Implement `network_inventory/collectors/cisco_ios.py`

**Purpose**: Collect serial number and firmware version from Cisco IOS and IOS-XE devices. One collector class handles both because the SSH commands and output format are identical.

**Steps**:

1. Create `network_inventory/collectors/cisco_ios.py`:

```python
"""Cisco IOS / IOS-XE collector.

Registered device_type values: cisco_ios, cisco_xe
SSH commands:
  - Serial:   show inventory  → match "SN: <value>" (first chassis entry)
  - Firmware: show version    → match "Version <version_string>"
"""
from __future__ import annotations

import logging
import re

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

# Patterns confirmed against Cisco IOS/IOS-XE output (research.md)
_SERIAL_PATTERN = re.compile(r'\bSN:\s*(\S+)', re.IGNORECASE)
_FIRMWARE_PATTERN = re.compile(
    r'(?:Cisco IOS Software|IOS-XE Software)[^\n]*Version\s+([\d.()A-Za-z]+)',
    re.IGNORECASE,
)
# Fallback firmware pattern (generic "Version X.Y" on the version line)
_FIRMWARE_FALLBACK = re.compile(r'^.*Version\s+([\d.()A-Za-z]+)', re.MULTILINE | re.IGNORECASE)


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
            self.device.hostname, output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        """Run 'show version' and extract the IOS/IOS-XE version string."""
        output = self.connection.send_command("show version")
        match = _FIRMWARE_PATTERN.search(output)
        if not match:
            # Try the generic fallback pattern (covers edge cases)
            match = _FIRMWARE_FALLBACK.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse firmware from 'show version'. Output excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None
```

**Regex details**:
- `SN:\s*(\S+)` — captures the value after `SN:` (the first match is the chassis; module entries follow).
- Primary firmware pattern anchors on the known IOS/IOS-XE preamble line to avoid matching unrelated "Version" strings.
- Fallback pattern is `re.MULTILINE` line-by-line to catch variants.
- Both patterns are case-insensitive (`re.IGNORECASE`).

**Sample matching output**:
```
# show inventory
NAME: "Chassis", DESCR: "Cisco 2911 Chassis"
PID: CISCO2911/K9   , VID: V06  , SN: FGL1234ABCD    ← match group(1) = "FGL1234ABCD"

# show version
Cisco IOS Software, Version 15.7(3)M8, RELEASE SOFTWARE
                                                ↑ match group(1) = "15.7(3)M8"
```

**Files**:
- `network_inventory/collectors/cisco_ios.py`

**Parallel?**: Yes — implement simultaneously with T014.

**Validation**:
- [ ] `_SERIAL_PATTERN.search("  SN: ABC12345").group(1)` == `"ABC12345"`.
- [ ] `_FIRMWARE_PATTERN.search("Cisco IOS Software, Version 15.7(3)M8, RELEASE SOFTWARE").group(1)` == `"15.7(3)M8"`.
- [ ] `_FIRMWARE_FALLBACK.search("... Version 17.3.4a ...").group(1)` == `"17.3.4a"`.
- [ ] No output match → returns `None`, logs DEBUG with output excerpt.
- [ ] `get_collector('cisco_ios')` returns `CiscoIOSCollector`.
- [ ] `get_collector('cisco_xe')` returns `CiscoIOSCollector`.

---

### Subtask T014 – Implement `network_inventory/collectors/cisco_nxos.py`

**Purpose**: Collect serial number and firmware version from Cisco NX-OS devices. NX-OS output format differs significantly from IOS/IOS-XE.

**Steps**:

1. Create `network_inventory/collectors/cisco_nxos.py`:

```python
"""Cisco NX-OS collector.

Registered device_type values: cisco_nxos
SSH commands:
  - Serial:   show inventory  → match "serialnum : <value>"
  - Firmware: show version    → match "NXOS: version <value>"
"""
from __future__ import annotations

import logging
import re

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

# NX-OS output patterns (research.md)
_SERIAL_PATTERN = re.compile(r'serialnum\s*:\s*(\S+)', re.IGNORECASE)
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
            "%s: could not parse NX-OS serial from 'show inventory'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None

    def get_firmware_version(self) -> str | None:
        """Run 'show version' and extract the NX-OS version string."""
        output = self.connection.send_command("show version")
        match = _FIRMWARE_PATTERN.search(output)
        if match:
            return match.group(1)
        logger.debug(
            "%s: could not parse NX-OS firmware from 'show version'. Excerpt: %r",
            self.device.hostname, output[:200],
        )
        return None
```

**Sample matching output**:
```
# show inventory
NAME: "Chassis",  DESCR: "Nexus7700 C7706 (6 Slot) Chassis"
  serialnum : TME123456789         ← match group(1) = "TME123456789"

# show version
  NXOS: version 9.3(10)           ← match group(1) = "9.3(10)"
```

**Files**:
- `network_inventory/collectors/cisco_nxos.py`

**Parallel?**: Yes — implement simultaneously with T013.

**Validation**:
- [ ] `_SERIAL_PATTERN.search("  serialnum : TME123456789").group(1)` == `"TME123456789"`.
- [ ] `_FIRMWARE_PATTERN.search("  NXOS: version 9.3(10)").group(1)` == `"9.3(10)"`.
- [ ] No match → returns `None`, logs DEBUG.
- [ ] `get_collector('cisco_nxos')` returns `CiscoNXOSCollector`.

---

## Risks & Mitigations

- **Modular chassis (Cisco 6500, 7K)**: `show inventory` may contain many `SN:` entries for line cards. The first match is correct for chassis-level serial — explicitly documented in regex comments.
- **IOS vs IOS-XE version line wording**: The primary pattern covers both; the fallback pattern catches any remaining edge cases. Log the raw output at DEBUG if neither matches, so the operator can update the regex.
- **`show inventory` not supported on some old IOS**: If the command returns `% Invalid input detected`, Netmiko will return that string; `_SERIAL_PATTERN` won't match → `None` is returned and the partial record is written (serial=null, firmware from `show version` may still succeed).

## Review Guidance

- Verify all three `device_type` → class mappings are present in `COLLECTOR_REGISTRY` after WP05 is merged.
- Test each regex against the documented sample output from `research.md` before real device testing.
- Confirm that a parse failure (no regex match) results in `None` return + DEBUG log, not an exception.
- Confirm `get_collector('cisco_xe')` returns the IOS class (shared collector).

## Activity Log

> **CRITICAL**: Append new entries at the END. Never prepend.

- 2026-03-12T10:45:33Z – system – lane=planned – Prompt created.
- 2026-03-13T01:15:51Z – claude-sonnet-4-6 – shell_pid=58642 – lane=doing – Assigned agent via workflow command
