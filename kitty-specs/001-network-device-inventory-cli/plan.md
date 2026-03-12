# Implementation Plan: Network Device Inventory CLI

**Branch**: `master` | **Date**: 2026-03-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/001-network-device-inventory-cli/spec.md`

## Summary

On-demand Python 3.11+ CLI tool that queries MariaDB for enabled network devices, connects to each in parallel via SSH using Netmiko, collects serial numbers and firmware versions using device-type-specific commands, writes results back to MariaDB with success/failed/timeout status, and prints a completion summary. Supports Cisco (IOS, IOS-XE, NX-OS), HP ProCurve, Aruba ArubaOS-Switch, Ruckus ICX, and Ruckus wireless controllers in v1.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Netmiko (SSH sessions), mariadb (MariaDB connector), cryptography (Fernet encryption), python-dotenv (env config), concurrent.futures (stdlib thread pool)
**Storage**: MariaDB — `devices` table (input) and `device_inventory` table (output/results)
**Testing**: pytest — integration tests only; real devices and DB required; no mocked unit tests in v1
**Target Platform**: Linux/macOS server or workstation; plain venv; run via `python network_inventory/main.py`
**Project Type**: Single Python CLI project
**Performance Goals**: 50 devices complete within 5 minutes with default concurrency (10 workers, 30s SSH timeout)
**Constraints**: SSH timeout configurable (default: 30s); max workers configurable (default: 10); DB credentials and encryption key path via env vars only; DB population out of scope

## Constitution Check

- **Python 3.11+**: Compliant — matches constitution requirement
- **pytest**: Compliant — integration tests use pytest
- **FastAPI**: N/A — CLI tool, no HTTP layer; constitution's FastAPI standard does not apply here
- **Result**: No violations. No complexity justification required.

## Project Structure

### Documentation (this feature)

```
kitty-specs/001-network-device-inventory-cli/
├── plan.md              ← This file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── schema.sql       ← Phase 1 output (MariaDB DDL)
└── tasks.md             ← Phase 2 output (/spec-kitty.tasks — not created here)
```

### Source Code (repository root)

```
network_inventory/
├── main.py                    # Entry point and orchestration
├── config.py                  # Settings loaded from env / .env
├── db/
│   ├── __init__.py
│   ├── connection.py          # MariaDB connection pool
│   └── queries.py             # SQL read (devices) + upsert (device_inventory)
├── collectors/
│   ├── __init__.py            # device_type → collector class registry
│   ├── base_collector.py      # Abstract base: get_serial_number(), get_firmware_version()
│   ├── cisco_ios.py           # Cisco IOS / IOS-XE  (device_type: cisco_ios, cisco_xe)
│   ├── cisco_nxos.py          # Cisco NX-OS          (device_type: cisco_nxos)
│   ├── hp_procurve.py         # HP ProCurve          (device_type: hp_procurve)
│   ├── aruba.py               # Aruba ArubaOS-Switch (device_type: aruba_procurve)
│   ├── ruckus_icx.py          # Ruckus ICX / FastIron (device_type: ruckus_fastiron)
│   └── ruckus_wireless.py     # Ruckus wireless controllers (see research.md caveat)
├── models/
│   ├── __init__.py
│   └── device.py              # Device + CollectionResult dataclasses
├── utils/
│   ├── __init__.py
│   ├── logger.py              # RotatingFileHandler + stdout, LOG_FILE / LOG_LEVEL env vars
│   ├── encryption.py          # Fernet key file load + decrypt helper
│   └── error_handler.py       # Exception → status classification
├── .env.example               # Template: all required env vars documented
└── requirements.txt

tests/
└── integration/
    ├── test_full_run.py       # End-to-end: DB query → SSH poll → DB write + summary
    ├── test_collectors.py     # Per-collector: real device SSH + command output parsing
    └── test_db.py             # DB: upsert correctness, connection failure at startup
```

**Structure Decision**: Single project layout. `network_inventory/` is the application package; `tests/` lives at repo root for pytest auto-discovery. No web frontend, no service split, no build tooling.

## Complexity Tracking

No constitution violations detected. No complexity justification required.
