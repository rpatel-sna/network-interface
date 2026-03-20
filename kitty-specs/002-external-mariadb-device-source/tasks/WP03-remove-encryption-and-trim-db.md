---
work_package_id: WP03
title: Remove Encryption and Trim DB Layer
lane: "doing"
dependencies: [WP01]
base_branch: 002-external-mariadb-device-source-WP01
base_commit: 8609129f96a6b9bc1e3511b00d861285a304854c
created_at: '2026-03-20T15:32:44.373075+00:00'
subtasks:
- T011
- T012
- T013
- T014
phase: Phase 1 - Core Implementation
assignee: ''
agent: ''
shell_pid: "37075"
review_status: ''
reviewed_by: ''
history:
- timestamp: '2026-03-20T14:42:47Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-005
- FR-006
- FR-011
---

# Work Package Prompt: WP03 – Remove Encryption and Trim DB Layer

## ⚠️ IMPORTANT: Review Feedback Status

Check `review_status` in frontmatter. If `has_feedback`, read the Review Feedback section below.

---

## Review Feedback

*[Empty — no feedback yet.]*

---

## Objectives & Success Criteria

- `network_inventory/utils/encryption.py` no longer exists.
- `from network_inventory.utils.encryption import decrypt_password` raises `ModuleNotFoundError`.
- `load_enabled_devices()` and `_LOAD_ENABLED_DEVICES_SQL` no longer exist in `db/queries.py`.
- `from network_inventory.db import load_enabled_devices` raises `ImportError`.
- `from network_inventory.db import upsert_inventory_record` still works.
- `cryptography` package removed from `requirements.txt` if it has no other consumers.

## Context & Constraints

- **Workspace**: `.worktrees/002-external-mariadb-device-source-WP03/`
- **Depends on**: WP01 (confirms encryption is fully superseded before deleting)
- **Spec**: FR-005, FR-006, FR-011
- This WP is pure deletion/trimming — no new functionality.
- `upsert_inventory_record()` in `db/queries.py` is **unchanged** — do not touch it.
- `base_collector.py` still imports `decrypt_password` at this point — that is resolved in WP04, which depends on both WP02 and WP03.

**Run from workspace root:**
```bash
spec-kitty implement WP03 --base WP01
```

---

## Subtasks & Detailed Guidance

### Subtask T011 – Delete `utils/encryption.py`

**Purpose**: The Fernet encryption module is fully replaced by plaintext credentials from the external DB. Deleting it makes the removal explicit and prevents accidental re-use.

**File**: `network_inventory/utils/encryption.py` — **delete**

**Steps**:
1. Verify no other file besides `base_collector.py` and `main.py` imports from this module:
   ```bash
   grep -r "from network_inventory.utils.encryption" network_inventory/ tests/
   ```
   Expected: only `base_collector.py` (WP04 will fix) and potentially `main.py` (WP04 will fix).
2. Delete the file:
   ```bash
   git rm network_inventory/utils/encryption.py
   ```
3. Do **not** modify `base_collector.py` or `main.py` in this WP — those are WP04.

**Notes**:
- If any other file (outside the expected two) imports from `encryption.py`, flag it in the WP review feedback rather than silently fixing it.

---

### Subtask T012 – Remove `load_enabled_devices()` from `db/queries.py`

**Purpose**: Device loading from the local `devices` table is replaced by the external source. The local function is dead code.

**File**: `network_inventory/db/queries.py`

**Steps**:
1. Delete the `_LOAD_ENABLED_DEVICES_SQL` constant (the multi-line string at the top of the file).
2. Delete the `load_enabled_devices()` function entirely (the function definition and its docstring).
3. Leave the file header comment, `_UPSERT_INVENTORY_SQL`, and `upsert_inventory_record()` completely intact.

**After the edit**, `queries.py` should contain only:
- Module docstring
- Imports (`logging`, `mariadb`, `CollectionResult`, `Device`)
- `_UPSERT_INVENTORY_SQL` constant
- `upsert_inventory_record()` function

**Validation**: Import `upsert_inventory_record` from the module — no errors. Confirm `load_enabled_devices` attribute is absent.

---

### Subtask T013 – Remove `load_enabled_devices` from `db/__init__.py`

**Purpose**: Keep the package's public API in sync with the removed function.

**File**: `network_inventory/db/__init__.py`

**Steps**:
1. Read the current `__init__.py`.
2. Remove the `load_enabled_devices` import line.
3. Remove `"load_enabled_devices"` from `__all__` (if present).
4. Leave all other imports and exports untouched.

**Notes**:
- Do not add `load_devices_from_external_db` here — that is WP02's responsibility. These are parallel WPs that touch different lines of the same file, so keep changes minimal to avoid merge conflicts.

---

### Subtask T014 – Check `requirements.txt` and remove `cryptography` if unused

**Purpose**: Avoid shipping unused dependencies.

**File**: `requirements.txt`

**Steps**:
1. Search for any remaining imports of `cryptography` in the codebase (excluding the now-deleted `encryption.py`):
   ```bash
   grep -r "from cryptography\|import cryptography" network_inventory/ tests/
   ```
2. If **no results**: Remove `cryptography>=42.0,<44.0` from `requirements.txt`.
3. If **any results found**: Leave `cryptography` in `requirements.txt` and add a comment in the review feedback noting which file still uses it.

**Notes**:
- Expected result: no remaining imports → remove `cryptography`.

---

## Risks & Mitigations

- **WP04 will temporarily have a broken import** (`from network_inventory.utils.encryption import decrypt_password`) after this WP lands — that is expected and resolved in WP04.
- **`db/__init__.py` conflict with WP02** — WP02 adds `load_devices_from_external_db`; this WP removes `load_enabled_devices`. In stacked branches this resolves cleanly as long as each WP only touches its own line. If a merge conflict occurs, keep both changes.

## Review Guidance

Reviewer checks:
1. `utils/encryption.py` does not exist in the worktree.
2. `db/queries.py` contains only `_UPSERT_INVENTORY_SQL` and `upsert_inventory_record()` — no `load_enabled_devices` remnants.
3. `db/__init__.py` does not import or export `load_enabled_devices`.
4. `cryptography` is absent from `requirements.txt` (or a justification comment is in the review feedback).
5. `upsert_inventory_record()` is fully intact and unchanged.

## Activity Log

- 2026-03-20T14:42:47Z – system – lane=planned – Prompt created.
