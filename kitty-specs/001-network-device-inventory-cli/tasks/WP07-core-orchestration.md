---
work_package_id: WP07
title: Core Orchestration
lane: "planned"
dependencies:
- WP02
base_branch: 001-network-device-inventory-cli-WP02
base_commit: 3c75b0ab65d25f650d216b22a2fed18b9a8f9efe
created_at: '2026-03-13T16:00:19.344185+00:00'
subtasks:
- T019
- T020
- T021
- T022
- T023
phase: Phase 2 - Integration
assignee: ''
agent: "claude-sonnet-4-6"
shell_pid: "26684"
review_status: "has_feedback"
reviewed_by: "rpatel-hk"
review_feedback_file: "/private/var/folders/9q/_tbpgj3j6k5b3_6wcw8y8rpw0000gp/T/spec-kitty-review-feedback-WP07.md"
history:
- timestamp: '2026-03-12T10:45:33Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
requirement_refs:
- FR-001
- FR-002
- FR-005
- FR-006
- FR-007
- FR-008
- FR-011
- FR-012
- FR-013
---

# Work Package Prompt: WP07 – Core Orchestration

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check `review_status` above. If `has_feedback`, read the Review Feedback section first.

---

## Review Feedback

**Reviewed by**: rpatel-hk
**Status**: ❌ Changes Requested
**Date**: 2026-03-16
**Feedback file**: `/private/var/folders/9q/_tbpgj3j6k5b3_6wcw8y8rpw0000gp/T/spec-kitty-review-feedback-WP07.md`

# Review Feedback: WP07 — CHANGES REQUESTED

## Issue 1 (High): logger.py regressed — parameterized signature re-introduced

WP07 modified `network_inventory/utils/logger.py` back to the old parameterized form:

```python
# WP07 (WRONG — reverts WP02 fix)
def configure_logging(log_file: str = "inventory.log", log_level: str = "INFO") -> None:
```

WP02 fixed this to be a no-argument function that reads from the `settings` singleton:

```python
# WP02 correct version
from network_inventory.config import settings

def configure_logging() -> None:
    """Set up root logger handlers. Call once at application startup."""
    ...
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    file_handler = RotatingFileHandler(settings.log_file, ...)
```

`logger.py` must NOT be in WP07's deliverables at all — it was fixed in WP02 and should be
left untouched. Remove the change to `logger.py` from this WP.

## Issue 2 (High): main.py calls configure_logging() with arguments

Line 45 of `main.py`:

```python
configure_logging(log_file=settings.log_file, log_level=settings.log_level)
```

This must be changed to the no-arg call that matches the WP02 contract:

```python
configure_logging()
```

The settings-import order in `main.py` (load settings → configure_logging) also contradicts
the spec which calls `configure_logging()` first. However, since `configure_logging()` now
reads `settings` internally, the correct sequence in `main.py` is:

```python
from network_inventory.utils.logger import configure_logging, get_logger
try:
    from network_inventory.config import settings
except EnvironmentError as exc:
    print(f"Configuration error: {exc}", file=sys.stderr)
    sys.exit(1)
configure_logging()           # no args — reads settings internally
logger = get_logger(__name__)
```

## Issue 3 (Medium): .gitignore — Spec Kitty managed entries stripped

The WP07 diff removes the `# Added by Spec Kitty CLI (auto-managed)` block from `.gitignore`.
`logger.py` and `.gitignore` are both outside WP07's deliverable scope — do not touch either.

The `.gitignore` must retain the Spec Kitty entries (same fix as WP01):

```
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
```

## Required Actions

1. **Revert `logger.py`** to the WP02 state (no-arg, reads from `settings`). Either revert
   the file outright or exclude it from the WP07 commit entirely.
2. **Fix `main.py` line 45**: change `configure_logging(log_file=..., log_level=...)` → `configure_logging()`.
3. **Restore `.gitignore`**: prepend the Spec Kitty managed block back.
4. Re-commit and re-submit for review.

## Dependent Warning

WP08 stacks on WP07. Once this WP is fixed and merged, WP08 must rebase:
```
cd .worktrees/001-network-device-inventory-cli-WP08
git rebase 001-network-device-inventory-cli-WP07
```


## Objectives & Success Criteria

- `python network_inventory/main.py` runs end-to-end: loads devices, polls concurrently, writes results, prints summary.
- Any startup failure (missing env var, unreadable key file, DB connection failure) causes immediate `sys.exit(1)` with a clear error message — no partial execution.
- Every enabled device produces a row in `device_inventory` — no device is silently skipped or dropped.
- A single device failure does not abort the run; all other devices are polled.
- The completion summary matches the format specified in `quickstart.md`.

**Done when**:
- US1 acceptance scenario: populate `devices` table with ≥1 enabled device, run the CLI, verify `device_inventory` row with `status='success'`, non-null serial, non-null firmware, and printed summary.
- US2 acceptance scenario: add a device with wrong password, run CLI, verify `device_inventory` row with `status='failed'` and non-empty `error_message`.
- US3 acceptance scenario: `enabled=0` device has no row written or updated.

## Context & Constraints

- **Spec**: `kitty-specs/001-network-device-inventory-cli/spec.md` — FR-001, FR-002, FR-005, FR-006, FR-007, FR-008, FR-011, FR-012, FR-013; US1, US2, US3 acceptance scenarios; all edge cases
- **Quickstart**: `kitty-specs/001-network-device-inventory-cli/quickstart.md` — summary output format, run command
- **Plan**: `kitty-specs/001-network-device-inventory-cli/plan.md` — ThreadPoolExecutor pattern, `as_completed()` with `future_to_device` dict
- **Implement with**: `spec-kitty implement WP07 --base WP06`
- Depends on all prior WPs: config (WP01), models/utils (WP02), DB layer (WP03), collector registry (WP04), all collectors (WP05, WP06).
- Run command: `python network_inventory/main.py` (no CLI flags in v1).
- Logging configured before any other operation.

## Subtasks & Detailed Guidance

### Subtask T019 – Startup validation

**Purpose**: Validate all preconditions before any device polling begins. Any failure must exit immediately with a non-zero code and a descriptive message (FR-013).

**Startup sequence** (in `main.py`, top-level `main()` function):

```python
from network_inventory.utils.logger import configure_logging, get_logger
configure_logging()
logger = get_logger(__name__)
```

Then in order:

1. **Config already validated**: `settings` module-level singleton raises `EnvironmentError` at import if required vars are missing. Catch at top of `main()`:
   ```python
   try:
       from network_inventory.config import settings
   except EnvironmentError as exc:
       print(f"Configuration error: {exc}", file=sys.stderr)
       sys.exit(1)
   ```

2. **Key file check**: Before any DB or SSH operations:
   ```python
   from network_inventory.utils.encryption import load_key
   try:
       key = load_key(settings.encryption_key_file)
   except (FileNotFoundError, PermissionError, ValueError) as exc:
       logger.error("Encryption key error: %s", exc)
       sys.exit(1)
   ```

3. **DB connection pool**: `get_pool()` calls `sys.exit(1)` internally on failure (WP03) — calling it here triggers that fail-fast behaviour:
   ```python
   from network_inventory.db import get_pool
   get_pool()  # Exits if DB unreachable
   ```

**Files**:
- `network_inventory/main.py` (create)

**Validation**:
- [ ] With `ENCRYPTION_KEY_FILE` pointing to a non-existent path → exits with code 1, error logged.
- [ ] With wrong `DB_HOST` → exits with code 1 before loading any devices.
- [ ] All checks pass in order; subsequent steps only run if preceding checks pass.

---

### Subtask T020 – Device loading and zero-devices edge case

**Purpose**: Load enabled devices from the DB and handle the empty-list case gracefully.

**Steps** (inside `main()`):

```python
from network_inventory.db import get_connection, load_enabled_devices

conn = get_connection()
devices = load_enabled_devices(conn)
conn.close()  # Return to pool after load

if not devices:
    print("No enabled devices found. Nothing to poll.")
    logger.info("No enabled devices found — exiting.")
    sys.exit(0)

logger.info("Starting inventory run for %d device(s)", len(devices))
```

**Notes**:
- The device-loading connection is short-lived and returned to pool before ThreadPoolExecutor starts.
- `sys.exit(0)` on zero devices — clean exit, not an error (matches spec edge case).
- Disabled devices are never loaded (`WHERE enabled = 1` in SQL) — US3 is satisfied by DB layer.

**Validation**:
- [ ] With zero enabled devices → message printed, exit code 0.
- [ ] With `enabled=0` device in DB → not returned by `load_enabled_devices()`.

---

### Subtask T021 – Collector dispatch via ThreadPoolExecutor

**Purpose**: Submit all enabled devices to the thread pool, skipping any with unknown device_type (but still logging a warning per the collector registry).

**Steps**:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from network_inventory.collectors import get_collector

future_to_device: dict[Future, Device] = {}

with ThreadPoolExecutor(max_workers=settings.max_threads) as executor:
    for device in devices:
        collector_class = get_collector(device.device_type)
        if collector_class is None:
            # Warning already logged by get_collector(); no result record written
            logger.warning(
                "Skipping %s (%s) — device_type '%s' has no registered collector",
                device.hostname, device.ip_address, device.device_type,
            )
            continue

        collector = collector_class(device=device, key=key)
        future = executor.submit(collector.collect)
        future_to_device[future] = device
```

**Notes**:
- Devices with unknown `device_type` are skipped — no `CollectionResult` written for them (per spec edge case: "device is skipped with a logged warning; all other devices proceed normally").
- `collector.collect()` is the `BaseCollector.collect()` template method — it handles all SSH errors internally and always returns a `CollectionResult`.
- The `with executor` block waits for all futures before continuing.

**Validation**:
- [ ] Submitting a device with `device_type='unknown_xyz'` → warning logged, no future submitted.
- [ ] All known-type devices are submitted to the executor.
- [ ] ThreadPoolExecutor respects `settings.max_threads`.

---

### Subtask T022 – Result collection and DB upsert

**Purpose**: Iterate completed futures, extract results, write each to the DB, and accumulate summary counts. No future result is ever dropped.

**Steps** (inside the `with executor:` block, after futures are submitted):

```python
from network_inventory.db import get_connection, upsert_inventory_record

counts = {'success': 0, 'failed': 0, 'timeout': 0}

for future in as_completed(future_to_device):
    device = future_to_device[future]
    try:
        result: CollectionResult = future.result()
    except Exception as exc:
        # BaseCollector.collect() should never raise — but guard defensively
        from network_inventory.utils.error_handler import classify_exception
        from datetime import datetime
        status, error_message = classify_exception(exc)
        result = CollectionResult(
            device_id=device.id,
            status=status,
            attempted_at=datetime.utcnow(),
            error_message=f"Unexpected orchestrator error: {error_message}",
        )
        logger.error(
            "%s (%s) — unexpected future error: %s",
            device.hostname, device.ip_address, exc,
        )

    # Write to DB (main thread — thread-safe via new connection per write)
    write_conn = get_connection()
    try:
        upsert_inventory_record(write_conn, result)
    finally:
        write_conn.close()

    counts[result.status] += 1
    logger.info(
        "%s (%s) — %s",
        device.hostname, device.ip_address, result.status,
    )
```

**Thread safety note**:
- Each `upsert_inventory_record()` call acquires a fresh connection from the pool and closes it immediately after. This is safe because all DB writes happen in the main thread (after `future.result()` returns).
- Do NOT pass a shared connection object into worker threads.

**Partial data handling**:
- `CollectionResult.serial_number` and `.firmware_version` may be `None` — the upsert writes `NULL` for missing fields (per spec edge case: "available fields are stored and missing fields are left null").

**Validation**:
- [ ] Every submitted future produces a row in `device_inventory` (success + failure cases).
- [ ] `counts` totals equal the number of submitted futures.
- [ ] A future that raises unexpectedly still produces a `status='failed'` row.

---

### Subtask T023 – Completion summary and exit

**Purpose**: Print the human-readable summary to stdout and exit cleanly.

**Steps** (after the `with executor:` block):

```python
total = sum(counts.values())

print("\nInventory run complete.")
print(f"  Total polled : {total}")
print(f"  Success      : {counts['success']}")
print(f"  Failed       : {counts['failed']}")
print(f"  Timeout      : {counts['timeout']}")

logger.info(
    "Run complete — total=%d success=%d failed=%d timeout=%d",
    total, counts['success'], counts['failed'], counts['timeout'],
)

sys.exit(0)
```

**Full `main.py` entry point**:

```python
if __name__ == "__main__":
    main()
```

**Summary format** matches `quickstart.md`:
```
Inventory run complete.
  Total polled : 12
  Success      : 10
  Failed       : 1
  Timeout      : 1
```

**Validation**:
- [ ] Summary printed after all futures complete.
- [ ] `Total polled` equals `Success + Failed + Timeout`.
- [ ] Process exits with code 0 on normal completion.
- [ ] Summary format matches `quickstart.md` exactly (spacing, labels).

---

## Full `main.py` Structure (Reference)

```python
"""Network Device Inventory CLI — entry point."""
from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime

from network_inventory.models.device import CollectionResult, Device


def main() -> None:
    # 1. Logging
    # 2. Settings (config validation)
    # 3. Key file load
    # 4. DB pool init (fail-fast)
    # 5. Load enabled devices
    # 6. Zero-devices check
    # 7. Dispatch to ThreadPoolExecutor
    # 8. Collect results + upsert
    # 9. Print summary
    # 10. sys.exit(0)
    pass  # Replace with full implementation per T019–T023


if __name__ == "__main__":
    main()
```

## Risks & Mitigations

- **Future exception swallowing**: `BaseCollector.collect()` catches all exceptions internally. The defensive `try/except` around `future.result()` in T022 is a last-resort guard — never the primary path.
- **ThreadPoolExecutor not entering context**: If startup validation fails before the `with executor:` block, no threads are started and the process exits cleanly.
- **DB connection exhaustion**: Pool size = `max_threads + 2`. The main thread acquires one connection per upsert (after each `as_completed()` iteration) and releases it immediately. Workers don't hold DB connections — SSH only.
- **Unknown device_type devices**: These are not counted in `total` because no future is submitted for them. The operator sees only polled devices in the summary. This is correct per spec — skipped devices are not "polled".
- **Concurrency and `counts` dict**: `counts` is only modified in the main thread (inside `for future in as_completed(...)`) — no race condition.

## Review Guidance

- Trace the startup validation sequence: config → key file → DB pool — must be in this order.
- Verify that `sys.exit(0)` is called on zero-devices (not an error exit).
- Confirm `as_completed()` loop handles every submitted future, including ones that raise.
- Verify upsert connection is acquired and released within the same iteration of `as_completed()` loop.
- Check summary output spacing matches `quickstart.md` exactly.
- Run a manual end-to-end with one enabled device and confirm summary prints correctly.

## Activity Log

> **CRITICAL**: Append new entries at the END. Never prepend.

- 2026-03-12T10:45:33Z – system – lane=planned – Prompt created.
- 2026-03-13T16:00:20Z – claude-sonnet-4-6 – shell_pid=78396 – lane=doing – Assigned agent via workflow command
- 2026-03-13T16:02:40Z – claude-sonnet-4-6 – shell_pid=78396 – lane=for_review – T019-T023 complete: main() with ordered startup (logging→config→key file→DB pool→device load→dispatch→upsert→summary), ThreadPoolExecutor with future_to_device dict, defensive future.result() guard, per-write DB connection acquire/release in main thread, zero-devices exit 0, summary format matching quickstart.md
- 2026-03-16T16:31:26Z – claude-sonnet-4-6 – shell_pid=26684 – lane=doing – Started review via workflow command
- 2026-03-16T17:48:11Z – claude-sonnet-4-6 – shell_pid=26684 – lane=planned – Moved to planned
