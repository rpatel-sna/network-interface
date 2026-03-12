# Research: Network Device Inventory CLI

**Date**: 2026-03-12
**Phase**: 0 — Pre-implementation research

---

## Decision: MariaDB Python Connector

**Decision**: Use `mariadb` (official MariaDB Connector/Python)

**Rationale**: Native C library with PEP-249 compliance, best throughput (~15% over generic MySQL clients), and built-in connection pooling. First-party support from MariaDB Corporation.

**Alternatives considered**:
- `mysql-connector-python` (Oracle): Broad community support but third-party to MariaDB; acceptable fallback if C library installation is blocked
- `PyMySQL`: Pure Python, no C build step, but slower; use only if native connector cannot be installed on the target host

---

## Decision: Netmiko Device Type Identifiers

**Decision**: Use the following confirmed `device_type` strings for `ConnectHandler(device_type=...)`:

| Device Family | device_type |
|---|---|
| Cisco IOS | `cisco_ios` |
| Cisco IOS-XE | `cisco_xe` |
| Cisco NX-OS | `cisco_nxos` |
| HP ProCurve | `hp_procurve` |
| Aruba ArubaOS-Switch | `aruba_procurve` |
| Ruckus ICX (FastIron) | `ruckus_fastiron` |
| Ruckus wireless | See caveat below |

**Ruckus wireless caveat**: Ruckus ZoneDirector and SmartZone controllers do not have a confirmed standard Netmiko `device_type`. The `ruckus_wireless` collector will attempt connection using `linux` or `generic_termserver` as the device_type and issue `show version` in privileged mode. This must be validated against real hardware during integration testing. If the generic approach fails, a custom Netmiko subclass will be required.

**Source**: [Netmiko PLATFORMS.md](https://github.com/ktbyers/netmiko/blob/develop/PLATFORMS.md)

---

## Decision: SSH Commands per Device Family

| Device Family | Serial Number Command | Firmware Command | Parse Target |
|---|---|---|---|
| Cisco IOS / IOS-XE | `show inventory` | `show version` | "SN:" field; "Version" line |
| Cisco NX-OS | `show inventory` | `show version` | "serialnum" field; "NXOS:" version line |
| HP ProCurve | `show system information` | `show version` | "Serial Number" field; "Software revision" |
| Aruba ArubaOS-Switch | `show system information` | `show version` | "Serial Number" field; firmware line |
| Ruckus ICX | `show version` | `show version` | "Serial #" field; "SW: Version" field |
| Ruckus wireless | `show version` | `show version` | "Serial Number" field; "Version" field |

**Note**: All parsing uses line-by-line regex in v1. TextFSM/NTC templates may be added later but are not required. If a command returns unexpected output, the raw output is stored in `error_message` and status is set to `failed`.

---

## Decision: Password Encryption (Fernet)

**Decision**: Use `cryptography.fernet.Fernet` for symmetric encryption of device passwords at rest.

**Pattern**:
1. Encryption key stored in a binary key file on disk
2. Key file path configured via `ENCRYPTION_KEY_FILE` environment variable
3. At startup: validate key file exists and is readable; exit with error if absent
4. At connection time: load key → `Fernet(key).decrypt(encrypted_bytes)` → plaintext used in memory only
5. Plaintext never logged, never written back to disk

**Key generation** (one-time operator task, out of scope for this tool):
```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > /secure/path/inventory.key
```

**Alternatives considered**:
- AES-256-CBC via `cryptography.hazmat`: More control but lower-level and more error-prone for this use case
- HashiCorp Vault / AWS Secrets Manager: Stronger posture but adds external runtime dependency; deferred to a future enhancement

---

## Decision: Parallel Execution Pattern

**Decision**: `concurrent.futures.ThreadPoolExecutor` with `as_completed()` and a future-to-device mapping dict.

**Pattern**: Submit all enabled device jobs upfront, iterate `as_completed()`, catch exceptions per-future, write results incrementally to DB. Every future is accounted for — no device is silently dropped.

**Max workers default**: 10 (configurable via `MAX_THREADS` env var)

---

## Decision: Logging

**Decision**: Python `logging` stdlib with `RotatingFileHandler` (size-based rotation, 10 MB per file, 5 backups).

- Log to both file (`LOG_FILE` env var) and stdout
- `LOG_LEVEL` env var controls verbosity (default: INFO)
- Format: `%(asctime)s | %(levelname)s | %(name)s | %(message)s`
- Sensitive values (passwords, decrypted credentials) are never logged

---

## Open Item: Ruckus Wireless Validation

The Ruckus wireless collector device_type is unconfirmed. During integration testing, the team must:
1. Test `linux` and `generic_termserver` as fallback device_types
2. Confirm that `show version` (privileged mode) returns parseable serial and firmware output
3. If neither works, evaluate implementing a custom Netmiko subclass

This does not block development of other collectors but must be resolved before v1 sign-off.
