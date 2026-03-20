---
work_package_id: WP01
title: Config & Model Changes
lane: "done"
dependencies: []
base_branch: master
base_commit: 78c19143c79ae7bba90daa1ded5150e618a8332d
created_at: '2026-03-20T14:56:56.191242+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 0 - Foundation
assignee: ''
agent: "claude-sonnet-4-6"
shell_pid: "42186"
review_status: "approved"
reviewed_by: "rpatel-hk"
history:
- timestamp: '2026-03-20T14:42:47Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-003
- FR-004
- FR-005
- FR-006
- FR-012
---

# Work Package Prompt: WP01 – Config & Model Changes

## ⚠️ IMPORTANT: Review Feedback Status

Check `review_status` in frontmatter. If `has_feedback`, read the Review Feedback section below before touching any code.

---

## Review Feedback

*[Empty — no feedback yet.]*

---

## Objectives & Success Criteria

- `Settings` dataclass no longer has `encryption_key_file`; adding it to the environment has no effect.
- `Settings` resolves `EXT_DB_HOST`, `EXT_DB_PORT` (default 3306), `EXT_DB_USER`, `EXT_DB_PASSWORD`, `EXT_DB_NAME`, `EXT_DB_QUERY` from environment.
- `_load_settings()` fails fast listing all missing `EXT_DB_*` vars; `ENCRYPTION_KEY_FILE` is no longer checked.
- `Device.password` is typed `str` (not `bytes`); instantiation with a plaintext string works.
- `.env.example` documents the new `EXT_DB_*` variables and omits `ENCRYPTION_KEY_FILE`.

## Context & Constraints

- **Working branch**: `001-network-device-inventory-cli-WP01` (stacked on `master`)
- **Workspace**: `.worktrees/002-external-mariadb-device-source-WP01/`
- **Spec**: `kitty-specs/002-external-mariadb-device-source/spec.md` — FR-003, FR-004, FR-005, FR-006, FR-012
- **Data model**: `kitty-specs/002-external-mariadb-device-source/data-model.md`
- This WP is foundational — WP02 and WP03 both depend on these changes.
- `Device.enabled` field is **kept** (always `True` from external source; downstream code uses it).
- Do **not** touch `base_collector.py`, `encryption.py`, `main.py`, or `db/queries.py` in this WP — those are WP02–WP04.

**Run from workspace root:**
```bash
spec-kitty implement WP01
```

---

## Subtasks & Detailed Guidance

### Subtask T001 – Remove `encryption_key_file` from `config.py`

**Purpose**: The Fernet key file is no longer required. Removing it from `Settings` ensures startup validation doesn't demand a key that no longer exists.

**File**: `network_inventory/config.py`

**Steps**:
1. Delete the `encryption_key_file` field from the `Settings` dataclass:
   ```python
   # DELETE this block:
   encryption_key_file: str = field(
       default_factory=lambda: os.environ["ENCRYPTION_KEY_FILE"]
   )
   ```
2. In `_load_settings()`, remove `"ENCRYPTION_KEY_FILE"` from the required-vars tuple:
   ```python
   # BEFORE:
   for var in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME", "ENCRYPTION_KEY_FILE"):
   # AFTER (T003 will complete this change):
   for var in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"):
   ```
   Note: T003 will add the `EXT_DB_*` vars to this check. For now just remove `ENCRYPTION_KEY_FILE`.

**Validation**: `Settings()` can be instantiated without `ENCRYPTION_KEY_FILE` in the environment.

---

### Subtask T002 – Add `EXT_DB_*` fields to `Settings`

**Purpose**: Expose the external database connection parameters as typed, env-backed settings fields.

**File**: `network_inventory/config.py`

**Steps**:
1. After the existing `db_name` field, add the external DB fields:
   ```python
   # External device source database (required)
   ext_db_host: str = field(default_factory=lambda: os.environ["EXT_DB_HOST"])
   ext_db_port: int = field(default_factory=lambda: int(os.getenv("EXT_DB_PORT", "3306")))
   ext_db_user: str = field(default_factory=lambda: os.environ["EXT_DB_USER"])
   ext_db_password: str = field(default_factory=lambda: os.environ["EXT_DB_PASSWORD"])
   ext_db_name: str = field(default_factory=lambda: os.environ["EXT_DB_NAME"])
   ext_db_query: str = field(default_factory=lambda: os.environ["EXT_DB_QUERY"])
   ```
2. No other fields change.

**Notes**:
- `ext_db_port` defaults to `3306` (consistent with `db_port` pattern).
- `ext_db_query` is a required string — the operator must supply a full SQL SELECT.

---

### Subtask T003 – Update `_load_settings()` required-var check

**Purpose**: Fail fast at startup with a descriptive message listing all missing `EXT_DB_*` vars (FR-012).

**File**: `network_inventory/config.py`

**Steps**:
1. Replace the existing required-vars tuple to include the new external DB vars and remove `ENCRYPTION_KEY_FILE`:
   ```python
   def _load_settings() -> Settings:
       missing = []
       for var in (
           "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME",
           "EXT_DB_HOST", "EXT_DB_USER", "EXT_DB_PASSWORD",
           "EXT_DB_NAME", "EXT_DB_QUERY",
       ):
           if not os.getenv(var):
               missing.append(var)
       if missing:
           raise EnvironmentError(
               f"Missing required environment variables: {', '.join(missing)}. "
               f"Copy .env.example to .env and populate the values."
           )
       return Settings()
   ```
2. Note: `EXT_DB_PORT` is intentionally excluded (has a default of `3306`).

**Validation**: With `EXT_DB_HOST` and `EXT_DB_QUERY` unset, `_load_settings()` raises `EnvironmentError` listing both vars.

---

### Subtask T004 – Change `Device.password: bytes` → `str`

**Purpose**: Plaintext passwords from the external DB are strings. The `bytes` type was required for Fernet-encrypted VARBINARY storage — no longer applicable.

**File**: `network_inventory/models/device.py`

**Steps**:
1. Change the `password` field type annotation:
   ```python
   # BEFORE:
   password: bytes          # Fernet-encrypted; decrypted only at SSH connection time

   # AFTER:
   password: str            # Plaintext SSH password from external device source
   ```
2. Update the class docstring from `"Represents a row from the 'devices' table"` to something like `"Represents a device record sourced from the external database"`.

**Validation**: `Device(id=1, hostname="sw1", ip_address="10.0.0.1", ssh_port=22, username="admin", password="secret", device_type="cisco_ios", enabled=True)` instantiates without error.

---

### Subtask T005 – Update `.env.example`

**Purpose**: Operators copy `.env.example` to `.env` as their starting point. It must document the new `EXT_DB_*` vars and omit `ENCRYPTION_KEY_FILE`.

**File**: `network_inventory/.env.example`

**Steps**:
1. Remove the `ENCRYPTION_KEY_FILE` line/block entirely.
2. Add an `# External device source` section after the existing local DB section:
   ```dotenv
   # External device source — read-only connection to fetch device list
   EXT_DB_HOST=external-db.example.com
   EXT_DB_PORT=3306
   EXT_DB_USER=readonly_user
   EXT_DB_PASSWORD=change_me
   EXT_DB_NAME=network_management
   # SQL query returning: ip_address, device_type, username, password
   # (hostname, ssh_port optional — defaults to ip_address and 22)
   EXT_DB_QUERY=SELECT ip_address, device_type, username, password, hostname, ssh_port FROM managed_devices WHERE active = 1
   ```

**Notes**:
- Keep existing `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` section intact (local results DB).
- The example query is illustrative; include a comment explaining expected columns.

---

## Risks & Mitigations

- **`Device.password` type change breaks WP04 collector code** — acceptable; WP04 is in a separate worktree.
- **`_load_settings()` now requires `EXT_DB_*`** — ensure local dev `.env` is updated before running locally.

## Review Guidance

Reviewer should verify:
1. `config.py`: `encryption_key_file` field gone; 6 new `ext_db_*` fields present; `_load_settings()` checks 9 required vars (no `ENCRYPTION_KEY_FILE`, no `EXT_DB_PORT`).
2. `models/device.py`: `password` annotation is `str`, not `bytes`.
3. `.env.example`: `ENCRYPTION_KEY_FILE` absent; all 6 `EXT_DB_*` vars documented with example values.
4. No other files modified in this WP.

## Activity Log

- 2026-03-20T14:42:47Z – system – lane=planned – Prompt created.
- 2026-03-20T14:56:56Z – claude-sonnet-4-6 – shell_pid=29528 – lane=doing – Assigned agent via workflow command
- 2026-03-20T14:57:50Z – claude-sonnet-4-6 – shell_pid=29528 – lane=for_review – Ready for review: config.py (EXT_DB_* fields, no encryption_key_file), Device.password str, .env.example updated
- 2026-03-20T15:52:32Z – claude-sonnet-4-6 – shell_pid=42186 – lane=doing – Started review via workflow command
- 2026-03-20T15:53:15Z – claude-sonnet-4-6 – shell_pid=42186 – lane=done – Review passed: EXT_DB_* config fields correct with 3306 default for port; Device.password correctly changed to str; _load_settings() validates 9 required vars; .env.example well-documented with example query
