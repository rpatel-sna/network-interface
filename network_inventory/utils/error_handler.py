"""Map Netmiko (and generic) exceptions to inventory status + error message."""
from __future__ import annotations

from typing import Literal

try:
    from netmiko.exceptions import (
        NetmikoAuthenticationException,
        NetmikoTimeoutException,
    )
except ImportError:
    # Allow import before netmiko is installed (e.g. during linting)
    NetmikoTimeoutException = TimeoutError  # type: ignore[misc,assignment]
    NetmikoAuthenticationException = PermissionError  # type: ignore[misc,assignment]

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
