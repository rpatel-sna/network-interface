"""Database layer public API."""
from .connection import get_connection, get_pool
from .external_source import load_devices_from_external_db
from .queries import upsert_inventory_record

__all__ = [
    "get_connection",
    "get_pool",
    "load_devices_from_external_db",
    "upsert_inventory_record",
]
