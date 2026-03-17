---
work_package_id: WP04
title: Collector Architecture
lane: "done"
dependencies:
- WP01
base_branch: 001-network-device-inventory-cli-WP01
base_commit: eca7140efd847a0ddb947a2d2f5386076aef9fbd
created_at: '2026-03-13T01:04:21.864404+00:00'
subtasks:
- T011
- T012
phase: Phase 0 - Foundation
assignee: ''
agent: "claude-sonnet-4-6"
shell_pid: "34522"
review_status: "has_feedback"
reviewed_by: "rpatel-hk"
review_feedback_file: "/private/var/folders/9q/_tbpgj3j6k5b3_6wcw8y8rpw0000gp/T/spec-kitty-review-feedback-WP04.md"
history:
- timestamp: '2026-03-12T10:45:33Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-003
- FR-004
- FR-006
- FR-007
- FR-014
---

# Work Package Prompt: WP04 – Collector Architecture

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status` above. If `has_feedback`, read the Review Feedback section first.

---

## Review Feedback

**Reviewed by**: rpatel-hk
**Status**: ❌ Changes Requested
**Date**: 2026-03-16
**Feedback file**: `/private/var/folders/9q/_tbpgj3j6k5b3_6wcw8y8rpw0000gp/T/spec-kitty-review-feedback-WP04.md`

## Review Feedback

**Issue: WP04 imports from WP02 modules but is not stacked on WP02**

`network_inventory/collectors/base_collector.py` imports:
```python
from network_inventory.models.device import CollectionResult, Device      # WP02
from network_inventory.utils.encryption import decrypt_password            # WP02
from network_inventory.utils.error_handler import classify_exception       # WP02
```

None of these files exist in the WP04 worktree (`models/device.py`, `utils/encryption.py`, `utils/error_handler.py` are all missing). The branch is stacked only on WP01, so WP02 deliverables are absent.

**Fix**: Rebase the WP04 branch onto WP02 (which is `done`):

```bash
cd .worktrees/001-network-device-inventory-cli-WP04
git rebase 001-network-device-inventory-cli-WP02
```

No code changes are needed — the implementation is correct and matches the spec.

**All other deliverables are correct:**
- `base_collector.py` — `del plaintext_password` immediately after `ConnectHandler()`, `session_log=None`, `finally: self._disconnect()`, abstract methods enforced via ABC, `collect()` template method returns `CollectionResult` and never raises
- `collectors/__init__.py` — `COLLECTOR_REGISTRY` dict, `get_collector()` with `WARNING` on unknown type, `try/except ImportError` wrappers for WP05/WP06 modules, `__all__` correct


## Objectives & Success Criteria

- `BaseCollector` defines the SSH connection + collect() template method that all concrete collectors inherit.
- Adding a new device type requires exactly one new file + one registry entry — no other changes (FR-014, SC-004).
- `get_collector('unknown_type')` returns `None` and logs a `WARNING`.
- `get_collector('cisco_ios')` returns the `CiscoIOSCollector` class once WP05 is merged.

**Done when**:
- `from network_inventory.collectors.base_collector import BaseCollector` succeeds.
- Concrete subclass can implement `get_serial_number()` and `get_firmware_version()` and inherit working SSH + error handling from `collect()`.
- `COLLECTOR_REGISTRY` in `__init__.py` is populated by individual collector modules (WP05, WP06) — registry itself contains zero entries until those WPs are complete.

## Context & Constraints

- **Spec**: FR-003, FR-004, FR-006, FR-007, FR-014
- **Research**: `kitty-specs/001-network-device-inventory-cli/research.md` — Netmiko device_type identifiers, SSH pattern
- **Plan**: `kitty-specs/001-network-device-inventory-cli/plan.md` — collector module list
- **Implement with**: `spec-kitty implement WP04 --base WP01`
- `Device`, `CollectionResult` from WP02. `Settings` from WP01. `decrypt_password`, `classify_exception` from WP02.
- SSH connections must be closed in `finally` blocks to prevent leaks.
- `device_type` passed to Netmiko `ConnectHandler` comes from `Device.device_type`.

## Subtasks & Detailed Guidance

### Subtask T011 – Implement `network_inventory/collectors/base_collector.py`

**Purpose**: Abstract base class that handles SSH connection lifecycle, exception classification, and the collect() template method. Individual collectors only implement parsing logic.

**Steps**:

1. Create `network_inventory/collectors/base_collector.py`:

```python
"""Abstract base collector — SSH connection + collect() template method."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from network_inventory.config import Settings, settings as default_settings
from network_inventory.models.device import CollectionResult, Device
from network_inventory.utils.encryption import decrypt_password, load_key
from network_inventory.utils.error_handler import classify_exception

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Subclass this to implement a new device type collector.

    Subclasses must implement:
        get_serial_number(self) -> str | None
        get_firmware_version(self) -> str | None

    The SSH connection is available as self.connection during those calls.
    """

    def __init__(self, device: Device, key: bytes, app_settings: Settings | None = None) -> None:
        self.device = device
        self._key = key                              # Fernet key bytes
        self._settings = app_settings or default_settings
        self.connection: ConnectHandler | None = None

    def _connect(self) -> None:
        """Open an SSH session to the device. Sets self.connection."""
        plaintext_password = decrypt_password(self._key, self.device.password)
        try:
            self.connection = ConnectHandler(
                device_type=self.device.device_type,
                host=self.device.ip_address,
                port=self.device.ssh_port,
                username=self.device.username,
                password=plaintext_password,
                timeout=self._settings.ssh_timeout,
                session_log=None,       # Never log session data (contains credentials)
                global_delay_factor=2,  # Slightly generous timing for slow devices
            )
        finally:
            # Wipe plaintext from local scope immediately
            del plaintext_password

    def _disconnect(self) -> None:
        """Close the SSH session if open."""
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception:
                pass  # Best-effort disconnect; do not mask original error
            self.connection = None

    @abstractmethod
    def get_serial_number(self) -> str | None:
        """Return the device serial number, or None if not parseable."""
        ...

    @abstractmethod
    def get_firmware_version(self) -> str | None:
        """Return the firmware/OS version string, or None if not parseable."""
        ...

    def collect(self) -> CollectionResult:
        """Template method: connect → collect data → disconnect → return result.

        Returns:
            CollectionResult with status 'success', 'failed', or 'timeout'.
        """
        attempted_at = datetime.now(timezone.utc).replace(tzinfo=None)  # UTC naive for MariaDB
        serial_number: str | None = None
        firmware_version: str | None = None

        try:
            self._connect()
            serial_number = self.get_serial_number()
            firmware_version = self.get_firmware_version()

            logger.info(
                "%s (%s) — polled successfully: serial=%r firmware=%r",
                self.device.hostname, self.device.ip_address, serial_number, firmware_version,
            )

            return CollectionResult(
                device_id=self.device.id,
                status='success',
                attempted_at=attempted_at,
                serial_number=serial_number,
                firmware_version=firmware_version,
                succeeded_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )

        except (NetmikoTimeoutException, NetmikoAuthenticationException, Exception) as exc:
            status, error_message = classify_exception(exc)
            logger.warning(
                "%s (%s) — %s: %s",
                self.device.hostname, self.device.ip_address, status, error_message,
            )
            return CollectionResult(
                device_id=self.device.id,
                status=status,
                attempted_at=attempted_at,
                error_message=error_message,
            )

        finally:
            self._disconnect()
```

**Critical requirements**:
- `del plaintext_password` immediately after `ConnectHandler()` call — plaintext lives in memory for the shortest possible time.
- `session_log=None` — Netmiko must not write session transcripts (they contain command output which may include sensitive data in some environments).
- `self._disconnect()` in `finally` ensures SSH sessions close even when exceptions occur.
- `datetime.now(timezone.utc).replace(tzinfo=None)` produces timezone-naive UTC datetimes compatible with MariaDB `DATETIME` columns.

**Files**:
- `network_inventory/collectors/base_collector.py`

**Validation**:
- [ ] Can subclass `BaseCollector`, implement the two abstract methods, and call `collect()` without error.
- [ ] Subclass fails to instantiate if abstract methods are not implemented (Python ABC enforcement).
- [ ] `collect()` returns a `CollectionResult` with `status='timeout'` when `NetmikoTimeoutException` is raised inside `get_serial_number()`.

---

### Subtask T012 – Implement `network_inventory/collectors/__init__.py`

**Purpose**: Provide the `COLLECTOR_REGISTRY` dict and `get_collector()` factory function so the orchestrator never has device-type-specific logic.

**Steps**:

1. Create `network_inventory/collectors/__init__.py`:

```python
"""Collector registry — maps device_type strings to BaseCollector subclasses.

To add a new device type:
1. Create network_inventory/collectors/<vendor_platform>.py
2. Subclass BaseCollector and implement get_serial_number() + get_firmware_version()
3. Import your class here and add it to COLLECTOR_REGISTRY
No other files require changes (FR-014).
"""
from __future__ import annotations

import logging

from network_inventory.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

# Registry populated by individual collector modules (WP05 + WP06 add entries here)
COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {}

# Individual collector imports — each module registers itself below:
# (populated by WP05 and WP06)
try:
    from network_inventory.collectors.cisco_ios import CiscoIOSCollector
    COLLECTOR_REGISTRY.update({"cisco_ios": CiscoIOSCollector, "cisco_xe": CiscoIOSCollector})
except ImportError:
    pass  # Not yet implemented

try:
    from network_inventory.collectors.cisco_nxos import CiscoNXOSCollector
    COLLECTOR_REGISTRY["cisco_nxos"] = CiscoNXOSCollector
except ImportError:
    pass

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
        Logs a WARNING on unknown types (SC-001 — no device silently dropped).
    """
    collector_class = COLLECTOR_REGISTRY.get(device_type)
    if collector_class is None:
        logger.warning(
            "Unknown device_type '%s' — no collector registered. Skipping device.",
            device_type,
        )
    return collector_class


__all__ = ["COLLECTOR_REGISTRY", "get_collector", "BaseCollector"]
```

**Design notes**:
- `try/except ImportError` wrapping each collector import allows the registry to work even if some collector modules don't exist yet (enables incremental development).
- Once WP05 and WP06 are complete, the `try/except` wrapping can be removed — the imports should always succeed.
- The comment block at the top of the file is the SC-004 / FR-014 documentation: one file, one registry entry.
- `COLLECTOR_REGISTRY` is a plain `dict` — intentionally not auto-discovered so the registry is explicit and auditable.

**Files**:
- `network_inventory/collectors/__init__.py`

**Validation**:
- [ ] `from network_inventory.collectors import get_collector` succeeds.
- [ ] `get_collector('unknown_xyz')` returns `None` and emits a `WARNING` log.
- [ ] After WP05 is merged: `get_collector('cisco_ios')` returns `CiscoIOSCollector`.
- [ ] `COLLECTOR_REGISTRY` is a `dict` with `type[BaseCollector]` values.

---

## Risks & Mitigations

- **Circular import**: `collectors/__init__.py` imports from `collectors/cisco_ios.py` etc. which import from `collectors/base_collector.py`. This is a standard Python pattern; `base_collector.py` must not import from `__init__.py` to avoid the cycle.
- **Netmiko `device_type` for Ruckus wireless is unconfirmed**: `BaseCollector._connect()` passes `self.device.device_type` directly to Netmiko. The Ruckus wireless collector (WP06) will override `_connect()` to try fallback `device_type` values — `BaseCollector` does not need to handle this.
- **Plaintext password lifetime**: Using `del plaintext_password` after `ConnectHandler()` removes the reference from local scope. Note that the string may still reside in memory until GC — this is acceptable for a CLI tool; production hardening (e.g. `ctypes.memset`) is out of scope for v1.

## Review Guidance

- Confirm `session_log=None` is set in `ConnectHandler` to prevent credential leakage.
- Verify `_disconnect()` is in a `finally` block in `collect()`.
- Check that `COLLECTOR_REGISTRY` is a plain `dict` (not auto-populated via `__subclasses__()` or similar magic that would make it non-auditable).
- Verify the comment in `__init__.py` accurately describes the "one file + one entry" extension protocol (FR-014).
- Run `from network_inventory.collectors import get_collector; print(get_collector('does_not_exist'))` → should return `None` with a WARNING log.

## Activity Log

> **CRITICAL**: Append new entries at the END. Never prepend.

- 2026-03-12T10:45:33Z – system – lane=planned – Prompt created.
- 2026-03-13T01:04:22Z – claude-sonnet-4-6 – shell_pid=57162 – lane=doing – Assigned agent via workflow command
- 2026-03-13T01:05:32Z – claude-sonnet-4-6 – shell_pid=57162 – lane=for_review – T011-T012 complete: BaseCollector abstract class (connect/collect/disconnect template, session_log=None, del plaintext_password), COLLECTOR_REGISTRY with try/except ImportError scaffolding for WP05+WP06, get_collector() with WARNING on unknown type
- 2026-03-16T15:20:52Z – claude-sonnet-4-6 – shell_pid=24218 – lane=doing – Started review via workflow command
- 2026-03-16T16:06:01Z – claude-sonnet-4-6 – shell_pid=24218 – lane=planned – Moved to planned
- 2026-03-16T18:50:59Z – claude-sonnet-4-6 – shell_pid=30553 – lane=doing – Started implementation via workflow command
- 2026-03-16T18:52:15Z – claude-sonnet-4-6 – shell_pid=30553 – lane=for_review – Ready for review: rebased onto WP02 so all WP02 imports (models.device, utils.encryption, utils.error_handler) are now in the stack
- 2026-03-16T19:42:53Z – claude-sonnet-4-6 – shell_pid=34522 – lane=doing – Started review via workflow command
- 2026-03-16T19:43:22Z – claude-sonnet-4-6 – shell_pid=34522 – lane=done – Review passed: BaseCollector with session_log=None, del plaintext_password, _disconnect() in finally, collect() never raises; COLLECTOR_REGISTRY with try/except ImportError scaffolding, get_collector() with WARNING on unknown type; FR-014 extension comment accurate; rebased correctly onto WP02
