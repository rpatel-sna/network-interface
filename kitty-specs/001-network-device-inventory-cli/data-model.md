# Data Model: Network Device Inventory CLI

**Date**: 2026-03-12
**Source**: spec.md + clarification session 2026-03-12

---

## Entities

### Device — `devices` table (input, read-only for this tool)

Represents a managed network device to be polled. This table is populated by the operator; the tool only reads from it.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | INT | PK, AUTO_INCREMENT | Unique device identifier |
| `hostname` | VARCHAR(255) | NOT NULL | Human-readable label or DNS hostname |
| `ip_address` | VARCHAR(45) | NOT NULL | Management IP (IPv4 or IPv6) |
| `ssh_port` | INT | NOT NULL, DEFAULT 22 | SSH port number |
| `username` | VARCHAR(255) | NOT NULL | SSH authentication username |
| `password` | VARBINARY(512) | NOT NULL | SSH password, Fernet-encrypted at rest |
| `device_type` | VARCHAR(64) | NOT NULL | Netmiko device_type (e.g. `cisco_ios`, `hp_procurve`) |
| `enabled` | TINYINT(1) | NOT NULL, DEFAULT 1 | 1 = poll on next run; 0 = skip |

**Identity**: `id` (primary key). No composite unique constraint enforced in v1.

**State**: `enabled` flag is the only lifecycle toggle. No other state transitions on this entity.

---

### Inventory Record — `device_inventory` table (output, upserted by this tool)

Captures the outcome of the **most recent** poll attempt for a device. One record per device — upserted on every run.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | INT | PK, AUTO_INCREMENT | Record identifier |
| `device_id` | INT | FK → devices.id, NOT NULL, UNIQUE | Reference to the polled device |
| `serial_number` | VARCHAR(255) | NULL | Collected serial number; null if parse failed or not reached |
| `firmware_version` | VARCHAR(255) | NULL | Collected firmware/OS version; null if parse failed |
| `last_success` | DATETIME | NULL | Timestamp of the last successful poll; null if never succeeded |
| `last_attempt` | DATETIME | NOT NULL | Timestamp of the most recent poll attempt (this run) |
| `status` | ENUM('success','failed','timeout') | NOT NULL | Result classification for this run |
| `error_message` | TEXT | NULL | Full error message or raw device output; null on success |

**Identity**: `device_id` is UNIQUE — at most one current record per device.

**Upsert key**: `device_id`. On conflict, all fields except `id` are overwritten with the latest run's values.

**History**: No historical records are retained. Each run overwrites the previous result for a given device.

---

### CollectionResult — in-memory only (not persisted)

Transient dataclass representing the outcome of a single device poll within the running process.

| Field | Type | Description |
|---|---|---|
| `device_id` | int | Reference to the polled Device |
| `serial_number` | str \| None | Parsed serial number |
| `firmware_version` | str \| None | Parsed firmware version |
| `status` | Literal['success', 'failed', 'timeout'] | Result classification |
| `error_message` | str \| None | Error detail or raw output if non-success |
| `attempted_at` | datetime | When the poll attempt began |
| `succeeded_at` | datetime \| None | When the poll succeeded; None if not success |

---

## Relationships

```
devices (1) ──────────────── (0..1) device_inventory
               device_id FK

Device (1) ──── (1) CollectionResult   [in-memory, per run]
```

- Each enabled `Device` produces exactly one `CollectionResult` per run
- Each `Device` has at most one `device_inventory` row (UNIQUE constraint on `device_id`)
- `CollectionResult` is transient and consumed when the DB write step runs

---

## Valid device_type Values (v1)

The `devices.device_type` field must match one of the following registered collector identifiers:

| device_type value | Maps to collector | Device family |
|---|---|---|
| `cisco_ios` | `cisco_ios.py` | Cisco IOS |
| `cisco_xe` | `cisco_ios.py` | Cisco IOS-XE |
| `cisco_nxos` | `cisco_nxos.py` | Cisco NX-OS |
| `hp_procurve` | `hp_procurve.py` | HP ProCurve |
| `aruba_procurve` | `aruba.py` | Aruba ArubaOS-Switch |
| `ruckus_fastiron` | `ruckus_icx.py` | Ruckus ICX switches |
| `ruckus_wireless` | `ruckus_wireless.py` | Ruckus wireless controllers |

Devices with an unrecognised `device_type` are skipped with a logged warning; no result record is written for them.
