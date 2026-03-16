---
work_package_id: WP01
title: Project Setup & Configuration
lane: "planned"
dependencies: []
base_branch: master
base_commit: 9f285b789553b12b8968d6c778008cfb21489d3e
created_at: '2026-03-12T14:40:00.551790+00:00'
subtasks:
- T001
- T002
- T003
phase: Phase 0 - Foundation
assignee: ''
agent: "claude-sonnet-4-6"
shell_pid: "18272"
review_status: "has_feedback"
reviewed_by: "rpatel-hk"
review_feedback_file: "/private/var/folders/9q/_tbpgj3j6k5b3_6wcw8y8rpw0000gp/T/spec-kitty-review-feedback-WP01.md"
history:
- timestamp: '2026-03-12T10:45:33Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-009
- FR-010
- FR-012
- FR-013
---

# Work Package Prompt: WP01 – Project Setup & Configuration

## ⚠️ IMPORTANT: Review Feedback Status

**Read this first if you are implementing this task!**

- **Has review feedback?**: Check the `review_status` field above. If it says `has_feedback`, scroll to the **Review Feedback** section immediately (right below this notice).
- **You must address all feedback** before your work is complete.
- **Mark as acknowledged**: When you understand the feedback and begin addressing it, update `review_status: acknowledged` in the frontmatter.

---

## Review Feedback

**Reviewed by**: rpatel-hk
**Status**: ❌ Changes Requested
**Date**: 2026-03-16
**Feedback file**: `/private/var/folders/9q/_tbpgj3j6k5b3_6wcw8y8rpw0000gp/T/spec-kitty-review-feedback-WP01.md`

## Review Feedback

**Issue: `.env.example` contains real credentials instead of placeholder values**

The `.env.example` file was committed with what appear to be real database credentials:

```
DB_HOST=snapx-us1.safetynetaccess.com
DB_PORT=33062
DB_USER=domo-com
DB_PASSWORD=sQRqqygoLm
DB_NAME=snapx
```

`.env.example` is a template file committed to version control — it must only contain safe placeholder values. Real credentials must never be stored in version control.

**Fix**: Replace with the placeholder values specified in the WP:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=inventory_user
DB_PASSWORD=change_me
DB_NAME=network_inventory
```

**Action required**: If these are real credentials, rotate them immediately (change the password on the database server), as they may already be exposed in git history.

All other deliverables are correct:
- `.gitignore` now correctly preserves Spec Kitty managed entries (previous feedback addressed)
- `config.py` matches spec exactly
- `requirements.txt` is correct
- Directory structure with `__init__.py` stubs is complete


## Review Feedback

**Issue: `.gitignore` was fully replaced instead of extended**

The WP01 commit replaced the entire `.gitignore` with Python-specific entries, removing all Spec Kitty CLI-managed entries that existed on master:

```
# Removed entries (from master):
.claude/
.codex/
.opencode/
.windsurf/
.gemini/
.cursor/
.qwen/
.kilocode/
.augment/
.roo/
.amazonq/
.github/copilot/
.kittify/.dashboard
.kittify/missions/__pycache__/
```

When this WP merges to master, those directories will no longer be gitignored, risking accidental commits of AI tooling config and spec-kitty internal files.

**Fix**: Merge both sets of entries — preserve the existing Spec Kitty-managed lines and append the Python-specific additions below them. The final `.gitignore` should contain both sections:

```gitignore
# Added by Spec Kitty CLI (auto-managed)
.claude/
.codex/
.opencode/
.windsurf/
.gemini/
.cursor/
.qwen/
.kilocode/
.augment/
.roo/
.amazonq/
.github/copilot/
.kittify/.dashboard
.kittify/missions/__pycache__/

# Environment files — never commit secrets
.env
.env.test
*.key

# Python
__pycache__/
*.py[cod]
*.pyo
.venv/
venv/
*.egg-info/
dist/
build/

# Logs
*.log

# Test artifacts
.pytest_cache/
.coverage
htmlcov/
```

All other deliverables (directory structure, `config.py`, `.env.example`, `requirements.txt`) are correct and match the spec exactly.


## Objectives & Success Criteria

- Create the complete `network_inventory/` and `tests/` directory structure matching the plan.
- Implement `config.py` so that all downstream modules can `from network_inventory.config import settings` and get a validated `Settings` object.
- Provide `.env.example` so a new operator knows exactly which variables to set.

**Done when**:
- `python -c "from network_inventory.config import settings"` raises `EnvironmentError` listing missing vars when `.env` is absent.
- With a valid `.env`, the import succeeds and `settings.db_host` etc. are populated.
- `requirements.txt` installs cleanly in a fresh Python 3.11 venv.

## Context & Constraints

- **Spec**: `kitty-specs/001-network-device-inventory-cli/spec.md` FR-009, FR-010, FR-012, FR-013
- **Plan**: `kitty-specs/001-network-device-inventory-cli/plan.md` — Stack: Python 3.11+, Netmiko, `mariadb`, `cryptography`, `python-dotenv`
- **Quickstart**: `kitty-specs/001-network-device-inventory-cli/quickstart.md` — reference for env var names and defaults
- **Constitution**: `.kittify/memory/constitution.md` — Python 3.11+, pytest
- Run via: `python network_inventory/main.py`
- No `setup.py` / `pyproject.toml` required — plain venv + `requirements.txt`

## Subtasks & Detailed Guidance

### Subtask T001 – Create project directory structure and `requirements.txt`

**Purpose**: Establish the file tree so all other WPs have canonical paths to write to.

**Steps**:

1. Create the following directories and empty `__init__.py` files:
   ```
   network_inventory/
   network_inventory/db/
   network_inventory/collectors/
   network_inventory/models/
   network_inventory/utils/
   tests/
   tests/integration/
   ```
   Each package dir needs an `__init__.py` (can be empty for now; db, collectors, utils will be populated by later WPs).

2. Create `network_inventory/requirements.txt` (place at repo root, not inside the package):
   ```
   # Network Device Inventory CLI — dependencies
   netmiko>=4.3,<5.0
   mariadb>=1.1,<2.0
   cryptography>=42.0,<44.0
   python-dotenv>=1.0,<2.0
   ```
   Pin major versions. All are stdlib-compatible on Python 3.11+.

3. Create `tests/integration/__init__.py` (empty).

**Files**:
- `network_inventory/__init__.py` (empty)
- `network_inventory/db/__init__.py` (stub — populated in WP03)
- `network_inventory/collectors/__init__.py` (stub — populated in WP04)
- `network_inventory/models/__init__.py` (stub)
- `network_inventory/utils/__init__.py` (stub)
- `tests/__init__.py` (empty)
- `tests/integration/__init__.py` (empty)
- `requirements.txt` (at repo root)

**Validation**:
- [ ] `python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` completes without errors.
- [ ] `python -c "import netmiko, mariadb, cryptography, dotenv"` succeeds after install.

---

### Subtask T002 – Implement `network_inventory/config.py`

**Purpose**: Single source of truth for all runtime configuration; validates required vars at import time so failures are loud and early.

**Steps**:

1. Create `network_inventory/config.py`:

```python
"""Runtime configuration loaded from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()  # No-op if .env absent; env vars already set take precedence


@dataclass
class Settings:
    # Database (required)
    db_host: str = field(default_factory=lambda: os.environ["DB_HOST"])
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "3306")))
    db_user: str = field(default_factory=lambda: os.environ["DB_USER"])
    db_password: str = field(default_factory=lambda: os.environ["DB_PASSWORD"])
    db_name: str = field(default_factory=lambda: os.environ["DB_NAME"])

    # Encryption key file (required)
    encryption_key_file: str = field(
        default_factory=lambda: os.environ["ENCRYPTION_KEY_FILE"]
    )

    # Tuning (optional with defaults)
    max_threads: int = field(
        default_factory=lambda: int(os.getenv("MAX_THREADS", "10"))
    )
    ssh_timeout: int = field(
        default_factory=lambda: int(os.getenv("SSH_TIMEOUT", "30"))
    )

    # Logging (optional with defaults)
    log_file: str = field(default_factory=lambda: os.getenv("LOG_FILE", "inventory.log"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


def _load_settings() -> Settings:
    missing = []
    for var in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME", "ENCRYPTION_KEY_FILE"):
        if not os.getenv(var):
            missing.append(var)
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy .env.example to .env and populate the values."
        )
    return Settings()


settings = _load_settings()
```

**Important notes**:
- `settings` is a module-level singleton. All other modules import it as `from network_inventory.config import settings`.
- `load_dotenv()` is called before `_load_settings()` so `.env` file is respected.
- Do NOT raise on optional vars — they have defaults.
- `EnvironmentError` lists ALL missing vars in one shot, not just the first.

**Files**:
- `network_inventory/config.py`

**Validation**:
- [ ] `DB_HOST=x DB_USER=x DB_PASSWORD=x DB_NAME=x ENCRYPTION_KEY_FILE=/tmp/test python -c "from network_inventory.config import settings; print(settings.max_threads)"` prints `10`.
- [ ] Without those vars, import raises `EnvironmentError` with all missing var names listed.

---

### Subtask T003 – Create `.env.example` template

**Purpose**: Document all environment variables so any operator can configure the tool without reading source code.

**Steps**:

Create `network_inventory/.env.example` (place alongside `main.py`):

```dotenv
# =============================================================================
# Network Device Inventory CLI — Environment Configuration
# Copy this file to .env and fill in your values.
# =============================================================================

# --- Database (required) ---
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=inventory_user
DB_PASSWORD=change_me
DB_NAME=network_inventory

# --- Encryption ---
# Absolute path to the Fernet key file generated by:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > /secure/path/inventory.key
#   chmod 600 /secure/path/inventory.key
ENCRYPTION_KEY_FILE=/secure/path/inventory.key

# --- Concurrency ---
# Maximum number of parallel SSH workers (default: 10)
MAX_THREADS=10

# --- SSH ---
# SSH connection timeout in seconds (default: 30)
SSH_TIMEOUT=30

# --- Logging ---
# Log output file path (default: inventory.log in current working directory)
LOG_FILE=inventory.log
# Log verbosity: DEBUG, INFO, WARNING (default: INFO)
LOG_LEVEL=INFO
```

**Files**:
- `network_inventory/.env.example`

**Validation**:
- [ ] Every variable in `Settings` dataclass has a corresponding entry in `.env.example`.
- [ ] Comments explain what each variable does and whether it is required or optional.
- [ ] Key generation command matches `quickstart.md` step 3.

---

## Risks & Mitigations

- **Env var typo at startup**: `EnvironmentError` message explicitly lists all missing vars — operator doesn't need to re-run to discover each one individually.
- **`requirements.txt` version drift**: Pin major versions (not exact). If `mariadb` C extension cannot be installed on the target host, the operator can substitute `PyMySQL` (document in README, out of scope here).
- **`.env` accidentally committed**: Add `.env` to `.gitignore` in this WP. Only `.env.example` is committed.

## Review Guidance

- Verify `settings` singleton raises `EnvironmentError` on partial config (not just total absence).
- Confirm `.env.example` matches the `Settings` dataclass field by field.
- Check `.gitignore` excludes `.env` (but not `.env.example`).
- Run `pip install -r requirements.txt` in a fresh venv to confirm no conflicts.

## Activity Log

> **CRITICAL**: Append new entries at the END. Never prepend.

- 2026-03-12T10:45:33Z – system – lane=planned – Prompt created.
- 2026-03-12T14:40:00Z – claude-sonnet-4-6 – shell_pid=44718 – lane=doing – Assigned agent via workflow command
- 2026-03-12T14:43:35Z – claude-sonnet-4-6 – shell_pid=44718 – lane=for_review – T001-T003 complete: directory structure, config.py with EnvironmentError validation, .env.example, requirements.txt, .gitignore all committed
- 2026-03-16T14:26:33Z – claude-sonnet-4-6 – shell_pid=17424 – lane=doing – Started review via workflow command
- 2026-03-16T14:28:23Z – claude-sonnet-4-6 – shell_pid=17424 – lane=planned – Moved to planned
- 2026-03-16T14:30:03Z – claude-sonnet-4-6 – shell_pid=17977 – lane=doing – Started implementation via workflow command
- 2026-03-16T14:30:45Z – claude-sonnet-4-6 – shell_pid=17977 – lane=for_review – Ready for review: fixed .gitignore to preserve Spec Kitty managed entries alongside Python-specific additions
- 2026-03-16T14:31:24Z – claude-sonnet-4-6 – shell_pid=18272 – lane=doing – Started review via workflow command
- 2026-03-16T14:31:59Z – claude-sonnet-4-6 – shell_pid=18272 – lane=planned – Moved to planned
