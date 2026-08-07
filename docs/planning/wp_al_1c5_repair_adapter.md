# WP-AL-1C5 — Minimal Repair Adapter

**Status:** APPROVED — READY FOR PLANNING COMMIT

**Branch (proposed):** `feature/agent-loop-repair-adapter`
**Base:** `origin/main` @ `8472985e98d7979014153adb57d3d4dc7dd7ec82`
**Depends on:** WP-AL-1C1, WP-AL-1C2, WP-AL-1C3, WP-AL-1C4
**Precedes:** minimal orchestration wiring WP (earliest dogfooding milestone)

---

## 1. Status

**Status:** APPROVED — READY FOR PLANNING COMMIT

**Title:** WP-AL-1C5 — Minimal Repair Adapter

**Branch (proposed):** `feature/agent-loop-repair-adapter`

**Base:** `origin/main` @ `8472985e98d7979014153adb57d3d4dc7dd7ec82`

**Depends on:** WP-AL-1C1 (Review Contract), WP-AL-1C2 (Reviewer Adapter), WP-AL-1C3 (Review-Result Reporting Guard), WP-AL-1C4 (Repair Contract)

**Precedes:** Minimal orchestration wiring WP (earliest dogfooding milestone)

**Product Owner Approval:** APPROVED on 2026-08-06

All architectural decisions (DEC-C5-01 through DEC-C5-08) are RESOLVED. The reduced dogfooding-oriented scope is approved. The deferred-hardening boundary is approved. Implementation is not yet started. Planning must merge before the implementation branch is created.

---

## 2. Objective

Implement the **Minimal Repair Adapter**: a boundary component between the orchestrator and an external repair actor that:

1. Captures a clean tracked baseline before actor invocation.
2. Invokes a repair actor subprocess via JSON file paths.
3. Enforces timeout and bounds stdout/stderr capture.
4. Validates the WP-AL-1C4 repair result contract.
5. Produces an actual path inventory (added/modified/deleted/untracked).
6. Normalizes renames to delete + add.
7. Reconciles declared `changed_files` against actual workspace paths (exact match required).
8. Enforces `allowed_paths` and `forbidden_paths` against actual changes.
9. Produces a separate deterministic adapter-result artifact.
10. Does not auto-commit, reset, clean, stash, restore, or roll back.

This closes the Layer 2 enforcement gap deferred by WP-AL-1C4 §6.0.1.

### 2.1 Honest scope statement

The adapter provides **practical workspace integrity for dogfooding**, not complete workspace integrity. Specifically:

- **Inspected**: tracked files (via Git porcelain), untracked non-ignored files (via `git ls-files --others --exclude-standard`).
- **Not inspected**: files excluded by `.gitignore` patterns.
- **Not inspected**: files outside the repository root (handled by containment checks, not by active inspection).
- **Not inspected**: advanced symlink-target resolution beyond lexical and repository-boundary safety.

Complete workspace integrity — including ignored-file inspection, full symlink-target resolution, and production sandboxing — is deferred to a later hardening WP. This WP must not silently claim to deliver it.

---

## 3. Background

WP-AL-1C4 defined the repair-request and repair-result contracts but explicitly deferred workspace enforcement to a future adapter WP. The contract validates JSON artifact claims; it does not prove that the actual working tree matches those claims.

WP-AL-1C5 closes that gap with minimal scope appropriate for the earliest dogfooding milestone. It is the analog of WP-AL-1C2 (reviewer adapter) but adds workspace inspection and reconciliation responsibilities, because the repair actor modifies the workspace while the reviewer only reads it.

| WP-AL-1C2 (Review Adapter) | WP-AL-1C5 (Minimal Repair Adapter) |
|----------------------------|-------------------------------------|
| Invoke reviewer subprocess | Invoke repair actor subprocess |
| Validate review result | Validate repair result (WP-AL-1C4) |
| Publish canonical result | Publish adapter result with reconciliation |
| No workspace inspection | Inspect actual workspace changes |
| No reconciliation | Reconcile declared vs actual changes |
| No permission enforcement | Enforce allowed_paths/forbidden_paths on actual |

---

## 4. Source of Truth

### 4.1 Authoritative documents

| Document | Role |
|----------|------|
| `.agent-loop/repair/SCHEMA.md` | WP-AL-1C4 repair request/result contracts |
| `scripts/agent-loop/lib/repair_contract.py` | WP-AL-1C4 validator + builder |
| `scripts/agent-loop/lib/review_adapter.py` | WP-AL-1C2 adapter pattern reference |
| `scripts/agent-loop/lib/mock_reviewer.py` | WP-AL-1C2 mock pattern reference |
| `scripts/agent-loop/tests/run_harness_scenarios.sh` | Harness scenario registry |
| `.agent-loop/project.json` | Project structure and runtime policy |

### 4.2 Key invariants from WP-AL-1C4

- REPAIRED does NOT mean verification passed.
- Contract validation does NOT prove workspace integrity.
- The repair actor cannot define or expand `allowed_paths` or `forbidden_paths`.
- No PARTIAL status; only REPAIRED, NO_CHANGE, ERROR.

### 4.3 Key patterns from WP-AL-1C2

- `shell=False` in all subprocess calls.
- `start_new_session=True` for process group isolation.
- SIGTERM → 5s grace → SIGKILL escalation.
- Atomic file writes with `os.replace()`.
- Minimal environment, no inheritance.
- Bounded output reading.
- Error code taxonomy for adapter failures.
- Lock-based concurrency guard.

---

## 5. Definitions

| Term | Definition |
|------|------------|
| **Repair actor** | External subprocess that attempts to fix failures. Output is untrusted. |
| **Repair adapter** | This WP's component. Invokes the actor, validates the result, reconciles declared vs actual, enforces permissions. |
| **Orchestrator** | `run-story.sh` — trusted; owns retry and continuation decisions. |
| **Clean tracked baseline** | No pre-existing tracked modifications or staged changes. Required by WP-AL-1C5. |
| **Baseline-exclusion list** | Orchestrator-supplied list of explicitly approved pre-existing untracked artifacts excluded from inspection. |
| **Actual changes** | Files added, modified, deleted, or untracked in the workspace after actor invocation, compared to baseline. |
| **Declared changes** | `changed_files` array in the repair result artifact. |
| **Reconciliation** | Comparison of actual vs declared changes; requires exact match in WP-AL-1C5. |
| **Adapter result** | Separate artifact produced by the adapter, containing validated repair result summary + reconciliation metadata. |

---

## 6. Trust Model

| Component | Trust level | Confined by |
|-----------|-------------|-------------|
| Orchestrator (`run-story.sh`) | Trusted | — |
| Verifier (`verify-story.sh`) | Trusted | — |
| Reporter (`report-story.sh`) | Trusted | — |
| **Repair adapter (this WP)** | **Trusted** | Adapter contract |
| Repair actor (subprocess) | **Untrusted** | WP-AL-1C4 contract, adapter enforcement |
| Repair request | Trusted input | Built by orchestrator from validated manifest |
| Repair result (actor output) | **Untrusted** | WP-AL-1C4 contract validation |
| Workspace state | Observed fact | Git porcelain, filesystem checks |

### 6.1 Trust boundary rules

- The actor output is untrusted. The adapter validates facts, not intent.
- The actor cannot define or widen permissions.
- The actor cannot override the source revision.
- The adapter validates actual workspace state, not actor claims alone.
- The orchestrator owns retry and continuation decisions.

---

## 7. Architecture

### 7.1 Component structure

```
scripts/agent-loop/lib/repair_adapter.py
├── RepairAdapterResult (dataclass)
├── AdapterStatus (enum)
├── WorkspaceBaseline (dataclass)
├── WorkspaceChange (dataclass)
├── ReconciliationResult (dataclass)
├── run_repair() (main API)
├── _verify_clean_tracked_baseline()
├── _capture_workspace_baseline()
├── _capture_post_run_workspace()
├── _normalize_renames_to_delete_add()
├── _reconcile_changes()
├── _enforce_permissions()
├── _invoke_actor()
├── _validate_repair_result()
├── _build_adapter_result()
├── _build_minimal_env()
├── _atomic_write_json()
└── main() (CLI entry point)

scripts/agent-loop/lib/mock_repair_actor.py
├── Deterministic mock actor
├── REPAIRED / NO_CHANGE / ERROR modes
├── Configurable workspace modifications
└── Schema-compliant result format
```

### 7.2 Invocation flow

```
Orchestrator
    │
    ├─ Build repair request (WP-AL-1C4 builder)
    │
    ├─ Call run_repair()
    │   │
    │   ├─ Validate repair request (WP-AL-1C4 structural + referential)
    │   │
    │   ├─ Verify clean tracked baseline
    │   │   ├─ git rev-parse HEAD (must match source_revision)
    │   │   ├─ git status --porcelain=v1
    │   │   ├─ Reject if any tracked modifications or staged changes
    │   │   │   → ADAPTER_DIRTY_BASELINE
    │   │   └─ Apply baseline-exclusion list for known untracked artifacts
    │   │
    │   ├─ Build actor command (resolve executable, validate arguments)
    │   │
    │   ├─ Write repair request to $RUN_DIR/repair/repair-request.json
    │   │
    │   ├─ Invoke actor subprocess
    │   │   ├─ start_new_session=True, shell=False
    │   │   ├─ stdout/stderr → temp files (bounded)
    │   │   ├─ Timeout enforcement (SIGTERM → grace → SIGKILL)
    │   │   └─ On timeout: terminate, mark ADAPTER_TIMEOUT
    │   │
    │   ├─ If timeout/termination:
    │   │   ├─ May inspect resulting workspace for safety reporting
    │   │   ├─ Must NOT accept partial repair result as successful
    │   │   └─ Write adapter result with ADAPTER_TIMEOUT status
    │   │
    │   ├─ Read actor output
    │   │   ├─ Check for repair-result.json
    │   │   ├─ Parse JSON
    │   │   └─ Validate against WP-AL-1C4 contract
    │   │
    │   ├─ Capture post-run workspace
    │   │   ├─ git status --porcelain=v1 (all changes are new, baseline was clean)
    │   │   ├─ git ls-files --others --exclude-standard (untracked non-ignored)
    │   │   ├─ Normalize renames to delete + add
    │   │   └─ Exclude baseline-exclusion list entries
    │   │
    │   ├─ Reconcile declared vs actual
    │   │   ├─ Exact match required
    │   │   ├─ Any mismatch → hard failure
    │   │   └─ Build reconciliation result
    │   │
    │   ├─ Enforce permissions on actual changes
    │   │   ├─ Each actual change must match allowed_paths
    │   │   ├─ No actual change may match forbidden_paths
    │   │   └─ Forbidden wins over allowed
    │   │
    │   ├─ Build adapter result
    │   │   ├─ Include validated repair result summary
    │   │   ├─ Include reconciliation metadata
    │   │   ├─ Include workspace change inventory
    │   │   ├─ Include adapter status
    │   │   └─ Include bounded diagnostics
    │   │
    │   └─ Write adapter result to $RUN_DIR/repair/repair-adapter-result.json
    │
    └─ Return RepairAdapterResult
```

### 7.3 Separation of concerns

- **WP-AL-1C4 contract**: validates the repair result artifact structure.
- **WP-AL-1C5 adapter**: validates the repair result AND enforces workspace integrity.
- **Orchestrator (future WP)**: decides whether to retry, reverify, or abort.

---

## 8. Inputs

| Input | Type | Source | Purpose |
|-------|------|--------|---------|
| Repair request | `dict` | WP-AL-1C4 builder | Actor invocation parameters |
| `repo_root` | `Path` | Orchestrator | Workspace root |
| `run_dir` | `Path` | Orchestrator | Artifact directory |
| Actor executable | `str` | Orchestrator | Path to repair actor binary |
| Actor arguments | `list[str]` | Orchestrator | Command-line arguments |
| `timeout_seconds` | `int` | Orchestrator | Actor timeout (1–600, default 120) |
| `max_output_bytes` | `int` | Orchestrator | stdout/stderr capture limit (default 4096) |
| `baseline_exclusions` | `list[str]` | Orchestrator | Pre-existing untracked artifacts to exclude |

---

## 9. Outputs

### 9.1 Adapter result schema v1.0

```json
{
  "schema_version": "1.0",
  "run_id": "string",
  "story_id": "string",
  "attempt": 1,
  "adapter_status": "ADAPTER_SUCCESS | ADAPTER_TIMEOUT | ...",
  "repair_result_summary": {
    "status": "REPAIRED | NO_CHANGE | ERROR",
    "changed": true,
    "changed_files": ["path"],
    "recommended_action": "reverify | abort | human_review",
    "summary": "string (max 2048 bytes)"
  },
  "workspace_changes": {
    "baseline_source_revision": "40-char hex",
    "post_source_revision": "40-char hex",
    "source_revision_stable": true,
    "added": ["path"],
    "modified": ["path"],
    "deleted": ["path"],
    "untracked": ["path"]
  },
  "reconciliation": {
    "declared_files": ["path"],
    "actual_files": ["path"],
    "undeclared_changes": ["path"],
    "declared_but_missing": ["path"],
    "exact_match": true
  },
  "permission_enforcement": {
    "allowed_violations": ["path"],
    "forbidden_violations": ["path"],
    "all_actual_changes_permitted": true
  },
  "diagnostics": {
    "actor_exit_code": 0,
    "actor_stdout_tail": "string (max 4096 bytes)",
    "actor_stderr_tail": "string (max 4096 bytes)",
    "adapter_error_message": "string | null"
  },
  "sanitization": {
    "redaction_applied": false,
    "redaction_count": 0,
    "truncation_applied": false,
    "truncated_fields": []
  },
  "integrity_scope": {
    "tracked_files_inspected": true,
    "untracked_non_ignored_inspected": true,
    "ignored_files_inspected": false,
    "advanced_symlink_inspected": false,
    "note": "String: short explanation of scope limitations"
  },
  "completed_at": "2026-08-06T12:00:00Z"
}
```

### 9.2 Integrity scope disclaimer

The `integrity_scope` field explicitly records what the adapter inspected and what it did not. Consumers (orchestrator, reviewers, humans) must not interpret the adapter result as proof of complete workspace integrity.

### 9.3 Rename normalization

Renames reported by Git porcelain are normalized to two entries: one delete (old path) and one add (new path). Both paths appear in the workspace inventory and are subject to permission checks independently. Rename identity is not preserved; this is deferred to a later hardening WP.

---

## 10. Invocation Contract

### 10.1 Subprocess protocol

```python
proc = subprocess.Popen(
    [actor_executable] + actor_arguments,
    stdout=stdout_fd,
    stderr=stderr_fd,
    cwd=str(repo_root),
    env=minimal_env,
    start_new_session=True,
    close_fds=True,
    shell=False,
)
```

### 10.2 Argument contract

The actor receives `--repair-request <path>` (path to repair-request.json).

### 10.3 Environment contract

Minimal environment: `PATH` (reduced), `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`. No inherited environment. No secrets.

### 10.4 Timeout and output limits

- Timeout: 1–600 seconds (configurable, default 120).
- On timeout: SIGTERM → 5s grace → SIGKILL.
- After termination, the adapter may inspect the resulting workspace for safety reporting, but must NOT accept any partial repair result as successful.
- Output capture: 4096 bytes max for stdout/stderr tails.

### 10.5 Exit code semantics

| Exit code | Interpretation |
|-----------|----------------|
| 0 | Actor completed (result may still be invalid) |
| Non-zero | Actor failed (ADAPTER_NON_ZERO_EXIT) |

The adapter does not interpret specific non-zero codes.

### 10.6 Malformed or missing result

- No `repair-result.json`: `ADAPTER_MISSING_RESULT`.
- Not valid JSON: `ADAPTER_MALFORMED_RESULT`.
- Fails WP-AL-1C4 validation: `ADAPTER_CONTRACT_VIOLATION` or `ADAPTER_IDENTITY_MISMATCH`.

---

## 11. Workspace Baseline

### 11.1 Clean tracked baseline requirement

Before invocation, the adapter verifies:

1. `git rev-parse HEAD` matches `request.source_revision`.
2. `git status --porcelain=v1` reports no tracked modifications or staged changes.

If any tracked modifications or staged changes exist: `ADAPTER_DIRTY_BASELINE`.

**This WP does not support dirty tracked baselines.** Dirty-baseline manifests are deferred to a later hardening WP.

### 11.2 Baseline-exclusion list

The orchestrator may supply `baseline_exclusions` — explicitly approved pre-existing untracked artifacts to exclude from inspection.

- Each entry is a repo-relative path.
- Excluded files do not appear in the baseline snapshot.
- Excluded files do not appear in post-run workspace inspection.
- The adapter never cleans, stashes, resets, restores, or deletes excluded files.

### 11.3 Baseline snapshot structure

```python
WorkspaceBaseline:
    source_revision: str           # 40-char hex
    baseline_exclusions: list[str] # excluded untracked paths
    captured_at: str               # ISO-8601 UTC
```

---

## 12. Workspace Inspection

### 12.1 Post-invocation capture

After actor invocation, the adapter captures:

1. `git rev-parse HEAD` — must match baseline source revision.
2. `git status --porcelain=v1` — all tracked changes (since baseline was clean, all are new).
3. `git ls-files --others --exclude-standard` — untracked non-ignored files.

### 12.2 Change classification

| Git status code | Classification |
|----------------|----------------|
| `??` (untracked) | Added to untracked list |
| `M` (modified) | Modified |
| `A` (added, staged) | Added |
| `D` (deleted) | Deleted |
| `R` (renamed) | Normalized to delete + add |
| `C` (copied) | Added (copy destination) |

### 12.3 Rename normalization

Git porcelain `R  old → new` is normalized to:
- Delete: `old`
- Add: `new`

Both paths are subject to permission checks independently.

### 12.4 Ignored files

Ignored files (matching `.gitignore`) are excluded via `git ls-files --others --exclude-standard`. This WP does **not** inspect ignored files. This limitation is recorded in `integrity_scope.ignored_files_inspected = false`.

---

## 13. Reconciliation Rules

### 13.1 Exact match requirement

The adapter requires exact match between declared `changed_files` and actual workspace changes.

- `declared == actual` → `exact_match = true`.
- Any mismatch → adapter failure (hard failure, not configurable).

### 13.2 Mismatch detection

| Condition | Adapter status |
|-----------|----------------|
| `actual ⊂ declared` (declared-but-missing) | `ADAPTER_DECLARED_MISSING` |
| `declared ⊂ actual` (undeclared) | `ADAPTER_UNDECLARED_CHANGE` |
| Both | `ADAPTER_UNDECLARED_CHANGE` (primary) |
| `declared == actual` | Success |

### 13.3 Reconciliation result

```python
ReconciliationResult:
    declared_files: list[str]     # sorted
    actual_files: list[str]       # sorted
    undeclared_changes: list[str] # actual - declared
    declared_but_missing: list[str] # declared - actual
    exact_match: bool
```

### 13.4 Empty reconciliation

- `NO_CHANGE` with no actual changes: trivially successful.
- `NO_CHANGE` with actual changes: `ADAPTER_UNDECLARED_CHANGE`.
- `REPAIRED` with no actual changes: `ADAPTER_DECLARED_MISSING`.
- `ERROR`: reconciliation skipped (adapter status reflects actor failure).

---

## 14. Path and Permission Enforcement

### 14.1 Allowed-paths check

Each actual workspace change must match at least one `allowed_paths` pattern (if non-empty). Gitwildmatch semantics. Violations → `permission_enforcement.allowed_violations` → `ADAPTER_FORBIDDEN_CHANGE`.

### 14.2 Forbidden-paths check

No actual workspace change may match any `forbidden_paths` pattern. Forbidden takes precedence over allowed. Violations → `permission_enforcement.forbidden_violations` → `ADAPTER_FORBIDDEN_CHANGE`.

### 14.3 Path safety

All actual changes must be under `repo_root`. The adapter verifies:
- No path contains `..` traversal.
- No absolute paths.
- No null bytes.
- No Windows drive letters or UNC paths.
- Lexical repository-boundary check on resolved paths.

Violations → `ADAPTER_INTERNAL_ERROR`.

### 14.4 Symlink handling in WP-AL-1C5

The adapter performs lexical path safety and repository-boundary checks. Advanced symlink-target inspection (resolving and verifying symlink targets) is deferred to a later hardening WP. This limitation is recorded in `integrity_scope.advanced_symlink_inspected = false`.

---

## 15. Dirty-Worktree Policy

### 15.1 Tracked worktree

WP-AL-1C5 **requires a clean tracked worktree**. Pre-existing tracked modifications or staged changes cause `ADAPTER_DIRTY_BASELINE`.

Dirty-baseline manifests (allowing declared pre-existing tracked changes) are deferred.

### 15.2 Untracked files

Pre-existing untracked files:
- In `baseline_exclusions`: excluded from baseline and post-run inspection.
- Not in `baseline_exclusions`: cause `ADAPTER_DIRTY_BASELINE` before actor invocation (DEC-R1 fail-closed). The actor is not invoked in this case.

> **DEC-R1 supersession note:** An earlier version of this section allowed non-excluded pre-existing untracked files at baseline time, treating them as potential actor changes that would trigger `ADAPTER_UNDECLARED_CHANGE` during post-run reconciliation. That allowance was superseded by DEC-R1 during PR #56 remediation. The fail-closed policy is now authoritative: exclusions are required for any permitted pre-existing untracked paths. Actor-created new untracked paths still participate in post-run reconciliation.

### 15.3 Ignored files

Ignored files (`.gitignore`) are never inspected. This is a documented limitation.

### 15.4 Adapter non-interference

The adapter never cleans, stashes, resets, restores, or deletes any files — whether pre-existing, excluded, or actor-produced. It only reads workspace state.

---

## 16. Failure Taxonomy

### 16.1 Adapter status codes

| Status | Category | Description |
|--------|----------|-------------|
| `ADAPTER_SUCCESS` | Success | Adapter completed normally |
| `ADAPTER_DIRTY_BASELINE` | Baseline | Pre-existing tracked modifications found |
| `ADAPTER_TIMEOUT` | Invocation | Actor exceeded timeout |
| `ADAPTER_NON_ZERO_EXIT` | Invocation | Actor exited non-zero |
| `ADAPTER_MISSING_RESULT` | Invocation | No result file produced |
| `ADAPTER_MALFORMED_RESULT` | Validation | Invalid JSON |
| `ADAPTER_CONTRACT_VIOLATION` | Validation | Fails WP-AL-1C4 validation |
| `ADAPTER_IDENTITY_MISMATCH` | Validation | Identity does not match request |
| `ADAPTER_SOURCE_REVISION_DRIFT` | Workspace | Source revision changed |
| `ADAPTER_FORBIDDEN_CHANGE` | Enforcement | Permission violation |
| `ADAPTER_UNDECLARED_CHANGE` | Enforcement | Actual change not declared |
| `ADAPTER_DECLARED_MISSING` | Enforcement | Declared change not actual |
| `ADAPTER_OUTPUT_SIZE_EXCEEDED` | Invocation | Output exceeded limits |
| `ADAPTER_INTERNAL_ERROR` | Adapter | Infrastructure failure |

### 16.2 Priority order

When multiple failures occur:

1. `ADAPTER_INTERNAL_ERROR`
2. `ADAPTER_DIRTY_BASELINE`
3. `ADAPTER_SOURCE_REVISION_DRIFT`
4. `ADAPTER_FORBIDDEN_CHANGE`
5. `ADAPTER_UNDECLARED_CHANGE`
6. `ADAPTER_DECLARED_MISSING`
7. `ADAPTER_CONTRACT_VIOLATION`
8. `ADAPTER_IDENTITY_MISMATCH`
9. `ADAPTER_MALFORMED_RESULT`
10. `ADAPTER_MISSING_RESULT`
11. `ADAPTER_NON_ZERO_EXIT`
12. `ADAPTER_TIMEOUT`
13. `ADAPTER_OUTPUT_SIZE_EXCEEDED`

### 16.3 Repair result preservation

Even when the adapter fails, the adapter preserves the original repair result (if available) in the adapter result summary. This allows the orchestrator to inspect the actor's claim even if rejected.

---

## 17. Determinism and Sanitization

### 17.1 Determinism rules

- No `datetime.now()` or `time.time()` calls.
- All timestamps supplied by caller.
- Canonical JSON is deterministic.
- Workspace changes sorted lexicographically.

### 17.2 Sanitization pipeline

Same as WP-AL-1C4: UTF-8 normalization, binary detection, control char removal, base64 detection, secret redaction, URL query stripping, byte truncation. Sanitization metadata populated accurately.

---

## 18. Scope

### 18.1 IN SCOPE

- Repair actor invocation adapter via subprocess with JSON file paths.
- WP-AL-1C4 request/result integration.
- Clean tracked baseline verification.
- Bounded process execution with timeout.
- Result artifact validation (WP-AL-1C4 contract).
- Post-invocation workspace inspection (tracked + untracked non-ignored).
- Rename normalization to delete + add.
- Declared-versus-actual reconciliation (exact match required).
- Permission enforcement on actual workspace changes.
- Separate deterministic adapter-result artifact.
- Integrity-scope disclaimer field.
- Baseline-exclusion list for approved pre-existing untracked artifacts.
- Deterministic mock repair actor.
- Unit tests (U, W, S, B, M series).
- Adapter-specific harness scenarios (Y, Z, AA).
- Documentation (adapter schema, README, next_steps, planning doc).

### 18.2 OUT OF SCOPE (not implemented in this WP)

- Orchestrator retry loop wiring.
- Automatic re-verification after repair.
- Model/provider selection.
- Prompt design for the repair actor.
- Production sandbox/container isolation.
- Automatic commits.
- Automatic rollback.
- Multi-agent repair competition.
- Changes to review adapter behavior.
- WP-AL-1C6 or later work.

### 18.3 DEFERRED TO LATER HARDENING WP

These items are explicitly deferred and must not be silently claimed as complete in WP-AL-1C5:

- Dirty tracked baseline manifests (allowing pre-existing tracked changes with declared exceptions).
- Preserved rename identity in workspace inventory.
- Full filesystem snapshot engine beyond Git porcelain.
- Ignored-file inspection.
- Advanced symlink-target inspection beyond lexical/repository-boundary safety.
- Configurable declared-versus-actual mismatch tolerance.
- Partial repair acceptance after timeout.
- Production sandbox/container isolation.
- Orchestrator retry and reverify wiring.
- Automatic rollback.
- Concurrency and parallel worker integration.

### 18.4 FORBIDDEN

- Actor-controlled permission expansion.
- Silent cleanup of unrelated user changes.
- `git reset`, `git clean`, `git stash`, `git restore`.
- Automatic commit/push/merge.
- Force operations.
- Writing outside `repo_root` or `run_dir`.
- Treating REPAIRED as verification success.
- Trusting actor-declared `changed_files` without actual inspection.
- Claiming complete workspace integrity (ignored files not inspected).

---

## 19. Expected Files

### 19.1 New files

| Path | Purpose |
|------|---------|
| `.agent-loop/repair-adapter/SCHEMA.md` | Adapter result schema v1.0 documentation |
| `scripts/agent-loop/lib/repair_adapter.py` | Adapter implementation |
| `scripts/agent-loop/lib/mock_repair_actor.py` | Mock repair actor for tests |
| `scripts/agent-loop/tests/test_repair_adapter.py` | All adapter tests (including mock actor tests) |
| `docs/planning/wp_al_1c5_repair_adapter.md` | This planning document |

**File-scope rationale:**

- `.agent-loop/repair-adapter/SCHEMA.md` — kept. The adapter result is a distinct machine-readable contract from the WP-AL-1C4 repair result. It has different fields (`adapter_status`, `workspace_changes`, `reconciliation`, `permission_enforcement`, `integrity_scope`). Separate schema documentation follows the pattern of `.agent-loop/repair/SCHEMA.md` (WP-AL-1C4) and `.agent-loop/review-adapter/SCHEMA.md` (WP-AL-1C2).
- `test_repair_actor.py` — no separate mock test file. Mock actor behavior (modes, determinism, workspace modifications) is covered within `test_repair_adapter.py`. This reduces file count while keeping test IDs traceable.

### 19.2 Modified files (proposed, not modified in this planning session)

| Path | Change |
|------|--------|
| `docs/next_steps.md` | Record WP-AL-1C5 planning and completion |
| `scripts/agent-loop/README.md` | Document WP-AL-1C5 completion |

---

## 20. Forbidden Files

The following files must NOT be modified by WP-AL-1C5:

- `scripts/agent-loop/run-story.sh`
- `scripts/agent-loop/verify-story.sh`
- `scripts/agent-loop/report-story.sh`
- `scripts/agent-loop/lib/repair_contract.py`
- `scripts/agent-loop/lib/review_contract.py`
- `scripts/agent-loop/lib/review_adapter.py`
- `scripts/agent-loop/lib/mock_reviewer.py`
- `scripts/agent-loop/lib/failure_context.py`
- `scripts/agent-loop/lib/review_result_reporting.py`
- `.agent-loop/repair/SCHEMA.md`
- `.agent-loop/review/SCHEMA.md`
- `.agent-loop/review-adapter/SCHEMA.md`
- `.agent-loop/failure-context/SCHEMA.md`
- `.agent-loop/manifests/SCHEMA.md`
- `.agent-loop/gates.json`
- `.agent-loop/project.json`
- `backend/**`, `frontend/**`, `docker/**`
- `forgemind_project_source_of_truth/**`
- `.env`, `.env.*`, `*.pem`, `*.key`
- Gate implementations (`lib/{scope.sh,tests.sh,harness.py,manifest_loader.py,config_loader.py,guard.sh,passport.py,artifacts.sh,env.sh}`)

---

## 21. Product Decisions

### DEC-C5-01 — Invocation transport

**Decision:** APPROVED — Option A.

Subprocess invocation with JSON file paths. Matches WP-AL-1C2 pattern. File-based I/O is crash-safe (atomic writes).

**Status:** RESOLVED

---

### DEC-C5-02 — Baseline policy

**Decision:** APPROVED — Option A.

Require a clean tracked baseline for WP-AL-1C5. Pre-existing tracked modifications or staged changes cause `ADAPTER_DIRTY_BASELINE`. Pre-existing explicitly approved untracked artifacts may be excluded via an orchestrator-provided baseline-exclusion list. The adapter must never clean, stash, reset, restore, or delete those files.

Dirty-worktree manifests (allowing declared pre-existing tracked changes) are deferred to a later hardening WP.

**Status:** RESOLVED

---

### DEC-C5-03 — Workspace diff source

**Decision:** APPROVED — Option A with minimal scope.

Use Git porcelain/status and Git diff, supplemented only by narrowly required filesystem checks for untracked files and path safety. No full filesystem snapshot engine.

**Status:** RESOLVED

---

### DEC-C5-04 — Rename handling

**Decision:** APPROVED — Option B.

Normalize renames to delete + add for reconciliation and permission checks. Preserving rename identity is deferred to a later hardening WP.

**Status:** RESOLVED

---

### DEC-C5-05 — Untracked file policy

**Decision:** APPROVED — Option C.

Exclude ignored files and include all other untracked files.

Documented limitation: ignored-file enforcement is deferred and must not be silently claimed as complete workspace integrity. This limitation is recorded in the adapter result's `integrity_scope.ignored_files_inspected = false` field.

**Status:** RESOLVED

---

### DEC-C5-06 — Declared-versus-actual mismatch policy

**Decision:** APPROVED — Option A.

Any declared-versus-actual mismatch is a hard adapter failure. No configurable mismatch policy in WP-AL-1C5.

**Status:** RESOLVED

---

### DEC-C5-07 — Timeout behavior

**Decision:** APPROVED — Option A.

Terminate on timeout and report adapter failure. The adapter may inspect resulting workspace changes for safety reporting after termination, but must not accept a partial repair result as successful.

**Status:** RESOLVED

---

### DEC-C5-08 — Adapter output contract

**Decision:** APPROVED — Option A.

Produce a separate adapter-result artifact. The adapter result may reference or embed a validated summary of the WP-AL-1C4 repair result, but the two contracts remain distinct.

**Status:** RESOLVED

---

## 22. Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-01 | Adapter invokes actor subprocess via JSON file paths (DEC-C5-01). |
| AC-02 | Adapter verifies clean tracked baseline before invocation (DEC-C5-02). |
| AC-03 | Adapter rejects pre-existing tracked modifications or staged changes with ADAPTER_DIRTY_BASELINE. |
| AC-04 | Adapter applies baseline-exclusion list for approved pre-existing untracked artifacts. |
| AC-05 | Adapter never cleans, stashes, resets, restores, or deletes any files. |
| AC-06 | Adapter enforces timeout with SIGTERM → grace → SIGKILL. |
| AC-07 | On timeout, adapter may inspect workspace for safety reporting but does not accept partial result. |
| AC-08 | Adapter enforces output size limits (stdout/stderr tails). |
| AC-09 | Adapter validates repair result against WP-AL-1C4 contract. |
| AC-10 | Adapter validates identity binding (run_id, story_id, attempt, source_revision match). |
| AC-11 | Adapter captures actual workspace changes (added, modified, deleted, untracked). |
| AC-12 | Adapter normalizes renames to delete + add (DEC-C5-04). |
| AC-13 | Adapter reconciles declared vs actual with exact match required (DEC-C5-06). |
| AC-14 | Adapter detects undeclared changes (hard failure). |
| AC-15 | Adapter detects declared-but-missing changes (hard failure). |
| AC-16 | Adapter enforces allowed_paths on actual changes (gitwildmatch). |
| AC-17 | Adapter enforces forbidden_paths on actual changes (forbidden wins). |
| AC-18 | Adapter excludes ignored files from inspection (DEC-C5-05). |
| AC-19 | Adapter records integrity scope explicitly (`integrity_scope` field). |
| AC-20 | Adapter does not claim complete workspace integrity in documentation or output. |
| AC-21 | Adapter produces separate adapter-result artifact (DEC-C5-08). |
| AC-22 | Adapter produces deterministic output (same inputs → same output). |
| AC-23 | Adapter sanitizes actor output using WP-AL-1C4 sanitization pipeline. |
| AC-24 | Adapter does not leak secrets in diagnostics or error messages. |
| AC-25 | Adapter does not auto-commit, reset, clean, stash, restore, or roll back. |
| AC-26 | Adapter does not invoke orchestration logic (no retry, no reverify). |
| AC-27 | Adapter uses shell=False in all subprocess calls. |
| AC-28 | Adapter uses start_new_session=True for process group isolation. |
| AC-29 | Adapter uses atomic file writes (tmp + os.replace). |
| AC-30 | Adapter uses minimal environment (no inherited secrets). |
| AC-31 | Adapter result schema v1.0 documented at `.agent-loop/repair-adapter/SCHEMA.md`. |
| AC-32 | Existing harness scenarios A–X remain 24/24 PASS. |
| AC-33 | New harness scenarios Y, Z, AA pass. |
| AC-34 | `ruff check` clean for new/modified Python files. |
| AC-35 | `mypy --strict` clean for new/modified Python files. |
| AC-36 | No modification to forbidden files. |
| AC-37 | No LLM invocation, no network access, no shell interpolation. |
| AC-38 | Planning document reviewed and approved before implementation. |

---

## 23. Test Matrix

### 23.1 U-series: Unit validation and process behavior (23 tests)

| ID | Case | Expected |
|----|------|----------|
| U01 | Valid REPAIRED result with matching actual diff | ADAPTER_SUCCESS |
| U02 | Valid NO_CHANGE result with no actual diff | ADAPTER_SUCCESS |
| U03 | Valid ERROR result | ADAPTER_SUCCESS (actor failed, adapter succeeded) |
| U04 | Actor timeout | ADAPTER_TIMEOUT |
| U05 | Actor non-zero exit | ADAPTER_NON_ZERO_EXIT |
| U06 | Missing result file | ADAPTER_MISSING_RESULT |
| U07 | Malformed JSON result | ADAPTER_MALFORMED_RESULT |
| U08 | Invalid WP-AL-1C4 contract (wrong schema_version) | ADAPTER_CONTRACT_VIOLATION |
| U09 | Identity mismatch (run_id) | ADAPTER_IDENTITY_MISMATCH |
| U10 | Source revision drift (pre-invocation) | ADAPTER_SOURCE_REVISION_DRIFT |
| U11 | Source revision drift (post-invocation) | ADAPTER_SOURCE_REVISION_DRIFT |
| U12 | Output size exceeded (stdout) | ADAPTER_OUTPUT_SIZE_EXCEEDED |
| U13 | Adapter deterministic output (same inputs twice) | Identical adapter result |
| U14 | Secret pattern in actor stderr | Redacted in diagnostics |
| U15 | Actor produces REPAIRED with changed_files | Adapter validates contract |
| U16 | Actor produces NO_CHANGE with empty changed_files | Adapter validates contract |
| U17 | Actor exit code 0 but no result file | ADAPTER_MISSING_RESULT |
| U18 | Actor exit code 1 with valid result file | ADAPTER_NON_ZERO_EXIT |
| U19 | Result with duplicate changed_files | ADAPTER_CONTRACT_VIOLATION |
| U20 | Result with absolute path in changed_files | ADAPTER_CONTRACT_VIOLATION |
| U21 | Result with oversized summary | ADAPTER_CONTRACT_VIOLATION |
| U22 | shell=False in subprocess call | Verified |
| U23 | start_new_session=True and minimal environment | Verified |

### 23.2 W-series: Workspace diff and reconciliation (14 tests)

| ID | Case | Expected |
|----|------|----------|
| W01 | REPAIRED with exact matching actual diff | exact_match = true |
| W02 | NO_CHANGE with no actual diff | exact_match = true |
| W03 | Actual contains undeclared change | ADAPTER_UNDECLARED_CHANGE |
| W04 | Actual missing declared change | ADAPTER_DECLARED_MISSING |
| W05 | Both undeclared and declared-missing | ADAPTER_UNDECLARED_CHANGE (primary) |
| W06 | Actual is subset of declared | ADAPTER_DECLARED_MISSING |
| W07 | Actual is superset of declared | ADAPTER_UNDECLARED_CHANGE |
| W08 | Untracked file in actual changes | Included in reconciliation |
| W09 | Rename normalized to delete + add | Both paths in inventory |
| W10 | Delete in actual changes | Detected and reconciled |
| W11 | Baseline exclusion (orchestrator-supplied) | Excluded from reconciliation |
| W12 | Clean baseline (no pre-existing changes) | Adapter succeeds |
| W13 | Reconciliation result (exact match) | undeclared = [], declared_missing = [] |
| W14 | Reconciliation result (both mismatches) | undeclared = [extra], declared_missing = [missing] |

### 23.3 S-series: Security and path enforcement (11 tests)

| ID | Case | Expected |
|----|------|----------|
| S01 | Actual change matches allowed_paths | Permitted |
| S02 | Actual change does not match allowed_paths | ADAPTER_FORBIDDEN_CHANGE |
| S03 | Actual change matches forbidden_paths | ADAPTER_FORBIDDEN_CHANGE |
| S04 | Actual change matches both allowed and forbidden | ADAPTER_FORBIDDEN_CHANGE (forbidden wins) |
| S05 | Path with parent traversal (..) | ADAPTER_INTERNAL_ERROR |
| S06 | Absolute path in actual changes | ADAPTER_INTERNAL_ERROR |
| S07 | Lexical repository-boundary escape | ADAPTER_INTERNAL_ERROR |
| S08 | No secrets in diagnostics | Verified |
| S09 | No absolute paths in diagnostics | Verified |
| S10 | Minimal environment (no inherited secrets) | Verified |
| S11 | Atomic write for adapter result | Verified |

### 23.4 B-series: Boundary and failure behavior (9 tests)

| ID | Case | Expected |
|----|------|----------|
| B01 | Timeout boundary (1 second) | ADAPTER_TIMEOUT |
| B02 | Timeout boundary (600 seconds) | ADAPTER_TIMEOUT |
| B03 | Output size boundary (4096 bytes) | Truncated |
| B04 | Empty result file | ADAPTER_MALFORMED_RESULT |
| B05 | Internal error (repo_root missing) | ADAPTER_INTERNAL_ERROR |
| B06 | Internal error (run_dir missing) | ADAPTER_INTERNAL_ERROR |
| B07 | Concurrent adapter invocation (lock) | ADAPTER_INTERNAL_ERROR |
| B08 | Actor killed by signal (not timeout) | ADAPTER_NON_ZERO_EXIT |
| B09 | Dirty tracked baseline (pre-existing modification) | ADAPTER_DIRTY_BASELINE |

### 23.5 M-series: Mock repair actor (6 tests)

| ID | Case | Expected |
|----|------|----------|
| M01 | Mock actor REPAIRED mode | Produces valid result, modifies declared files |
| M02 | Mock actor NO_CHANGE mode | Produces valid result, no modifications |
| M03 | Mock actor ERROR mode | Produces valid ERROR result |
| M04 | Mock actor deterministic output | Same inputs → same result |
| M05 | Mock actor workspace modifications | Files modified match changed_files |
| M06 | Mock actor schema compliance | Result passes WP-AL-1C4 validation |

**Note:** M-series tests are included in `test_repair_adapter.py` (no separate mock test file).

### 23.6 H-series: Harness scenarios (exactly 3)

| ID | Name | Purpose | Actor behavior | Expected adapter outcome |
|----|------|---------|----------------|--------------------------|
| H01 | Scenario Y | Successful REPAIRED with matching diff | Produces valid result, modifies declared files | ADAPTER_SUCCESS |
| H02 | Scenario Z | NO_CHANGE with no diff | Produces valid result, no modifications | ADAPTER_SUCCESS |
| H03 | Scenario AA | Safety failure (undeclared or forbidden change) | Produces valid result, modifies undeclared/forbidden file | ADAPTER_UNDECLARED_CHANGE or ADAPTER_FORBIDDEN_CHANGE |

### 23.7 Test counts

| Series | Count |
|--------|-------|
| U-series | 23 |
| W-series | 14 |
| S-series | 11 |
| B-series | 9 |
| M-series | 6 |
| H-series | 3 |
| **Total** | **66** |

Actual pytest item count may differ based on parametrization.

---

## 24. Harness Plan

### 24.1 Proposed scenarios (exactly 3)

| Letter | Name | Purpose |
|--------|------|---------|
| Y | repair-success | Happy path: REPAIRED with exact matching diff |
| Z | repair-no-change | NO_CHANGE with no actual diff |
| AA | repair-safety-failure | Undeclared or forbidden actual change |

### 24.2 Existing scenarios

Scenarios A–X (24 scenarios) remain unchanged and must continue to pass.

### 24.3 Total after WP-AL-1C5

A through AA = 27 scenarios.

### 24.4 Deferred harness scenarios

Timeout, malformed output, and non-zero exit remain unit/integration tests (U-series, B-series) unless a future WP proves them essential as harness scenarios.

---

## 25. Implementation Sequence

### 25.1 Staged implementation

1. **Adapter result schema** (`.agent-loop/repair-adapter/SCHEMA.md`)
   - Adapter result schema v1.0
   - Adapter status taxonomy
   - Reconciliation metadata schema
   - Workspace change schema
   - Integrity-scope schema

2. **Process runner** (`repair_adapter.py`)
   - Subprocess invocation
   - Timeout handling
   - Output capture

3. **Clean baseline verification** (`repair_adapter.py`)
   - Source revision check
   - Clean tracked baseline check
   - Baseline-exclusion list handling

4. **Post-run workspace capture** (`repair_adapter.py`)
   - Workspace inspection (tracked + untracked non-ignored)
   - Change classification (added/modified/deleted/untracked)
   - Rename normalization to delete + add
   - Baseline-exclusion list filtering

5. **Reconciliation** (`repair_adapter.py`)
   - Declared-vs-actual comparison
   - Exact match enforcement
   - Reconciliation result

6. **Permission enforcement** (`repair_adapter.py`)
   - Allowed-paths check on actual changes
   - Forbidden-paths check on actual changes

7. **Sanitization and diagnostics** (`repair_adapter.py`)
   - Actor output sanitization
   - Sanitization metadata
   - Integrity-scope field

8. **Mock repair actor** (`mock_repair_actor.py`)
   - Deterministic mock actor
   - REPAIRED / NO_CHANGE / ERROR modes
   - Configurable workspace modifications

9. **Unit tests** (`test_repair_adapter.py`)
   - U-series, W-series, S-series, B-series, M-series tests

10. **Harness scenarios** (`run_harness_scenarios.sh`)
    - Scenarios Y, Z, AA

11. **Documentation** (`README.md`, `next_steps.md`)
    - WP-AL-1C5 completion

12. **Independent review**
    - Product Owner review
    - Address feedback
    - Merge upon approval

### 25.2 Stop gates

- After step 1: Schema review.
- After step 9: All unit tests pass, ruff/mypy clean.
- After step 10: All harness scenarios A–AA pass.
- After step 12: PO approval required for merge.

---

## 26. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Scope creep into orchestration | Medium | High | Strict forbidden-files list; stop condition if orchestration code appears |
| Clean baseline requirement too restrictive | Medium | Medium | Baseline-exclusion list for approved untracked artifacts; deferred dirty-baseline manifests |
| Reconciliation edge cases | Medium | Medium | Comprehensive test matrix (W-series); exact match semantics |
| Permission enforcement complexity | Low | High | Reuse gitwildmatch from harness.py; same as WP-AL-1C4 |
| Mock actor complexity | Low | Low | Match WP-AL-1C2 mock_reviewer pattern; keep simple |
| Incomplete workspace integrity misinterpretation | Low | High | Explicit `integrity_scope` field; honest documentation |

---

## 27. Stop Conditions

Stop and report if:

- Any file outside allowed paths is modified.
- Any test in the existing A–X harness suite fails.
- `ruff` or `mypy --strict` reports errors on new Python files.
- Any secret, absolute path, or path traversal appears in output.
- `run-story.sh`, `verify-story.sh`, or `report-story.sh` is modified.
- Any WP-AL-1C1/1C2/1C3/1C4 file is modified.
- Any LLM or network call is introduced.
- The scope expands into orchestration, retry, or reverify logic.
- REPAIRED status is claimed to mean verification passed.
- The adapter mutates the repository beyond actor-produced changes.
- The adapter claims complete workspace integrity (ignored files not inspected).

---

## 28. Definition of Done

- Branch created from `origin/main` @ `8472985e98d7979014153adb57d3d4dc7dd7ec82`.
- Implementation confined to the expected file scope in §19.
- All AC-01 through AC-38 pass with evidence.
- All 66 planned test cases pass (U, W, S, B, M, H series).
- Harness scenarios A–AA (27 scenarios) all pass.
- `ruff check` clean for new/modified Python files.
- `mypy --strict` clean for new/modified Python files.
- README and `next_steps.md` updated.
- Planning document updated to `IMPLEMENTATION COMPLETE — AWAITING REVIEW`.
- Independent review artifacts produced (not by this WP).
- Product Owner review and merge approval.

---

## 29. Earliest Dogfooding Milestone

After WP-AL-1C5, the **next work package** must be a **minimal orchestration wiring WP** that connects:

```
implement → verify → review → repair → reverify → human handoff
```

This next WP must prioritize **one supervised end-to-end self-development task**, not general production hardening.

### 29.1 Scope of the next wiring WP

- Wire repair adapter invocation into `run-story.sh` after review failure.
- Wire re-verification after REPAIRED (call `verify-story.sh` again).
- Wire final reporting with adapter result (update `report-story.sh` to read adapter result).
- No retry loop (human handoff after first repair attempt).
- No automatic commit/push/merge.

### 29.2 What this WP (WP-AL-1C5) does NOT deliver

WP-AL-1C5 delivers the repair adapter as a callable component. It does **not** deliver:

- Orchestration wiring.
- Re-verification after repair.
- Human handoff flow.
- End-to-end dogfooding cycle.

The dogfooding milestone requires both WP-AL-1C5 (this WP) and the subsequent wiring WP.

### 29.3 Priority

The next wiring WP must enable ForgeMind to be developed through Ralph-style agent cycles. It must not be blocked by production hardening concerns (sandboxing, concurrency, advanced symlink inspection, ignored-file inspection). Those are deferred to later hardening WPs after the dogfooding milestone is achieved.

---

## 30. Open Questions

None. All architectural decisions (DEC-C5-01 through DEC-C5-08) are RESOLVED.

---

## 31. Product Owner Approval

**APPROVED** — 2026-08-06

Product Owner has approved:

1. The planning document (title: "WP-AL-1C5 — Minimal Repair Adapter").
2. All architectural decisions (DEC-C5-01 through DEC-C5-08) as RESOLVED.
3. The reduced dogfooding-oriented scope (practical workspace integrity, not complete).
4. The deferred-hardening boundary (dirty baselines, advanced symlinks, ignored files, orchestration wiring, rollback, parallel execution deferred).
5. The proposed branch name (`feature/agent-loop-repair-adapter`).
6. The expected file scope (5 new files, 2 modified files).
7. The test matrix (66 total: U=23, W=14, S=11, B=9, M=6, H=3).
8. The harness scenarios (Y, Z, AA — exactly 3).
9. The earliest dogfooding milestone (next WP: minimal orchestration wiring).

**Document status:** APPROVED — READY FOR PLANNING COMMIT

**Next step:** Create planning branch from origin/main, commit this planning document, then create implementation branch for development.

**Implementation must not begin until:**

1. Planning document is committed on the planning branch.
2. Implementation branch (`feature/agent-loop-repair-adapter`) is created from origin/main.
3. Implementation follows the approved scope and forbidden-files list.

---

## Appendix A: Comparison with Original Draft

This revised planning document reduces scope from the original draft:

| Aspect | Original draft | Revised (this document) |
|--------|----------------|--------------------------|
| Baseline policy | Allow dirty baselines with manifest | Require clean tracked baseline |
| Rename handling | Preserve identity + normalize | Normalize to delete + add only |
| Workspace diff | Hybrid with full filesystem checks | Git porcelain + narrow filesystem checks |
| Mismatch policy | Hard failure | Hard failure (unchanged) |
| Timeout behavior | Terminate, no partial | Terminate, may inspect for safety reporting |
| Ignored files | Inspected | Not inspected (deferred) |
| Symlink inspection | Advanced | Lexical/boundary only (deferred) |
| Test count | 113 | 66 |
| Harness scenarios | 5 (Y, Z, AA, AB, AC) | 3 (Y, Z, AA) |
| Files | 6 new + 2 modified | 5 new + 2 modified |
| Integrity claim | Complete workspace integrity | Practical workspace integrity with explicit limitations |

---

## Appendix B: Comparison with WP-AL-1C2

| Aspect | WP-AL-1C2 (Review Adapter) | WP-AL-1C5 (Minimal Repair Adapter) |
|--------|----------------------------|-------------------------------------|
| Invokes | Reviewer subprocess | Repair actor subprocess |
| Validates | Review result contract | Repair result contract (WP-AL-1C4) |
| Workspace inspection | No | Yes (baseline + post-run) |
| Reconciliation | No | Yes (declared vs actual) |
| Permission enforcement | No | Yes (allowed/forbidden on actual) |
| Adapter result | Review adapter result | Repair adapter result with reconciliation |
| Mock component | mock_reviewer.py | mock_repair_actor.py |
| Harness scenarios | U, V | Y, Z, AA |
| Test count | 70 planned IDs | 66 planned cases |

---

## Appendix C: Failure Taxonomy Priority Order

When multiple failures occur, the adapter reports the highest-priority failure:

1. `ADAPTER_INTERNAL_ERROR`
2. `ADAPTER_DIRTY_BASELINE`
3. `ADAPTER_SOURCE_REVISION_DRIFT`
4. `ADAPTER_FORBIDDEN_CHANGE`
5. `ADAPTER_UNDECLARED_CHANGE`
6. `ADAPTER_DECLARED_MISSING`
7. `ADAPTER_CONTRACT_VIOLATION`
8. `ADAPTER_IDENTITY_MISMATCH`
9. `ADAPTER_MALFORMED_RESULT`
10. `ADAPTER_MISSING_RESULT`
11. `ADAPTER_NON_ZERO_EXIT`
12. `ADAPTER_TIMEOUT`
13. `ADAPTER_OUTPUT_SIZE_EXCEEDED`
