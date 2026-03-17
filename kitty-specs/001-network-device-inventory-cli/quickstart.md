# Quickstart: Network Device Inventory CLI

**Date**: 2026-03-12

## Prerequisites

- Python 3.11 or higher
- MariaDB server accessible from the host running the tool
- SSH access to all target network devices (firewall rules pre-configured)
- `devices` and `device_inventory` tables created in MariaDB (see below)

---

## 1. Create the database schema

```bash
mysql -u root -p <your_database> < kitty-specs/001-network-device-inventory-cli/contracts/schema.sql
```

Create a dedicated DB user with minimal privileges:

```sql
CREATE USER 'inventory_user'@'%' IDENTIFIED BY 'strong_password';
GRANT SELECT ON your_database.devices TO 'inventory_user'@'%';
GRANT INSERT, UPDATE ON your_database.device_inventory TO 'inventory_user'@'%';
FLUSH PRIVILEGES;
```

---

## 2. Set up the Python environment

```bash
git clone <repo-url> && cd <repo>
python3.11 -m venv .venv
source .venv/bin/activate        # macOS / Linux
pip install -r requirements.txt
```

---

## 3. Generate the encryption key file

Run once to generate the key. Store it somewhere secure and restrict permissions.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
    > /secure/path/inventory.key
chmod 600 /secure/path/inventory.key
```

> **Important**: Back up this key file. If it is lost, encrypted passwords in the `devices` table cannot be recovered.

---

## 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your values
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_HOST` | Yes | — | MariaDB hostname or IP |
| `DB_PORT` | No | 3306 | MariaDB port |
| `DB_USER` | Yes | — | MariaDB username |
| `DB_PASSWORD` | Yes | — | MariaDB password |
| `DB_NAME` | Yes | — | Database name |
| `ENCRYPTION_KEY_FILE` | Yes | — | Absolute path to the Fernet key file |
| `MAX_THREADS` | No | 10 | Max parallel SSH workers |
| `SSH_TIMEOUT` | No | 30 | SSH connection timeout (seconds) |
| `LOG_FILE` | No | `inventory.log` | Log output file path |
| `LOG_LEVEL` | No | `INFO` | Log verbosity: `DEBUG`, `INFO`, or `WARNING` |

---

## 5. Populate the devices table

Use your preferred DB client or migration tool to insert device records. Passwords must be Fernet-encrypted before inserting (use the same key file from step 3).

Example encryption helper (run interactively):

```python
from cryptography.fernet import Fernet

key = open('/secure/path/inventory.key', 'rb').read().strip()
f = Fernet(key)
plaintext = "my_device_password"
encrypted = f.encrypt(plaintext.encode())
print(encrypted)  # insert this value into devices.password
```

---

## 6. Run the inventory collector

```bash
source .venv/bin/activate
python network_inventory/main.py
```

On completion, a summary is printed:

```
Inventory run complete.
  Total polled : 12
  Success      : 10
  Failed       : 1
  Timeout      : 1
```

Results are written to the `device_inventory` table.

---

## Running integration tests

Integration tests require a live MariaDB instance and accessible test devices. Configure test credentials via environment variables or a `.env.test` file before running.

```bash
pytest tests/integration/ -v
```

---

## Adding a new device type

1. Create `network_inventory/collectors/<vendor_platform>.py`
2. Subclass `BaseCollector` and implement `get_serial_number()` and `get_firmware_version()`
3. Register the new `device_type` string → class mapping in `network_inventory/collectors/__init__.py`
4. No other files require changes
