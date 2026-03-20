# Network Device Inventory CLI — User Guide

A CLI tool that SSH-polls network devices and writes serial numbers, firmware versions, and poll status to a MariaDB database.

---

## Prerequisites

- macOS (Apple Silicon or Intel)
- [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) installed and running
- SSH reachable on all target devices (port 22 by default)

---

## 1. Start MariaDB with Docker

Create a `docker-compose.yml` in the project root:

```yaml
services:
  mariadb:
    image: mariadb:10.6
    container_name: inventory-db
    restart: unless-stopped
    environment:
      MARIADB_ROOT_PASSWORD: rootpassword
      MARIADB_DATABASE: inventory
      MARIADB_USER: inventory_user
      MARIADB_PASSWORD: strong_password
    ports:
      - "3306:3306"
    volumes:
      - mariadb_data:/var/lib/mysql

volumes:
  mariadb_data:
```

Start the database:

```bash
docker compose up -d
```

Wait a few seconds for MariaDB to initialize, then verify it is running:

```bash
docker compose ps
```

---

## 2. Apply the database schema

```bash
docker cp kitty-specs/001-network-device-inventory-cli/contracts/schema.sql \
    inventory-db:/tmp/schema.sql
docker exec inventory-db mariadb -u root -prootpassword inventory \
    -e "source /tmp/schema.sql"
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

The `docker-compose.yml` above creates `inventory_user` automatically. If you need additional privileges or a custom user, connect as root:

```bash
docker exec -it inventory-db mariadb -u root -prootpassword inventory
```

Then run:

```sql
GRANT SELECT ON inventory.devices TO 'inventory_user'@'%';
GRANT INSERT, UPDATE ON inventory.device_inventory TO 'inventory_user'@'%';
FLUSH PRIVILEGES;
```

---

## 3. Generate the encryption key

Device passwords are stored Fernet-encrypted in the database. Generate a key once and keep it safe:

```bash
docker run --rm python:3.11-slim \
    sh -c "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'" \
    > ~/inventory.key
chmod 600 ~/inventory.key
```

> **Back this file up.** If it is lost, the encrypted passwords in the `devices` table cannot be recovered.

---

## 4. Configure environment variables

Copy the example env file and edit it:

```bash
cp network_inventory/.env.example .env
```

Set these values in `.env`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_HOST` | Yes | — | `host.docker.internal` (to reach the Docker MariaDB from another container) or `127.0.0.1` (when running the tool directly on macOS) |
| `DB_PORT` | No | `3306` | MariaDB port |
| `DB_USER` | Yes | — | `inventory_user` |
| `DB_PASSWORD` | Yes | — | `strong_password` |
| `DB_NAME` | Yes | — | `inventory` |
| `ENCRYPTION_KEY_FILE` | Yes | — | Path to the Fernet key file (see below) |
| `MAX_THREADS` | No | `10` | Max parallel SSH workers |
| `SSH_TIMEOUT` | No | `30` | SSH connection timeout (seconds) |
| `LOG_FILE` | No | `inventory.log` | Log output file path |
| `LOG_LEVEL` | No | `INFO` | Log verbosity: `DEBUG`, `INFO`, or `WARNING` |

**DB_HOST note:** Use `127.0.0.1` when running the tool on macOS directly. Use `host.docker.internal` when running the tool inside a Docker container.

The tool validates all required variables at startup and exits with a descriptive error if any are missing.

---

## 5. Add devices to the database

Passwords must be encrypted before inserting. Use this one-liner with Docker:

```bash
docker run --rm \
    -v ~/inventory.key:/tmp/inventory.key:ro \
    python:3.11-slim \
    sh -c "pip install -q cryptography && python -c \
\"from cryptography.fernet import Fernet; \
key=open('/tmp/inventory.key','rb').read().strip(); \
f=Fernet(key); print(f.encrypt(b'my_device_password').decode())\""
```

Replace `my_device_password` with the actual SSH password for the device.

Copy the printed ciphertext, then insert the device:

```bash
docker exec -it inventory-db mariadb -u inventory_user -pstrong_password inventory
```

```sql
INSERT INTO devices (hostname, ip_address, ssh_port, username, password, device_type, enabled)
VALUES ('core-sw-01', '10.0.0.1', 22, 'admin', '<encrypted_value>', 'cisco_ios', 1);
```

See [Supported device types](#supported-device-types) for valid `device_type` values.

---

## 6. Build the tool image

```bash
docker build -t network-inventory .
```

---

## 7. Run the tool

```bash
docker run --rm \
    --env-file .env \
    -e DB_HOST=host.docker.internal \
    -v ~/inventory.key:/app/inventory.key:ro \
    -e ENCRYPTION_KEY_FILE=/app/inventory.key \
    network-inventory
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

Integration tests require a live MariaDB instance. The Docker MariaDB started in step 1 can serve as the test database. Apply the schema to a separate test database first:

```bash
docker exec -i inventory-db mariadb -u root -prootpassword -e \
    "CREATE DATABASE IF NOT EXISTS test_inventory;"
docker exec -i inventory-db mariadb -u root -prootpassword test_inventory \
    < kitty-specs/001-network-device-inventory-cli/contracts/schema.sql
```

Run the tests inside a container so the Python environment matches:

```bash
docker run --rm \
    --env-file .env \
    -e DB_HOST=host.docker.internal \
    -e TEST_DB_HOST=host.docker.internal \
    -e TEST_DB_PORT=3306 \
    -e TEST_DB_USER=root \
    -e TEST_DB_PASSWORD=rootpassword \
    -e TEST_DB_NAME=test_inventory \
    -v ~/inventory.key:/app/inventory.key:ro \
    -e ENCRYPTION_KEY_FILE=/app/inventory.key \
    network-inventory \
    python -m pytest tests/integration/ -v
```

To skip tests that require real network devices (safe for CI):

```bash
docker run --rm \
    ... \
    network-inventory \
    python -m pytest tests/integration/ -v -m "not real_device"
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

Rebuild the image after adding a new collector:

```bash
docker build -t network-inventory .
```

---

## Scheduling (launchd example)

To run inventory collection daily at 2 AM on macOS, create a launchd plist at `~/Library/LaunchAgents/com.inventory.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.inventory</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/docker</string>
        <string>run</string>
        <string>--rm</string>
        <string>--env-file</string>
        <string>/Users/YOUR_USERNAME/my-project/.env</string>
        <string>-e</string>
        <string>DB_HOST=host.docker.internal</string>
        <string>-v</string>
        <string>/Users/YOUR_USERNAME/inventory.key:/app/inventory.key:ro</string>
        <string>-e</string>
        <string>ENCRYPTION_KEY_FILE=/app/inventory.key</string>
        <string>network-inventory</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/inventory.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/inventory-error.log</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.inventory.plist
```

Replace `YOUR_USERNAME` with your macOS username (`echo $USER`).

---

## Stopping and cleaning up

Stop the MariaDB container (data is preserved in the Docker volume):

```bash
docker compose down
```

To also delete all stored data:

```bash
docker compose down -v
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Configuration error: Missing required environment variables: DB_HOST` | `.env` file not loaded or variable missing | Check `.env` exists in the working directory and contains the variable |
| `Encryption key error: [Errno 2] No such file or directory` | `ENCRYPTION_KEY_FILE` path wrong or key not mounted | Verify the `-v` mount and `ENCRYPTION_KEY_FILE` path in the `docker run` command |
| Exit code 1 immediately, no devices polled | DB unreachable | Confirm `docker compose ps` shows MariaDB healthy; use `DB_HOST=host.docker.internal` from inside a container |
| `Can't connect to MariaDB` from container | Wrong host | Use `host.docker.internal` as `DB_HOST`, not `127.0.0.1` or `localhost` |
| All devices `timeout` | SSH port blocked | Check macOS firewall and network rules from the Docker container to device management IPs |
| Device skipped with WARNING | Unknown `device_type` | Check the `device_type` value in `devices` table matches a [supported type](#supported-device-types) |
| `serial_number` / `firmware_version` is NULL | Regex did not match device output | Set `LOG_LEVEL=DEBUG` and inspect log for the output excerpt |
