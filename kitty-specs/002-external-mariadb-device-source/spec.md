# Feature Specification: External MariaDB Device Source

**Feature Branch**: `002-external-mariadb-device-source`
**Created**: 2026-03-20
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Query Devices from External Database (Priority: P1)

An operator runs the inventory collection tool. Instead of reading device records from the local MariaDB, the tool connects to a separate, externally managed MariaDB database and executes a user-supplied SQL query to retrieve the list of devices to poll.

**Why this priority**: This is the core change — without it, no other stories are possible. All downstream behaviour (SSH polling, result storage) depends on devices being sourced correctly.

**Independent Test**: Run the tool with a valid external DB connection and a SQL query that returns device rows. Confirm the tool successfully polls each returned device via SSH.

**Acceptance Scenarios**:

1. **Given** the external DB is reachable and the configured query returns one or more device rows, **When** the tool starts, **Then** it connects to the external DB, executes the query, and uses the returned devices for SSH polling.
2. **Given** the external DB credentials or host are misconfigured, **When** the tool starts, **Then** it logs a clear error and exits with a non-zero code without attempting SSH.
3. **Given** the configured query returns zero rows, **When** the tool starts, **Then** it logs a warning ("no devices found") and exits cleanly with code 0.

---

### User Story 2 - Plaintext Credentials from External Source (Priority: P1)

Device SSH credentials (username and password) are returned as plaintext columns from the external database query. The tool uses them directly for SSH connections without any decryption step.

**Why this priority**: Removing encryption is a required simplification that affects the SSH connection path and eliminates the Fernet key dependency entirely.

**Independent Test**: Configure the external query to return a device with plaintext username/password. Confirm the tool establishes an SSH session without requiring a key file.

**Acceptance Scenarios**:

1. **Given** the external query returns a device row with plaintext `username` and `password` columns, **When** the tool connects via SSH, **Then** it uses those values directly without any decryption.
2. **Given** no Fernet key file is present on the system, **When** the tool runs, **Then** it starts successfully and collects inventory without error.

---

### User Story 3 - Configurable External DB Connection and Query (Priority: P2)

An operator can configure the external database connection (host, port, user, password, database name) and the SQL query via environment variables or a config file, without modifying source code.

**Why this priority**: Operators need to point the tool at different environments (dev, staging, production) and supply organisation-specific queries without code changes.

**Independent Test**: Change the external DB env vars to point at a different database, restart the tool, and confirm it queries the new source.

**Acceptance Scenarios**:

1. **Given** external DB settings are defined in the environment, **When** the tool starts, **Then** it uses those settings to connect to the external DB.
2. **Given** the SQL query is defined in the environment or config, **When** the tool starts, **Then** it executes that exact query against the external DB.
3. **Given** required external DB settings are missing, **When** the tool starts, **Then** it reports all missing variables and exits with code 1.

---

### Edge Cases

- What happens when the external DB is reachable but the SQL query is syntactically invalid? → Tool logs the DB error and exits with code 1.
- What happens when a device row is missing a required field (e.g. no IP address)? → That row is skipped with a warning; remaining devices are still polled.
- What happens when the external DB connection drops mid-query? → Tool logs the connection error and exits with code 1.
- What happens when the external DB returns duplicate device entries? → Duplicates are deduplicated by host/IP before polling begins.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The tool MUST connect to a configurable external MariaDB database at startup to source the device list.
- **FR-002**: The tool MUST execute a user-supplied SQL query against the external database to retrieve device records.
- **FR-003**: The external DB connection parameters (host, port, user, password, database name) MUST be configurable via environment variables.
- **FR-004**: The SQL query MUST be configurable via an environment variable or configuration file without code changes.
- **FR-005**: Device SSH credentials (username and password) returned by the external query MUST be used as plaintext — no decryption step.
- **FR-006**: The tool MUST NOT require a Fernet encryption key file to start or operate.
- **FR-007**: If the external DB is unreachable or the query fails, the tool MUST log a descriptive error and exit with a non-zero code.
- **FR-008**: If the external query returns zero device rows, the tool MUST log a warning and exit cleanly with code 0.
- **FR-009**: Device rows missing required fields (host/IP) MUST be skipped with a per-row warning; the remaining devices MUST still be processed.
- **FR-010**: Duplicate device entries returned by the external query MUST be deduplicated before SSH polling begins.
- **FR-011**: The existing SSH polling pipeline, inventory result storage (local MariaDB), and reporting behaviour MUST remain unchanged.
- **FR-012**: The tool MUST fail fast at startup if any required external DB environment variables are missing, listing all missing variables in the error message.

### Key Entities

- **External Device Record**: A row returned by the user-supplied SQL query. Must contain at minimum: `hostname` or `ip_address`, `device_type`, `username`, `password`. Additional columns are ignored.
- **External DB Connection**: Configuration for connecting to the source database (host, port, user, password, db name, optional connection timeout).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The tool retrieves the full device list from the external database and begins SSH polling within 10 seconds of startup under normal network conditions.
- **SC-002**: All devices returned by the external query are polled in a single run with no silent omissions — any skipped device produces a logged warning.
- **SC-003**: Removing the Fernet key file from the system does not cause the tool to fail or emit any encryption-related errors.
- **SC-004**: Changing the external DB connection settings or SQL query in the environment takes effect on the next run without code changes or redeployment.
- **SC-005**: A misconfigured or unreachable external DB results in a clear, actionable error message within 10 seconds of startup.

## Assumptions

- The external MariaDB database is managed by a third party and the tool has read-only access to it.
- The SQL query is trusted — no query sanitisation is required (it is operator-supplied, not user input).
- The external DB schema is not defined by this feature; the operator maps their existing schema to the expected column names via their SQL query (e.g. `SELECT ip AS ip_address, ...`).
- The local MariaDB (for storing collection results) remains in use and is unaffected by this change.
- Encryption of credentials stored in the local results DB is out of scope for this feature.
- Connection pooling to the external DB is not required — a single connection per run is sufficient.
