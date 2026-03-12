# Feature Specification: Network Device Inventory CLI

**Feature Branch**: `001-network-device-inventory-cli`
**Created**: 2026-03-12
**Status**: Draft
**Mission**: software-dev

## Overview

A command-line tool that collects hardware inventory data (serial numbers and firmware versions) from network devices by connecting to them over SSH, and stores the results in a central database. The tool runs on-demand and exits on completion.

## Clarifications

### Session 2026-03-12

- Q: Which Ruckus devices are in scope for v1? → A: Both ICX switches and wireless APs/controllers
- Q: Where does the decryption key for device passwords come from at runtime? → A: Separate key file on disk, with its path configured via an environment variable
- Q: Do HP and Aruba devices use the same SSH commands for serial/firmware collection? → A: Treat as separate collectors for now; consolidate later if commands prove identical
- Q: Should device_inventory keep history or overwrite per device? → A: Overwrite — always keep only the latest result (one record per device)

## User Scenarios & Testing

### User Story 1 - Full Inventory Run (Priority: P1)

A network operator wants to collect up-to-date serial numbers and firmware versions for all managed devices. They run the CLI tool from a workstation or automation server. The tool connects to every enabled device in the database, collects the required data, and records the results. The operator sees a summary of successes and failures on completion.

**Why this priority**: Core purpose of the tool — without this working end-to-end, no other story delivers value.

**Independent Test**: Populate the `devices` table with at least one enabled device, run the CLI, and verify a corresponding record appears in `device_inventory` with `status = success`, a non-empty serial number, and a firmware version.

**Acceptance Scenarios**:

1. **Given** one or more enabled devices exist in the database, **When** the operator runs the CLI, **Then** each device is polled and a result record is written to `device_inventory`
2. **Given** a device is successfully polled, **When** results are stored, **Then** the record contains a non-empty serial number, firmware version, `status = success`, and a `last_success` timestamp
3. **Given** the tool finishes all polling, **When** the summary is printed, **Then** it shows total devices polled, success count, failure count, and timeout count

---

### User Story 2 - Graceful Failure Handling (Priority: P2)

Some devices may be unreachable, have incorrect credentials, or time out during a run. The operator needs to know which devices failed and why, without aborting the entire run.

**Why this priority**: Partial failures are common in network environments. Silent failures would make the inventory unreliable and untrustworthy.

**Independent Test**: Add a device with an incorrect password to the database, run the CLI, and verify the device appears in `device_inventory` with `status = failed`, a non-empty `error_message`, and a `last_attempt` timestamp.

**Acceptance Scenarios**:

1. **Given** a device is unreachable, **When** the connection attempt times out, **Then** a record is written with `status = timeout` and a message describing the timeout
2. **Given** a device has invalid credentials, **When** authentication fails, **Then** a record is written with `status = failed` and a message indicating authentication failure
3. **Given** one device fails, **When** the run continues, **Then** all other enabled devices are still polled (a single failure does not abort the run)
4. **Given** a device returns unexpected or unparseable output, **When** parsing fails, **Then** a record is written with `status = failed` and the raw output is captured in `error_message`

---

### User Story 3 - Disabled Device Exclusion (Priority: P3)

A network operator wants to temporarily stop polling a device (e.g., during maintenance) without deleting it from the inventory database.

**Why this priority**: Operational necessity to avoid filling the inventory with expected failures during planned maintenance windows.

**Independent Test**: Set `enabled = FALSE` on a device, run the CLI, and verify no new or updated `device_inventory` record is written for that device.

**Acceptance Scenarios**:

1. **Given** a device has `enabled = FALSE`, **When** the CLI runs, **Then** that device is skipped and no result record is written or updated for it
2. **Given** a disabled device is re-enabled, **When** the CLI runs again, **Then** the device is polled and a result is recorded normally

---

### User Story 4 - Secure Credential Handling (Priority: P4)

An operator configures the tool by setting environment variables for database access. Device credentials stored in the database are encrypted so that a database export does not expose cleartext passwords.

**Why this priority**: Security baseline — credentials must not appear in source code, config files, or plaintext database records.

**Independent Test**: Inspect source files, `.env` template, and the raw value of a `password` column in the `devices` table — the database connection password must not appear in any source file, and device passwords in the DB must not be human-readable plaintext.

**Acceptance Scenarios**:

1. **Given** DB credentials are set as environment variables, **When** the tool starts, **Then** it connects to the database without any credentials present in source files
2. **Given** device passwords are stored encrypted in the DB, **When** the tool connects to a device, **Then** the password is decrypted only in memory at connection time
3. **Given** the tool is assigned a dedicated database user, **When** it runs, **Then** it requires only SELECT on `devices` and INSERT/UPDATE on `device_inventory` — no broader privileges

---

### Edge Cases

- What happens when there are no enabled devices in the database? Tool exits cleanly with a clear message indicating nothing to poll.
- What happens when the database is unreachable at startup? Tool exits immediately with a non-zero exit code and a descriptive error.
- What happens when a device returns partial data (e.g., serial found but firmware missing)? The available fields are stored and missing fields are left null.
- What happens when two workers attempt to write a result for the same device simultaneously? Upsert by `device_id` prevents duplicate records.
- What happens when a `device_type` value in the database has no corresponding collector? The device is skipped with a logged warning; all other devices proceed normally.
- What happens when all thread workers are busy? Remaining devices are queued and processed as workers become available — no device is silently dropped.
- What happens when the key file path is not configured or the file is missing/unreadable? Tool exits immediately at startup with a non-zero exit code and a clear error message before any device polling begins.

## Requirements

### Functional Requirements

- **FR-001**: The tool MUST query the `devices` table at startup and poll only records where `enabled = TRUE`
- **FR-002**: The tool MUST poll devices concurrently with a configurable maximum number of parallel workers
- **FR-003**: The tool MUST support the following device families in v1: Cisco (IOS, IOS-XE, NX-OS), HP, Aruba, and Ruckus (both ICX switches and wireless APs/controllers — each as a distinct collector)
- **FR-004**: The tool MUST collect a serial number and firmware version from each polled device
- **FR-005**: The tool MUST write a result record to `device_inventory` for every poll attempt, regardless of outcome
- **FR-006**: The tool MUST classify every result as one of: `success`, `failed`, or `timeout`
- **FR-007**: The tool MUST record a descriptive error message for every non-success result
- **FR-008**: The tool MUST perform an upsert (insert or update) on `device_inventory` keyed by `device_id`, so each device has at most one current result record
- **FR-009**: The tool MUST load all database credentials and app configuration from environment variables or a `.env` file — never from hardcoded values in source code
- **FR-010**: Device passwords stored in the `devices` table MUST be encrypted at rest; the decryption key MUST be loaded from a key file on disk whose path is configured via an environment variable, and decryption MUST occur only in memory at connection time
- **FR-011**: The tool MUST print a completion summary showing: total devices polled, success count, failure count, and timeout count
- **FR-012**: The tool MUST write structured logs to a configurable file path with automatic rotation
- **FR-013**: A database connection failure at startup MUST cause the tool to exit immediately with a non-zero exit code and a descriptive error message
- **FR-014**: The collector architecture MUST allow adding a new device type by creating one new module, with no changes required to existing collector code or core orchestration logic

### Key Entities

- **Device**: A managed network device — identified by hostname and management IP, associated with a device family/type, SSH access credentials, and an enabled/disabled flag
- **Inventory Record**: Captures the outcome of a poll for a specific device — contains serial number, firmware version, result status, attempt and success timestamps, and optional error details
- **Collector**: A device-type-specific handler that knows which commands to run on a given device family and how to parse the output to extract serial number and firmware version

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every enabled device in the database has a corresponding result record written after each run — zero enabled devices are silently skipped or dropped
- **SC-002**: A run against 50 devices completes within 5 minutes under normal network conditions with default concurrency settings
- **SC-003**: Every non-success outcome includes a human-readable error message sufficient to diagnose the failure without inspecting log files
- **SC-004**: Adding support for a new device type requires creating exactly one new file — no changes to existing collectors or the orchestration logic
- **SC-005**: No database credentials or device passwords appear in plaintext in source files, committed configuration, or raw database records

## Assumptions

- The `devices` and `device_inventory` tables are created before the tool runs (schema setup is out of scope for this feature)
- SSH access to all managed devices is available from the host running the tool (firewall rules are pre-configured by the operator)
- The `device_type` values stored in the `devices` table match the identifiers expected by each collector
- HP and Aruba are implemented as separate collectors; if commands prove identical during development, they may be consolidated into a shared collector at that time
- Ruckus scope confirmed: both ICX switches and wireless APs/controllers are in scope for v1, each requiring a distinct collector
- SSH host key verification defaults to auto-accept for trusted internal networks; strict verification can be enabled via configuration
- The tool does not send external alerts or notifications — failure visibility is through the completion summary, logs, and the `device_inventory` table only
