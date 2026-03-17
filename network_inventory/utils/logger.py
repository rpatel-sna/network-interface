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
