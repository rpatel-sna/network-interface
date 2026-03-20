# Data Model: External MariaDB Device Source

**Feature**: 002-external-mariadb-device-source
**Date**: 2026-03-20

---

## Changed Entity: Device

**File**: `network_inventory/models/device.py`

```python
@dataclass
class Device:
    id: int           # Row identifier (from external query or synthetic)
    hostname: str     # Device hostname (defaults to ip_address if absent in external query)
    ip_address: str   # Primary unique key for deduplication — REQUIRED
    ssh_port: int     # SSH port (default: 22 if not in external query)
    username: str     # SSH username — REQUIRED, plaintext
    password: str     # SSH password — REQUIRED, plaintext (was bytes, Fernet-encrypted)
    device_type: str  # Netmiko device type string — REQUIRED
    enabled: bool     # Retained for compatibility with CollectionResult writes (always True)
```

**Changes from feature 001**:
- `password: bytes` → `password: str` — plaintext, no decryption needed
- `enabled` field retained for downstream compatibility; always `True` (filtering done by SQL)

---

## New Entity: ExternalDbConfig (via Settings)

New fields added to `network_inventory/config.py` `Settings` dataclass:

| Field | Env Var | Type | Required | Default |
|---|---|---|---|---|
| `ext_db_host` | `EXT_DB_HOST` | `str` | Yes | — |
| `ext_db_port` | `EXT_DB_PORT` | `int` | No | `3306` |
| `ext_db_user` | `EXT_DB_USER` | `str` | Yes | — |
| `ext_db_password` | `EXT_DB_PASSWORD` | `str` | Yes | — |
| `ext_db_name` | `EXT_DB_NAME` | `str` | Yes | — |
| `ext_db_query` | `EXT_DB_QUERY` | `str` | Yes | — |

**Removed from Settings**:
- `encryption_key_file` / `ENCRYPTION_KEY_FILE` — deleted entirely

---

## New Module: `network_inventory/db/external_source.py`

**Public interface**:

```python
def load_devices_from_external_db(app_settings: Settings) -> list[Device]:
    """Connect to the external MariaDB, execute the configured SQL query,
    validate and deduplicate rows, and return a list of Device instances.

    Exits with sys.exit(1) on connection failure (timeout: 5s) or query error.
    Skips rows missing required fields with a WARNING log.
    Deduplicates by ip_address; logs WARNING for each dropped duplicate.
    """
```

**Expected external query output columns** (operator maps via SQL aliases):

| Column | Required | Notes |
|---|---|---|
| `ip_address` | Yes | Used as deduplication key |
| `device_type` | Yes | Netmiko device type string |
| `username` | Yes | SSH username |
| `password` | Yes | SSH password, plaintext |
| `hostname` | No | Defaults to `ip_address` if absent |
| `ssh_port` | No | Defaults to `22` if absent |
| `id` | No | Synthetic auto-increment if absent |

---

## Removed: `utils/encryption.py`

The entire `network_inventory/utils/encryption.py` module is deleted. No replacement.

Removed symbols:
- `load_key(key_file: str) -> bytes`
- `decrypt_password(key: bytes, encrypted: bytes) -> str`
- `InvalidToken` (re-export from `cryptography.fernet`)

`cryptography` package remains in `requirements.txt` only if used elsewhere; otherwise remove.

---

## Unchanged: `CollectionResult`

No changes to `CollectionResult` dataclass — `device_id`, `status`, `serial_number`, `firmware_version`, `error_message`, `attempted_at`, `succeeded_at` all remain the same.

---

## Unchanged: Local DB Schema

The local MariaDB `device_inventory` table and `upsert_inventory_record()` are unchanged. The `devices` table is no longer read by this application (device list comes from external DB), but it may still exist in the local schema.
