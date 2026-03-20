"""Data models for network device polling."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class Device:
    """Represents a device record sourced from the external database."""

    id: int
    hostname: str
    ip_address: str
    ssh_port: int
    username: str
    password: str            # Plaintext SSH password from external device source
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
