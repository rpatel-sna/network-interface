# Network Device Inventory CLI — User Guide

A CLI tool that SSH-polls network devices and writes serial numbers, firmware versions, and poll status to a MariaDB database.

---

## Prerequisites

- Python 3.11+
- MariaDB 10.6+ accessible from the host running the tool
- SSH reachable on all target devices (port 22 by default)

---

## 1. Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Dependencies installed:**

| Package | Version | Purpose |
|---|---|---|
| `netmiko` | ≥4.3,<5.0 | SSH device automation |
| `mariadb` | ≥1.1,<2.0 | MariaDB connector |
| `cryptography` | ≥42.0,<44.0 | Fernet password encryption |
| `python-dotenv` | ≥1.0,<2.0 | `.env` file loading |

---

## 2. Create the database schema

Apply the schema to your MariaDB instance:

```bash
mysql -u root -p <your_database> < kitty-specs/001-network-device-inventory-cli/contracts/schema.sql
```

This creates two tables:

**`devices`** — operator-managed input (tool reads only)

| Column | Type | Description |
|---|---|---|
| `id` | INT AUTO_INCREMENT | Primary key |
| `hostname` | VARCHAR(255) | Human-readable label or DNS name |
| `ip_address` | VARCHAR(45) | Management IP (IPv4 or IPv6) |
| `ssh_port` | INT DEFAULT 22 | SSH port |
| `username` | VARCHAR(255) | SSH username |
| `password` | VARBINARY(512) | **Fernet-encrypted** SSH password |
| `device_type` | VARCHAR(64) | Netmiko device type string (see [Supported device types](#supported-device-types)) |
| `enabled` | TINYINT(1) DEFAULT 1 | `1` = poll on next run, `0` = skip |

**`device_inventory`** — tool-managed output (one row per device, upserted each run)

| Column | Type | Description |
|---|---|---|
| `device_id` | INT UNIQUE | FK to `devices.id` |
| `serial_number` | VARCHAR(255) NULL | Collected serial, or NULL if not parsed |
| `firmware_version` | VARCHAR(255) NULL | Collected firmware/OS version, or NULL |
| `last_success` | DATETIME NULL | Timestamp of last successful poll |
| `last_attempt` | DATETIME | Timestamp of most recent poll attempt |
| `status` | ENUM | `success`, `failed`, or `timeout` |
| `error_message` | TEXT NULL | Error detail on non-success; NULL on success |

> `last_success` is **never overwritten** by a failed or timed-out poll — it always reflects the most recent successful run.

Create a minimal-privilege DB user for the tool:

```sql
CREATE USER 'inventory_user'@'%' IDENTIFIED BY 'strong_password';
GRANT SELECT ON your_database.devices TO 'inventory_user'@'%';
GRANT INSERT, UPDATE ON your_database.device_inventory TO 'inventory_user'@'%';
FLUSH PRIVILEGES;
```

---

## 3. Generate the encryption key

Device passwords are stored Fernet-encrypted in the database. Generate a key once and keep it safe:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
    > /secure/path/inventory.key
chmod 600 /secure/path/inventory.key
```

> **Back this file up.** If it is lost, the encrypted passwords in the `devices` table cannot be recovered.

---

## 4. Configure environment variables

```bash
cp network_inventory/.env.example .env
# Edit .env with your values
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_HOST` | Yes | — | MariaDB hostname or IP |
| `DB_PORT` | No | `3306` | MariaDB port |
| `DB_USER` | Yes | — | MariaDB username |
| `DB_PASSWORD` | Yes | — | MariaDB password |
| `DB_NAME` | Yes | — | Database name |
| `ENCRYPTION_KEY_FILE` | Yes | — | Absolute path to the Fernet key file |
| `MAX_THREADS` | No | `10` | Max parallel SSH workers |
| `SSH_TIMEOUT` | No | `30` | SSH connection timeout (seconds) |
| `LOG_FILE` | No | `inventory.log` | Log output file path |
| `LOG_LEVEL` | No | `INFO` | Log verbosity: `DEBUG`, `INFO`, or `WARNING` |

The tool validates all required variables at startup and exits with a descriptive error if any are missing.

---

## 5. Add devices to the database

Passwords must be encrypted before inserting. Use this helper:

```python
from cryptography.fernet import Fernet

key = open('/secure/path/inventory.key', 'rb').read().strip()
f = Fernet(key)
encrypted = f.encrypt(b"my_device_password")
print(encrypted.decode())   # paste this into devices.password
```

Then insert a device:

```sql
INSERT INTO devices (hostname, ip_address, ssh_port, username, password, device_type, enabled)
VALUES ('core-sw-01', '10.0.0.1', 22, 'admin', '<encrypted_value>', 'cisco_ios', 1);
```

See [Supported device types](#supported-device-types) for valid `device_type` values.

---

## 6. Run the tool

```bash
source .venv/bin/activate
python network_inventory/main.py
```

The tool runs non-interactively and exits when all devices have been polled. On completion:

```
Inventory run complete.
  Total polled : 12
  Success      : 10
  Failed       : 1
  Timeout      : 1
```

Results are written to the `device_inventory` table. Each device produces exactly one row, updated on every run.

### Exit codes

| Code | Cause |
|---|---|
| `0` | Normal completion (including zero enabled devices) |
| `1` | Missing/invalid env var, unreadable key file, or DB connection failure at startup |

### Startup validation sequence

The tool fails fast and exits 1 before polling any device if:

1. A required env var is missing — error printed to stderr naming the variable
2. The key file does not exist, is unreadable, or contains an invalid Fernet key
3. The MariaDB connection pool cannot be established

---

## Supported device types

Set the `device_type` column in the `devices` table to one of these values:

| `device_type` | Vendor / Platform | SSH commands used |
|---|---|---|
| `cisco_ios` | Cisco IOS | `show inventory`, `show version` |
| `cisco_xe` | Cisco IOS-XE | `show inventory`, `show version` |
| `cisco_nxos` | Cisco NX-OS | `show inventory`, `show version` |
| `hp_procurve` | HP ProCurve | `show system information` |
| `aruba_procurve` | Aruba ArubaOS-Switch | `show system information`, `show version` |
| `ruckus_fastiron` | Ruckus ICX / FastIron | `show version` |
| `ruckus_wireless` | Ruckus ZoneDirector / SmartZone | `show version` ⚠️ |

> ⚠️ **Ruckus wireless**: The Netmiko `device_type` for Ruckus wireless controllers is unconfirmed. The collector tries `ruckus_wireless`, then `linux`, then `generic_termserver` in order. Validate against real hardware before production use.

Devices with an unrecognised `device_type` are **skipped** with a `WARNING` log entry — they do not produce an inventory row and do not count toward the summary total.

---

## Running tests

Integration tests require a live MariaDB instance. Configure the test database via environment variables before running:

```bash
export TEST_DB_HOST=127.0.0.1
export TEST_DB_PORT=3306
export TEST_DB_USER=root
export TEST_DB_PASSWORD=
export TEST_DB_NAME=test_inventory

pytest tests/integration/ -v
```

To skip tests that require real network devices (safe for CI):

```bash
pytest tests/integration/ -v -m "not real_device"
```

The test database must have the schema applied and will be seeded automatically by the test fixtures (devices with ID 1 enabled, ID 2 disabled).

---

## Adding a new device type

1. Create `network_inventory/collectors/<vendor_platform>.py`
2. Subclass `BaseCollector` and implement two methods:
   - `get_serial_number(self) -> str | None`
   - `get_firmware_version(self) -> str | None`
3. Add the `device_type` string → class mapping in `network_inventory/collectors/__init__.py`

No other files require changes. Example skeleton:

```python
from network_inventory.collectors.base_collector import BaseCollector

class MyVendorCollector(BaseCollector):
    def get_serial_number(self) -> str | None:
        output = self.connection.send_command("show serial")
        # parse and return, or return None
        ...

    def get_firmware_version(self) -> str | None:
        output = self.connection.send_command("show version")
        # parse and return, or return None
        ...
```

Then in `network_inventory/collectors/__init__.py`:

```python
try:
    from network_inventory.collectors.my_vendor import MyVendorCollector
    COLLECTOR_REGISTRY["my_device_type"] = MyVendorCollector
except ImportError:
    pass
```

---

## Scheduling (cron example)

To run inventory collection daily at 2 AM:

```cron
0 2 * * * cd /path/to/repo && /path/to/repo/.venv/bin/python network_inventory/main.py >> /var/log/inventory-cron.log 2>&1
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Configuration error: Missing required environment variables: DB_HOST` | `.env` file not loaded or variable missing | Check `.env` exists in the working directory and contains the variable |
| `Encryption key error: [Errno 2] No such file or directory` | `ENCRYPTION_KEY_FILE` path wrong | Verify the path in `.env` points to the key file |
| Exit code 1 immediately, no devices polled | DB unreachable | Verify `DB_HOST`, `DB_PORT`, credentials, and network access |
| All devices `timeout` | SSH port blocked | Check firewall rules from the tool host to device management IPs |
| Device skipped with WARNING | Unknown `device_type` | Check the `device_type` value in `devices` table matches a [supported type](#supported-device-types) |
| `serial_number` / `firmware_version` is NULL | Regex did not match device output | Set `LOG_LEVEL=DEBUG` and inspect log for the output excerpt |
