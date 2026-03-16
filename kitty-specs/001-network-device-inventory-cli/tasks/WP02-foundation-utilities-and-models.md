---
work_package_id: WP02
title: Foundation Utilities & Models
lane: "planned"
dependencies:
- WP01
base_branch: 001-network-device-inventory-cli-WP01
base_commit: eca7140efd847a0ddb947a2d2f5386076aef9fbd
created_at: '2026-03-12T15:00:53.868917+00:00'
subtasks:
- T004
- T005
- T006
- T007
phase: Phase 0 - Foundation
assignee: ''
agent: "claude-sonnet-4-6"
shell_pid: "19430"
review_status: "has_feedback"
reviewed_by: "rpatel-hk"
review_feedback_file: "/private/var/folders/9q/_tbpgj3j6k5b3_6wcw8y8rpw0000gp/T/spec-kitty-review-feedback-WP02.md"
history:
- timestamp: '2026-03-12T10:45:33Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-006
- FR-007
- FR-009
- FR-010
- FR-012
---

# Work Package Prompt: WP02 – Foundation Utilities & Models

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status` above. If `has_feedback`, read the Review Feedback section first.
- Address all feedback before marking complete.

---

## Review Feedback

**Reviewed by**: rpatel-hk
**Status**: ❌ Changes Requested
**Date**: 2026-03-16
**Feedback file**: `/private/var/folders/9q/_tbpgj3j6k5b3_6wcw8y8rpw0000gp/T/spec-kitty-review-feedback-WP02.md`

## Review Feedback

**Issue: `configure_logging()` ignores `settings` — uses hardcoded parameter defaults instead**

The spec requires `logger.py` to import `settings` at module level and call `settings.log_file` / `settings.log_level` inside `configure_logging()` (no parameters):

```python
# Spec (required):
from network_inventory.config import settings

def configure_logging() -> None:
    ...
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    file_handler = RotatingFileHandler(settings.log_file, ...)
```

The implementation instead defines:

```python
# Implementation (incorrect):
def configure_logging(log_file: str = "inventory.log", log_level: str = "INFO") -> None:
```

**Why this matters**: Any caller that does `configure_logging()` with no arguments will silently use the hardcoded defaults `"inventory.log"` / `"INFO"` — completely bypassing whatever the operator set in `.env` (`LOG_FILE`, `LOG_LEVEL`). The spec's design intent is that the logger automatically picks up the configured values without the caller needing to pass them.

**Fix**: Match the spec's signature exactly:

```python
from network_inventory.config import settings

def configure_logging() -> None:
    """Set up root logger handlers. Call once at application startup."""
    global _configured
    if _configured:
        return
    _configured = True

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    file_handler = RotatingFileHandler(
        settings.log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root.addHandler(file_handler)
    root.addHandler(stdout_handler)
```

All other deliverables are correct:
- `device.py` — `Device` and `CollectionResult` match spec exactly, `password: bytes`
- `encryption.py` — `load_key()`, `decrypt_password()`, security warning, `InvalidToken` re-exported
- `error_handler.py` — all three classify branches correct, pre-install fallback stubs present
- `models/__init__.py` — exports both dataclasses


## Objectives & Success Criteria

- `Device` and `CollectionResult` dataclasses are importable and correctly typed.
- Encryption helper can load a Fernet key file and decrypt a test value (round-trip).
- Logger produces output to both file and stdout with the correct format.
- Error handler correctly classifies Netmiko exceptions to `'timeout'` or `'failed'` status.

**Done when**:
- `from network_inventory.models.device import Device, CollectionResult` succeeds.
- `from network_inventory.utils.encryption import load_key, decrypt_password` can encrypt + decrypt a test password without error.
- `from network_inventory.utils.logger import get_logger` returns a `logging.Logger` with two handlers.
- `from network_inventory.utils.error_handler import classify_exception` returns `('timeout', ...)` for a `NetmikoTimeoutException`.

## Context & Constraints

- **Data model**: `kitty-specs/001-network-device-inventory-cli/data-model.md`
- **Research**: `kitty-specs/001-network-device-inventory-cli/research.md` — Fernet pattern, logging format
- **Spec**: FR-006, FR-007, FR-009, FR-010, FR-012
- **Plan**: `kitty-specs/001-network-device-inventory-cli/plan.md` — all utilities in `network_inventory/utils/`, models in `network_inventory/models/`
- **Implement with**: `spec-kitty implement WP02 --base WP01`
- Decrypted passwords must **never** be logged or written to disk.

## Subtasks & Detailed Guidance

### Subtask T004 – Implement `network_inventory/models/device.py`

**Purpose**: Define the canonical in-process representations of a managed device and a poll result.

**Steps**:

1. Create `network_inventory/models/device.py`:

```python
"""Data models for network device polling."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class Device:
    """Represents a row from the `devices` table."""
    id: int
    hostname: str
    ip_address: str
    ssh_port: int
    username: str
    password: bytes          # Fernet-encrypted; decrypted only at SSH connection time
    device_type: str
    enabled: bool


@dataclass
class CollectionResult:
    """Transient result of one device poll — consumed when written to device_inventory."""
    device_id: int
    status: Literal['success', 'failed', 'timeout']
    attempted_at: datetime
    serial_number: str | None = None
    firmware_version: str | None = None
    error_message: str | None = None
    succeeded_at: datetime | None = None
```

**Notes**:
- `Device.password` is `bytes` — the raw `VARBINARY(512)` from the DB. It is NOT decrypted here.
- `CollectionResult.succeeded_at` is set to `datetime.utcnow()` by the collector only when `status == 'success'`.
- Both are plain dataclasses — no validation logic here (kept in DB/collector layers).

**Files**:
- `network_inventory/models/device.py`
- `network_inventory/models/__init__.py` — add `from .device import Device, CollectionResult`

**Validation**:
- [ ] `Device(id=1, hostname='sw1', ip_address='10.0.0.1', ssh_port=22, username='admin', password=b'enc', device_type='cisco_ios', enabled=True)` constructs without error.
- [ ] `CollectionResult(device_id=1, status='success', attempted_at=datetime.utcnow())` constructs without error.

---

### Subtask T005 – Implement `network_inventory/utils/encryption.py`

**Purpose**: Load the Fernet key from disk and decrypt device passwords in memory only — never expose plaintext elsewhere.

**Steps**:

1. Create `network_inventory/utils/encryption.py`:

```python
"""Fernet-based password decryption for device credentials."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def load_key(key_file_path: str) -> bytes:
    """Load and return the Fernet key from disk.

    Raises:
        FileNotFoundError: if the key file does not exist.
        PermissionError: if the key file is not readable.
        ValueError: if the key file content is not a valid Fernet key.
    """
    path = Path(key_file_path)
    if not path.exists():
        raise FileNotFoundError(f"Encryption key file not found: {key_file_path}")

    # Warn if world-readable (potential security misconfiguration)
    file_stat = path.stat()
    if file_stat.st_mode & stat.S_IROTH:
        import warnings
        warnings.warn(
            f"Key file {key_file_path} is world-readable. Restrict with: chmod 600 {key_file_path}",
            UserWarning,
            stacklevel=2,
        )

    key = path.read_bytes().strip()
    # Validate key is well-formed Fernet key (will raise if not)
    try:
        Fernet(key)
    except Exception as exc:
        raise ValueError(f"Invalid Fernet key in {key_file_path}: {exc}") from exc
    return key


def decrypt_password(key: bytes, encrypted_bytes: bytes) -> str:
    """Decrypt a Fernet-encrypted password and return plaintext string.

    Args:
        key: Raw Fernet key bytes (from load_key()).
        encrypted_bytes: Encrypted password bytes from the database.

    Returns:
        Decrypted plaintext password string.

    Raises:
        InvalidToken: if decryption fails (wrong key or corrupted ciphertext).
    """
    f = Fernet(key)
    return f.decrypt(encrypted_bytes).decode("utf-8")
```

**Security rules**:
- `decrypt_password()` must never be called outside of `BaseCollector.connect()` (in WP04).
- The return value must never be passed to any logging call.
- Do not cache the decrypted value between SSH sessions.

**Files**:
- `network_inventory/utils/encryption.py`

**Validation**:
- [ ] Round-trip test: `key = Fernet.generate_key(); enc = Fernet(key).encrypt(b"test"); assert decrypt_password(key, enc) == "test"`.
- [ ] Missing key file → `FileNotFoundError`.
- [ ] Corrupt key file → `ValueError`.
- [ ] Wrong key for ciphertext → `InvalidToken`.

---

### Subtask T006 – Implement `network_inventory/utils/logger.py`

**Purpose**: Configure the application-wide logger with both file rotation and stdout output so operators have real-time visibility and a persistent audit trail.

**Steps**:

1. Create `network_inventory/utils/logger.py`:

```python
"""Logging configuration: RotatingFileHandler + stdout."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from network_inventory.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

_configured = False


def configure_logging() -> None:
    """Set up root logger handlers. Call once at application startup."""
    global _configured
    if _configured:
        return
    _configured = True

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # File handler with rotation (10 MB per file, 5 backups)
    file_handler = RotatingFileHandler(
        settings.log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root.addHandler(file_handler)
    root.addHandler(stdout_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. configure_logging() must be called before use."""
    return logging.getLogger(name)
```

**Usage pattern** (in `main.py`):
```python
from network_inventory.utils.logger import configure_logging, get_logger
configure_logging()
logger = get_logger(__name__)
```

**Notes**:
- `configure_logging()` is idempotent (safe to call multiple times).
- Use `get_logger(__name__)` in every module — never `print()` for operational messages.
- Password strings must never be passed to any logger call at any level.

**Files**:
- `network_inventory/utils/logger.py`

**Validation**:
- [ ] After `configure_logging()`, `logging.getLogger().handlers` has exactly 2 handlers.
- [ ] Log file is created at `settings.log_file` path on first log call.
- [ ] `LOG_LEVEL=DEBUG` produces debug messages; `LOG_LEVEL=WARNING` suppresses INFO.

---

### Subtask T007 – Implement `network_inventory/utils/error_handler.py`

**Purpose**: Centralize exception-to-status mapping so the orchestrator and base collector don't contain scattered `except` branches.

**Steps**:

1. Create `network_inventory/utils/error_handler.py`:

```python
"""Map Netmiko (and generic) exceptions to inventory status + error message."""
from __future__ import annotations

from typing import Literal

try:
    from netmiko.exceptions import (
        NetmikoTimeoutException,
        NetmikoAuthenticationException,
    )
except ImportError:
    # Allow import before netmiko is installed (e.g. during linting)
    NetmikoTimeoutException = TimeoutError  # type: ignore[misc]
    NetmikoAuthenticationException = PermissionError  # type: ignore[misc]

StatusType = Literal['success', 'failed', 'timeout']


def classify_exception(exc: Exception) -> tuple[StatusType, str]:
    """Return (status, error_message) from an exception.

    Args:
        exc: Any exception raised during device polling.

    Returns:
        Tuple of status string and human-readable error message.
    """
    if isinstance(exc, NetmikoTimeoutException):
        return 'timeout', f"Connection timed out: {exc}"
    if isinstance(exc, NetmikoAuthenticationException):
        return 'failed', f"Authentication failed: {exc}"
    # All other exceptions → generic failure
    return 'failed', f"{type(exc).__name__}: {exc}"
```

**Notes**:
- The function returns a `tuple[status, message]` — callers destructure it.
- Output messages must be human-readable (FR-007, SC-003) — include exception type name.
- Raw device output that caused a parse failure should be appended by the caller, not here.

**Files**:
- `network_inventory/utils/error_handler.py`

**Validation**:
- [ ] `classify_exception(NetmikoTimeoutException("timeout"))` → `('timeout', 'Connection timed out: ...')`.
- [ ] `classify_exception(NetmikoAuthenticationException("auth"))` → `('failed', 'Authentication failed: ...')`.
- [ ] `classify_exception(ValueError("unexpected"))` → `('failed', 'ValueError: unexpected')`.

---

## Risks & Mitigations

- **Decrypted passwords in logs**: Enforce via code review — `decrypt_password()` result must never be passed to a logger. Add a comment in `encryption.py` reinforcing this.
- **Logger called before `configure_logging()`**: Individual module loggers work without configuration but output nothing until handlers are added. `configure_logging()` must be the first call in `main.py`.
- **World-readable key file**: `load_key()` emits a `UserWarning` — the operator sees it on first run without crashing the tool.

## Review Guidance

- Verify `Device.password` is typed as `bytes`, not `str`.
- Confirm `decrypt_password()` is not called in this WP (only defined here; called in WP04).
- Check that `configure_logging()` is idempotent (no duplicate handlers on repeated calls).
- Verify `classify_exception()` covers the three expected branches.
- Grep codebase for any `logger.debug(password)` or equivalent — must be absent.

## Activity Log

> **CRITICAL**: Append new entries at the END. Never prepend.

- 2026-03-12T10:45:33Z – system – lane=planned – Prompt created.
- 2026-03-12T15:00:54Z – claude-sonnet-4-6 – shell_pid=46671 – lane=doing – Assigned agent via workflow command
- 2026-03-12T15:06:42Z – claude-sonnet-4-6 – shell_pid=46671 – lane=for_review – T004-T007 complete: Device+CollectionResult dataclasses, load_key+decrypt_password (Fernet), configure_logging+get_logger (RotatingFileHandler+stdout), classify_exception (timeout/auth/generic)
- 2026-03-16T14:36:51Z – claude-sonnet-4-6 – shell_pid=19430 – lane=doing – Started review via workflow command
- 2026-03-16T14:38:32Z – claude-sonnet-4-6 – shell_pid=19430 – lane=planned – Moved to planned
