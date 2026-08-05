# WP-AL-1C4 — Repair Contract

**Status:** PLANNING COMPLETE — AWAITING REVIEW

**Branch:** `feature/agent-loop-repair-contract-planning`
**Base:** `origin/main` @ `d715b2c08eb0cfd0924d01c73efc2ff6f8f64262`
**Depends on:** WP-AL-1C1, WP-AL-1C2, WP-AL-1C3
**Precedes:** repair adapter (future WP), repair integration (future WP)

---

## 1. Objective

Define and implement a versioned repair-request and repair-result contract
(schema v1.0) for the repair phase of the agent loop, including structural
validators, identity binding rules, path-safety constraints, and a
deterministic builder. No repair execution, no adapter, no orchestrator
wiring, no report-story.sh changes, no LLM invocation.

This work package is analogous to WP-AL-1C1 (review contract): it defines
the shape and validation rules for repair artifacts but does not connect
them to a repair runner or the orchestration loop.

---

## 2. Current-State Evidence

### 2.1 Repository reconnaissance

| # | Concern | Current file/line | Existing behavior | Gap/Risk |
|---|---------|-------------------|-------------------|----------|
| 1 | Repair initiation | `run-story.sh:258` | Phase guard invoked with empty handler (`""`) | No actual repair execution |
| 2 | Repair inputs | (none) | Nothing passed to repair actor | No request contract exists |
| 3 | Repair outputs | `report-story.sh:87-99` | Glob `repair-*.json` in `$RUN_DIR/repair/` | Nothing produces these files |
| 4 | Repair counting | `run-story.sh:322-324` | `ITERATION` variable incremented | No per-attempt artifact schema |
| 5 | Repair exhaustion | `report-story.sh:108-109` | `iterations > 0` from file count | Based on file count, not schema-valid artifacts |
| 6 | Repair schema | (none) | Does not exist | Full gap |
| 7 | Repair validation | (none) | Does not exist | Full gap |
| 8 | Path safety for repair | (none) | No constraints defined | Untrusted actor could claim any path |
| 9 | Identity binding | (none) | No run_id/story_id/attempt check | Repair could claim different identity |
| 10 | Diagnostics bounds | (none) | No limits | Unbounded output risk |
| 11 | Harness scenario ownership | `run_harness_scenarios.sh` | A-X = 24 scenarios | Next available: Y, Z |
| 12 | Trust boundary | Architecture | Orchestrator trusted; worker/reviewer untrusted | Repair actor is untrusted like worker |

### 2.2 What is real vs stub

- **Real**: repair loop counting in `run-story.sh`, `ITERATION` variable,
  `MAX_REPAIR_ITERATIONS`, `report-story.sh` reading `repair/repair-*.json`.
- **Stub**: the repair phase handler (empty string at line 258), no repair
  artifacts ever written, no schema, no validator, no builder.

### 2.3 Existing repair-adjacent fields

| Location | Field | Purpose |
|----------|-------|---------|
| Review request/result | `repair_iteration` | Links review to repair state |
| Manifest | `repair_budget` | Integer 0-3, narrows global limit |
| Manifest | `repair_guidance` | Optional array of repair hints |
| Failure-context | `repair_guidance` | Pass-through from manifest |
| `project.json` | `runtime_policy.max_repair_iterations` | Global cap (default 3) |
| `project.json` | `roles.allowed` | Contains `"repair"` role |
| `guard.sh` / `passport.py` | Phase `"repair"` | Phase guard support |
| `lib/artifacts.sh:14` | `mkdir -p "$RUN_DIR/repair"` | Directory pre-created |

---

## 3. Problem Statement

The agent loop has a repair phase slot (phase guard, directory, iteration
counter, exhaustion reporting) but no contract defining what a repair
request looks like, what a repair result looks like, how identity is bound,
or what path-safety constraints apply.

Without a contract:

- A future repair adapter has no schema to produce or validate against.
- `report-story.sh` reads `repair-*.json` files without schema validation;
  a malformed file is silently swallowed by `json.load` exception handling.
- No identity binding prevents a repair artifact from claiming a different
  run_id or story_id.
- No path-safety rules prevent a repair actor from claiming it changed
  forbidden files.
- No bounds on diagnostics allow unbounded output.

WP-AL-1C4 closes the contract gap without implementing repair execution.

---

## 4. Scope

### 4.1 In scope

- Repair-request schema v1.0 (`.agent-loop/repair/SCHEMA.md`).
- Repair-result schema v1.0 (`.agent-loop/repair/SCHEMA.md`).
- Structural validators (`validate_repair_request`, `validate_repair_result`).
- Identity binding rules (run_id, story_id, attempt, source_revision).
- Path-safety rules (repo-root containment, forbidden-path protection,
  no traversal, no absolute paths, duplicate detection, max file count).
- Bounded diagnostics (size limits, sanitization metadata).
- Deterministic builder (`build_repair_request`).
- Validation API with fail-closed semantics.
- Deterministic mock/fixture support for contract tests.
- Compatibility with existing verification and reporting flow (no changes).
- Unit tests covering all invariants.
- Documentation (SCHEMA.md, planning doc).

### 4.2 Out of scope (non-goals)

- Real autonomous code-repair agent.
- Real LLM/provider invocation.
- Arbitrary shell execution.
- Unrestricted repository writes.
- Automatic commit/push/PR.
- Repair loop redesign (run-story.sh unchanged).
- Changing verification semantics (verify-story.sh unchanged).
- Changing review-result semantics (WP-AL-1C1/1C3 unchanged).
- Modifying report-story.sh (repair-*.json reading unchanged).
- Repair adapter or runner (future WP).
- Wiring repair into run-story.sh (future WP).
- Multi-agent orchestration expansion.
- Production deployment.

---

## 5. Trust Boundaries

| Actor | Trust level | Confined by |
|-------|-------------|-------------|
| Orchestrator (`run-story.sh`) | Trusted | — |
| Verifier (`verify-story.sh`) | Trusted | — |
| Reporter (`report-story.sh`) | Trusted | — |
| Reviewer (adapter + subprocess) | Untrusted | Review contract, adapter |
| Repair actor (future subprocess) | Untrusted | **Repair contract** (this WP) |
| Manifest | Trusted input | Schema validation |
| Failure-context | Trusted input | Schema validation |

The repair contract defines what an untrusted repair actor is allowed to
claim. The contract does not grant permissions; it constrains claims.
The orchestrator retains authority over what paths the repair actor may
actually touch (via manifest `allowed_paths`/`forbidden_paths`).

---

## 6. Proposed Repair-Request Contract

```json
{
  "schema_version": "1.0",
  "run_id": "string",
  "story_id": "string",
  "attempt": 1,
  "max_attempts": 3,
  "source_revision": "40-char lowercase hex",
  "failure_class": "verification_fail | review_fail",
  "failure_summary": "string (max 2048 bytes)",
  "failure_context_ref": {
    "path": "reports/failure-context.json",
    "schema_version": "1.0",
    "sha256": "64-char lowercase hex"
  },
  "verification_result_ref": {
    "path": "reports/verify-result.json",
    "schema_version": "1.0",
    "sha256": "64-char lowercase hex"
  },
  "review_result_ref": {
    "path": "reports/review-result.json",
    "schema_version": "1.0",
    "sha256": "64-char lowercase hex"
  },
  "allowed_paths": ["string (repo-relative, no traversal)"],
  "forbidden_paths": ["string (repo-relative, no traversal)"],
  "repair_guidance": ["string (max 256 bytes each, max 10 entries)"],
  "requested_action": "fix_verification | fix_review_findings",
  "generated_at": "2026-08-05T12:00:00Z"
}
```

### 6.0.1 Two-Layer Validation Architecture

**Layer 1: Contract Validation (this WP)**

The contract validator performs structural and semantic validation of JSON artifacts:

- JSON structure, required fields, field types, value ranges
- Identity binding: run_id, story_id, attempt, source_revision match between request and result
- Path safety: declared `changed_files` validated against orchestrator-provided `allowed_paths` and `forbidden_paths` rules (gitwildmatch semantics)
- Deterministic and filesystem-independent where possible (relies only on JSON artifacts and orchestrator-provided path rules)
- Does NOT prove the actual working tree contains only the declared changes
- Does NOT verify symlinks, file existence, or real filesystem state

**Layer 2: Future Adapter/Worktree Enforcement (not this WP)**

The future repair adapter/execution layer performs filesystem-level enforcement:

- Compare declared `changed_files` with actual repository diff
- Reject undeclared modifications (files changed but not listed in `changed_files`)
- Inspect actual symlinks and unsafe file types
- Enforce repository-root containment on real filesystem objects
- Ensure the repair actor did not modify forbidden paths in the real working tree
- Reconcile artifact claims with actual state

**Key invariant**: Contract validation verifies artifact claims. It does not prove workspace integrity. The repair actor cannot self-authorize path permissions; `allowed_paths` and `forbidden_paths` are orchestrator-provided.

### 6.1 Field specification

The request contains **16 top-level fields**.

| Field | Required | Type | Allowed values / constraints | Semantic purpose | Producer | Consumer |
|-------|----------|------|------------------------------|------------------|----------|----------|
| `schema_version` | Yes | string | Exactly `"1.0"` | Schema version | Orchestrator | Validator |
| `run_id` | Yes | string | Non-empty, max 256 bytes, `[A-Za-z0-9_:.-]` | Run identity | Orchestrator | Validator, repair actor |
| `story_id` | Yes | string | Non-empty, max 128 bytes, `[A-Za-z0-9_-]` | Story identity | Orchestrator | Validator, repair actor |
| `attempt` | Yes | integer | `1 <= attempt <= max_attempts` | Which repair iteration | Orchestrator | Validator, repair actor |
| `max_attempts` | Yes | integer | `>= 1`, capped by project policy | Total budget | Orchestrator | Validator |
| `source_revision` | Yes | string | 40-char lowercase hex | Base commit for repair | Orchestrator | Validator, repair actor |
| `failure_class` | Yes | string | `"verification_fail"` or `"review_fail"` | What triggered repair | Orchestrator | Repair actor |
| `failure_summary` | Yes | string | Max 2048 bytes, sanitized | Human-readable failure description | Orchestrator | Repair actor |
| `failure_context_ref` | Yes | object | `{path, schema_version, sha256}` | Reference to failure-context.json | Orchestrator | Validator, repair actor |
| `verification_result_ref` | Yes | object | `{path, schema_version, sha256}` | Reference to verify-result.json | Orchestrator | Validator, repair actor |
| `review_result_ref` | No | object or null | `{path, schema_version, sha256}` or null | Reference to review-result.json (if review ran) | Orchestrator | Validator, repair actor |
| `allowed_paths` | Yes | array of strings | Each: repo-relative, no `..`, no leading `/` | Paths repair may modify (from manifest) | Orchestrator | Repair actor |
| `forbidden_paths` | Yes | array of strings | Each: repo-relative, no `..`, no leading `/` | Paths repair must not touch (from manifest) | Orchestrator | Repair actor |
| `repair_guidance` | No | array of strings | Max 10 entries, each max 256 bytes | Hints from manifest | Orchestrator | Repair actor |
| `requested_action` | Yes | string | `"fix_verification"` or `"fix_review_findings"` | What repair should attempt | Orchestrator | Repair actor |
| `generated_at` | Yes | string | ISO-8601 UTC | Creation timestamp (supplied by caller) | Orchestrator | Validator |

### 6.2 Cross-field rules

- `attempt >= 1` and `attempt <= max_attempts`.
- `max_attempts >= 1`.
- If `failure_class == "review_fail"` then `review_result_ref` must be
  non-null.
- If `failure_class == "verification_fail"` then `review_result_ref` may
  be null.
- If `requested_action == "fix_review_findings"` then `failure_class`
  must be `"review_fail"`.

### 6.3 Identity binding rules

- `request.run_id` must equal failure-context `run_id`.
- `request.story_id` must equal failure-context `story_id`.
- `request.story_id` must equal manifest `story_id`.
- `request.source_revision` must equal manifest `base_commit`.
- `request.allowed_paths` must equal manifest `allowed_paths`.
- `request.forbidden_paths` must equal manifest `forbidden_paths`.

### 6.4 Path-base rules

| Path field | Resolved relative to |
|------------|---------------------|
| `failure_context_ref.path` | `run_dir` |
| `verification_result_ref.path` | `run_dir` |
| `review_result_ref.path` | `run_dir` |
| `allowed_paths[]` | `repo_root` |
| `forbidden_paths[]` | `repo_root` |

All paths must be relative (no leading `/`), no `..` traversal, no
Windows drive letters or UNC paths.

---

## 7. Proposed Repair-Result Contract

```json
{
  "schema_version": "1.0",
  "run_id": "string",
  "story_id": "string",
  "attempt": 1,
  "source_revision": "40-char lowercase hex",
  "status": "REPAIRED | NO_CHANGE | ERROR",
  "changed": true,
  "changed_files": ["string (repo-relative, no traversal)"],
  "summary": "string (max 2048 bytes)",
  "diagnostics": {
    "actions_taken": ["string (max 512 bytes each, max 20 entries)"],
    "obstacles_encountered": ["string (max 512 bytes each, max 10 entries)"],
    "confidence": "high | medium | low"
  },
  "recommended_action": "reverify | abort | human_review",
  "sanitization": {
    "redaction_applied": false,
    "redaction_count": 0,
    "truncation_applied": false,
    "truncated_fields": []
  },
  "completed_at": "2026-08-05T12:05:00Z"
}
```

### 7.1 Field specification

The result contains **13 top-level fields**.

| Field | Required | Type | Allowed values / constraints | Semantic purpose | Producer | Consumer |
|-------|----------|------|------------------------------|------------------|----------|----------|
| `schema_version` | Yes | string | Exactly `"1.0"` | Schema version | Repair actor | Validator |
| `run_id` | Yes | string | Non-empty, max 256 bytes, `[A-Za-z0-9_:.-]` | Run identity (must match request) | Repair actor | Validator |
| `story_id` | Yes | string | Non-empty, max 128 bytes, `[A-Za-z0-9_-]` | Story identity (must match request) | Repair actor | Validator |
| `attempt` | Yes | integer | Must match request `attempt` | Which repair iteration | Repair actor | Validator |
| `source_revision` | Yes | string | 40-char lowercase hex, must match request | Base commit (unchanged by repair) | Repair actor | Validator |
| `status` | Yes | string | `"REPAIRED"`, `"NO_CHANGE"`, or `"ERROR"` | Repair outcome | Repair actor | Validator |
| `changed` | Yes | boolean | Must be consistent with status | Whether files were modified | Repair actor | Validator |
| `changed_files` | Yes | array of strings | Each: repo-relative, no `..`, no leading `/`, max 50 entries | Paths modified by repair | Repair actor | Validator |
| `summary` | Yes | string | Max 2048 bytes, sanitized | Human-readable repair description | Repair actor | Consumer |
| `diagnostics` | No | object | Bounded sub-fields | Structured repair diagnostics | Repair actor | Consumer |
| `recommended_action` | Yes | string | `"reverify"`, `"abort"`, or `"human_review"` | What orchestrator should do next | Repair actor | Orchestrator |
| `sanitization` | Yes | object | `{redaction_applied, redaction_count, truncation_applied, truncated_fields}` | Sanitization metadata | Repair actor | Validator |
| `completed_at` | Yes | string | ISO-8601 UTC | Completion timestamp (supplied by caller) | Repair actor | Validator |

### 7.2 Status semantics

| Status | Meaning | `changed` | `changed_files` | `recommended_action` constraints |
|--------|---------|-----------|-----------------|----------------------------------|
| `REPAIRED` | Repair actor made changes | Must be `true` | Must be non-empty | Must be `"reverify"` |
| `NO_CHANGE` | Repair actor chose not to change anything | Must be `false` | Must be empty | Must be `"abort"` or `"human_review"` |
| `ERROR` | Repair actor infrastructure failure | Unconstrained | Unconstrained | Must be `"abort"` or `"human_review"` |

**Critical invariant**: `REPAIRED` status does NOT mean verification
passed. Repair success and post-repair verification are distinct. The
orchestrator must re-run verification after `REPAIRED` to determine
whether the repair actually fixed the problem.

### 7.3 Cross-field rules

- `REPAIRED` requires `changed == true` AND `len(changed_files) >= 1`.
- `NO_CHANGE` requires `changed == false` AND `len(changed_files) == 0`.
- `ERROR` has no constraint on `changed` or `changed_files` (may be
  indeterminate).
- `REPAIRED` requires `recommended_action == "reverify"`.
- `NO_CHANGE` requires `recommended_action in ("abort", "human_review")`.
- `ERROR` requires `recommended_action in ("abort", "human_review")`.
- `changed_files` entries must be unique (no duplicates).
- `changed_files` entries must be in `allowed_paths` (if allowed_paths is
  non-empty; glob matching).
- `changed_files` entries must NOT match any `forbidden_paths` entry.

### 7.4 Identity binding rules

- `result.run_id` must equal request `run_id`.
- `result.story_id` must equal request `story_id`.
- `result.attempt` must equal request `attempt`.
- `result.source_revision` must equal request `source_revision`.

---

## 8. Path and File Safety

### 8.1 Path normalization

- All paths in `changed_files`, `allowed_paths`, `forbidden_paths`, and
  `*_ref.path` must be normalized:
  - No leading `/` (must be relative).
  - No `..` traversal components.
  - No `.` single-dot components.
  - No empty segments (no `//`).
  - No Windows drive letters (`C:`) or UNC paths (`\\server\share`).
  - No null bytes.
  - Max 512 bytes per path string.

### 8.2 Repository-root containment

- `changed_files` are resolved relative to `repo_root`.
- After normalization, the resolved path must be under `repo_root`
  (verified via `Path.resolve().is_relative_to(repo_root.resolve())` or
  equivalent string check).

### 8.3 Symlink handling

- `changed_files` entries are logical paths. The contract does not verify
  whether they are symlinks; that is the responsibility of the repair
  adapter/runner (which must reject symlink targets outside allowed paths).
- The contract validator checks only string-level path safety.

### 8.4 Forbidden-path protection

- `forbidden_paths` use gitwildmatch semantics (same as manifest).
- A `changed_files` entry matching any `forbidden_paths` pattern is a
  contract violation.
- Forbidden paths take precedence over allowed paths.

### 8.5 Allowed-path allowlist

- `allowed_paths` use gitwildmatch semantics.
- A `changed_files` entry must match at least one `allowed_paths` pattern
  (if `allowed_paths` is non-empty).
- If `allowed_paths` is empty, all non-forbidden paths are allowed
  (defensive; manifest should always provide allowed_paths).

### 8.6 Duplicate detection

- `changed_files` must not contain duplicate entries (exact string match
  after normalization).

### 8.7 Maximum changed-file count

- `changed_files` array: max 50 entries.

### 8.8 File-type restrictions

- The contract does not restrict file types (any file type may be listed
  in `changed_files`). The repair adapter/runner is responsible for
  rejecting binary files, generated files, or other disallowed types.
- The contract validator checks only path safety, not file existence or
  type.

### 8.9 Deletion and rename representation

- Deletion: a `changed_files` entry may represent a deleted file. The
  contract does not distinguish creation/modification/deletion; that is
  the responsibility of the repair adapter/runner.
- Rename: represented as two entries (old path deleted, new path created).
  Both paths must satisfy path-safety rules.

---

## 9. Bounded Diagnostics

### 9.1 Diagnostics object

```json
{
  "actions_taken": ["string (max 512 bytes each, max 20 entries)"],
  "obstacles_encountered": ["string (max 512 bytes each, max 10 entries)"],
  "confidence": "high | medium | low"
}
```

- `actions_taken`: what the repair actor did (max 20 entries, each max
  512 bytes).
- `obstacles_encountered`: what blocked or slowed repair (max 10 entries,
  each max 512 bytes).
- `confidence`: repair actor's self-assessed confidence (optional field;
  if present, must be `"high"`, `"medium"`, or `"low"`).

### 9.2 Sanitization metadata

```json
{
  "redaction_applied": false,
  "redaction_count": 0,
  "truncation_applied": false,
  "truncated_fields": []
}
```

- Same structure as review contract sanitization metadata.
- `truncated_fields`: max 64 entries, each max 256 bytes.
- Sanitization pipeline: same as review contract (UTF-8 normalization,
  binary detection, control character removal, base64 redaction, secret
  pattern redaction, URL query stripping, byte truncation).

### 9.3 Summary field

- Max 2048 bytes after sanitization.
- No absolute paths, no raw secrets, no untrusted payloads.

---

## 10. Validation Architecture

### 10.1 API

```python
def validate_repair_request(request: dict[str, Any]) -> None:
    """
    Validate repair-request structural invariants.
    Raises RepairContractError on any violation.
    No filesystem access.
    """

def validate_repair_result(result: dict[str, Any]) -> None:
    """
    Validate repair-result structural invariants.
    Raises RepairContractError on any violation.
    No filesystem access.
    """

def validate_repair_request_references(
    request: dict[str, Any],
    repo_root: Path,
    run_dir: Path,
) -> None:
    """
    Validate repair-request referential invariants against filesystem.
    Raises RepairContractError on any violation.
    """

def validate_repair_result_identity(
    result: dict[str, Any],
    request: dict[str, Any],
) -> None:
    """
    Validate repair-result identity binding against request.
    Raises RepairContractError on any violation.
    No filesystem access.
    """

def validate_repair_result_paths(
    result: dict[str, Any],
    allowed_paths: list[str],
    forbidden_paths: list[str],
    repo_root: Path,
) -> None:
    """
    Validate repair-result changed_files against allowed/forbidden paths.
    Raises RepairContractError on any violation.
    """
```

### 10.2 Builder API

```python
def build_repair_request(
    repo_root: Path,
    run_dir: Path,
    manifest_path: Path,
    failure_context_path: Path,
    verify_result_path: Path,
    review_result_path: Path | None,
    run_id: str,
    story_id: str,
    attempt: int,
    max_attempts: int,
    source_revision: str,
    failure_class: str,
    failure_summary: str,
    requested_action: str,
    generated_at: str,
) -> dict[str, Any]:
    """
    Build repair request with both structural and referential validation.

    Computes SHA-256 of referenced files, extracts allowed_paths/forbidden_paths
    from manifest, sanitizes failure_summary and repair_guidance.
    """
```

### 10.3 Determinism rules

- Builder does not call `datetime.now()`, `time.time()`, or any internal
  time function.
- All timestamps supplied explicitly by caller as ISO-8601 strings.
- Canonical bytes are deterministic: same inputs produce identical bytes.
- `changed_files` array ordered lexicographically (for result).
- `sanitization.truncated_fields` array ordered lexicographically.

---

## 11. Integration Points

WP-AL-1C4 defines the contract but does NOT wire it into the orchestration
loop. Integration is deferred to future work packages:

- **Repair adapter WP** (future): invokes repair subprocess, produces
  repair-request and repair-result artifacts, validates with this contract.
- **Repair integration WP** (future): wires repair adapter into
  `run-story.sh`, updates `report-story.sh` to validate `repair-*.json`
  with this contract before counting iterations.

### 11.1 Exact expected files

| Path | Change type | Responsibility | Why required |
|------|-------------|----------------|--------------|
| `.agent-loop/repair/SCHEMA.md` | NEW | Request + result schemas v1.0 | Canonical schema documentation |
| `scripts/agent-loop/lib/repair_contract.py` | NEW | Validator + builder | Validation API implementation |
| `scripts/agent-loop/tests/test_repair_contract.py` | NEW | Unit tests | Contract validation coverage |
| `docs/planning/wp_al_1c4_repair_contract.md` | NEW | This document | Planning record |
| `scripts/agent-loop/README.md` | MODIFY | Status update | Document WP completion |
| `docs/next_steps.md` | MODIFY | Status update | Record WP-AL-1C4 planning |

### 11.2 Forbidden files

- `scripts/agent-loop/run-story.sh` (no orchestrator changes)
- `scripts/agent-loop/verify-story.sh` (no verification changes)
- `scripts/agent-loop/report-story.sh` (no reporting changes)
- `scripts/agent-loop/lib/failure_context.py` (consumed via narrow import only)
- `scripts/agent-loop/lib/review_contract.py` (unchanged)
- `scripts/agent-loop/lib/review_adapter.py` (unchanged)
- `scripts/agent-loop/lib/mock_reviewer.py` (unchanged)
- `.agent-loop/review/SCHEMA.md` (unchanged)
- `.agent-loop/failure-context/SCHEMA.md` (unchanged)
- `.agent-loop/manifests/SCHEMA.md` (unchanged)
- `.agent-loop/gates.json` (unchanged)
- `.agent-loop/project.json` (unchanged)
- `backend/**`, `frontend/**`, `docker/**`, `forgemind_project_source_of_truth/**`
- `.env`, `.env.*`, `*.pem`, `*.key`
- Gate implementations (`lib/{scope.sh,tests.sh,harness.py,manifest_loader.py,config_loader.py,guard.sh,passport.py,artifacts.sh,env.sh}`)

---

## 12. Unit-Test Plan

### 12.1 Structural validation tests (no filesystem) — U01–U30

| ID | Case | Expected |
|----|------|----------|
| U01 | Minimal valid repair request (all required fields) | Validator returns OK |
| U02 | Minimal valid repair result (REPAIRED with changed files) | Validator returns OK |
| U03 | Valid repair result (NO_CHANGE) | Validator returns OK |
| U04 | Valid repair result (ERROR) | Validator returns OK |
| U05 | Missing required field (schema_version) | Validator rejects |
| U06 | Wrong field type (attempt as string) | Validator rejects |
| U07 | Unknown status value ("FIXED") | Validator rejects |
| U08 | Schema version mismatch ("2.0") | Validator rejects |
| U09 | Run identity mismatch (result.run_id != request.run_id) | Validator rejects |
| U10 | Story identity mismatch (result.story_id != request.story_id) | Validator rejects |
| U11 | Attempt mismatch (result.attempt != request.attempt) | Validator rejects |
| U12 | Source revision mismatch | Validator rejects |
| U13 | Invalid attempt bounds (attempt < 1) | Validator rejects |
| U14 | Invalid attempt bounds (attempt > max_attempts) | Validator rejects |
| U15 | REPAIRED without changed files (changed=false) | Validator rejects |
| U16 | REPAIRED with empty changed_files array | Validator rejects |
| U17 | NO_CHANGE with changed files (changed=true) | Validator rejects |
| U18 | NO_CHANGE with non-empty changed_files | Validator rejects |
| U19 | Duplicate changed_files entries | Validator rejects |
| U20 | Absolute path in changed_files ("/etc/passwd") | Validator rejects |
| U21 | Parent traversal in changed_files ("../secrets.env") | Validator rejects |
| U22 | Forbidden path in changed_files (matches forbidden_paths pattern) | Validator rejects |
| U23 | Path outside allowed_paths (does not match any allowed pattern) | Validator rejects |
| U24 | Excessive changed_files count (51 entries) | Validator rejects |
| U25 | Oversized summary (2049 bytes) | Validator rejects |
| U26 | Malformed JSON (unparseable) | Validator rejects |
| U27 | Unreadable artifact (non-JSON file) | Validator rejects |
| U28 | Bounded diagnostics (actions_taken > 20 entries) | Validator rejects |
| U29 | Redacted diagnostics (secret pattern in summary) | Redacted in output |
| U30 | Deterministic repeated validation (same input twice) | Identical result |

### 12.2 Referential validation tests (filesystem required) — R01–R15

| ID | Case | Expected |
|----|------|----------|
| R01 | Valid referential validation (all matches) | Validator returns OK |
| R02 | Failure-context file does not exist | Validator rejects |
| R03 | Failure-context SHA-256 mismatch | Validator rejects |
| R04 | Failure-context schema_version mismatch | Validator rejects |
| R05 | Verify-result file does not exist | Validator rejects |
| R06 | Verify-result SHA-256 mismatch | Validator rejects |
| R07 | Review-result file does not exist (when review_result_ref is non-null) | Validator rejects |
| R08 | Review-result SHA-256 mismatch | Validator rejects |
| R09 | Manifest file does not exist | Validator rejects |
| R10 | Manifest SHA-256 mismatch | Validator rejects |
| R11 | run_id mismatch between request and failure-context | Validator rejects |
| R12 | story_id mismatch between request and manifest | Validator rejects |
| R13 | source_revision mismatch with manifest base_commit | Validator rejects |
| R14 | allowed_paths mismatch with manifest | Validator rejects |
| R15 | failure_class="review_fail" with null review_result_ref | Validator rejects |

### 12.3 Builder tests — B01–B15

| ID | Case | Expected |
|----|------|----------|
| B01 | Builder from valid inputs | Produces valid request |
| B02 | Builder computes failure_context_ref.sha256 correctly | Matches manual sha256sum |
| B03 | Builder computes verification_result_ref.sha256 correctly | Matches manual sha256sum |
| B04 | Builder computes review_result_ref.sha256 correctly (when present) | Matches manual sha256sum |
| B05 | Builder with missing failure-context file | Raises error |
| B06 | Builder with missing verify-result file | Raises error |
| B07 | Builder with invalid failure-context schema | Raises error |
| B08 | Builder sanitizes failure_summary (secret pattern) | Redacted in output |
| B09 | Builder sanitizes repair_guidance (control chars) | Removed |
| B10 | Builder truncates oversized summary (3000 bytes to 2048 bytes) | Truncated + marker |
| B11 | Builder with UTF-8 invalid bytes | Replaced with U+FFFD |
| B12 | Builder populates sanitization metadata accurately | redaction_count, truncation_applied correct |
| B13 | Builder with no sanitization needed | redaction_applied=false, redaction_count=0 |
| B14 | Builder deterministic output (same inputs twice) | Identical canonical bytes |
| B15 | Builder without explicit timestamp | Raises error (no internal time call) |

### 12.4 Serialization tests — C01–C05

| ID | Case | Expected |
|----|------|----------|
| C01 | Canonical bytes deterministic (same dict, different insertion order) | Identical bytes |
| C02 | Canonical bytes use sort_keys=True | Keys sorted alphabetically |
| C03 | Canonical bytes use compact separators | No spaces after : or , |
| C04 | Pretty JSON has indent=2 | Formatted with 2-space indent |
| C05 | Pretty JSON has exactly one terminal newline | Ends with "\n" |

### 12.5 Sanitization tests — D01–D10

| ID | Case | Expected |
|----|------|----------|
| D01 | Redact stripe key pattern in summary | "[REDACTED:stripe_key]" |
| D02 | Redact GitHub token pattern | "[REDACTED:github_token]" |
| D03 | Redact AWS key pattern | "[REDACTED:aws_key]" |
| D04 | Redact Bearer token | "[REDACTED:bearer_token]" |
| D05 | Redact Basic auth | "[REDACTED:basic_auth]" |
| D06 | Redact password assignment | "[REDACTED:password]" |
| D07 | Redact private key block | "[REDACTED:private_key]" |
| D08 | Strip URL query string | Query removed, path preserved |
| D09 | Detect binary content | "[REDACTED:binary_content]" |
| D10 | Redact base64 run (100+ chars) | "[REDACTED:base64_payload]" |

### 12.6 Test counts

- **75 planned unit-test cases** (U01–U30 + R01–R15 + B01–B15 + C01–C05 + D01–D10)
- These are planned cases, not guaranteed pytest item count. Actual pytest
  collection may differ based on parametrization and fixture grouping.

---

## 13. Harness-Scenario Plan

WP-AL-1C4 does NOT add harness scenarios. Repair execution is not
implemented; therefore no end-to-end harness scenario can exercise the
repair contract in a realistic pipeline.

Harness scenarios for repair will be added by the **repair adapter WP**
(future), which implements the actual repair subprocess invocation and
can produce realistic repair artifacts.

Current harness range remains: **A through X = 24 scenarios, 24/24 PASS**.

---

## 14. Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-01 | Repair-request schema v1.0 documented at `.agent-loop/repair/SCHEMA.md`. |
| AC-02 | Repair-result schema v1.0 documented at `.agent-loop/repair/SCHEMA.md` with REPAIRED/NO_CHANGE/ERROR semantics. |
| AC-03 | `validate_repair_request(request)` — structural validation, no filesystem. |
| AC-04 | `validate_repair_result(result)` — structural validation, no filesystem. |
| AC-05 | `validate_repair_request_references(request, repo_root, run_dir)` — referential validation, two-root. |
| AC-06 | `validate_repair_result_identity(result, request)` — identity binding validation. |
| AC-07 | `validate_repair_result_paths(result, allowed_paths, forbidden_paths, repo_root)` — path-safety validation. |
| AC-08 | Builder produces schema-valid request with structural + referential validation. |
| AC-09 | Builder computes SHA-256 of referenced files (failure-context, verify-result, review-result). |
| AC-10 | Builder validates referenced files exist and have correct schema_version before computing SHA-256. |
| AC-11 | Builder sanitizes failure_summary and repair_guidance. |
| AC-12 | Builder populates sanitization metadata accurately. |
| AC-13 | Validator rejects invalid fields, oversized strings, path traversal, bad attempt bounds. |
| AC-14 | Cross-field invariants enforced (status+changed+changed_files+recommended_action). |
| AC-15 | Identity binding enforced (run_id, story_id, attempt, source_revision match between request and result). |
| AC-16 | Path-safety rules enforced (no absolute paths, no traversal, forbidden-path protection, allowed-path allowlist). |
| AC-17 | Canonical JSON deterministic (sort_keys=True, separators=(",", ":"), ensure_ascii=False). |
| AC-18 | Pretty JSON has exactly one terminal newline, no trailing whitespace. |
| AC-19 | No internal time calls; all timestamps supplied by caller. |
| AC-20 | Sanitization imports narrow API from failure_context.py. |
| AC-21 | No duplication of sanitization logic, no private function imports. |
| AC-22 | REPAIRED status requires changed=true and non-empty changed_files. |
| AC-23 | NO_CHANGE status requires changed=false and empty changed_files. |
| AC-24 | ERROR status has no constraint on changed/changed_files. |
| AC-25 | REPAIRED does NOT imply verification passed (contract does not claim repair success = verification success). |
| AC-26 | No raw secret values, no absolute paths, no path traversal in output. |
| AC-27 | 75 planned unit-test cases covering all invariants. |
| AC-28 | Existing harness scenarios A–X remain 24/24 PASS (no regressions). |
| AC-29 | `ruff check` clean for new/modified Python files. |
| AC-30 | `mypy --strict` clean for new/modified Python files. |
| AC-31 | No LLM invocation, no network access, no shell interpolation. |
| AC-32 | No modification to forbidden files (run-story.sh, verify-story.sh, report-story.sh, review_contract.py, etc.). |
| AC-33 | Planning document approved before implementation. |

---

## 15. Verification Plan

### 15.1 Expected verification commands

```bash
# Focused pytest for repair contract
pytest scripts/agent-loop/tests/test_repair_contract.py -v

# Full agent-loop test suite (regression)
pytest scripts/agent-loop/tests/ -v

# Harness scenarios (A-X, 24 scenarios)
bash scripts/agent-loop/tests/run_harness_scenarios.sh

# Lint
ruff check scripts/agent-loop/lib/repair_contract.py
ruff check scripts/agent-loop/tests/test_repair_contract.py

# Type checking
mypy --strict scripts/agent-loop/lib/repair_contract.py

# Compile check
python3 -m py_compile scripts/agent-loop/lib/repair_contract.py

# Shell syntax (no shell changes expected, but verify no accidental modifications)
bash -n scripts/agent-loop/run-story.sh
bash -n scripts/agent-loop/verify-story.sh
bash -n scripts/agent-loop/report-story.sh

# Schema validation (JSON syntax)
python3 -c "import json; json.load(open('.agent-loop/repair/SCHEMA.md'))" || echo "SCHEMA.md is markdown, not JSON"

# Secret/path scan
grep -rn "sk_live_\|sk_test_\|ghp_\|AKIA\|Bearer\s\|Basic\s" scripts/agent-loop/lib/repair_contract.py scripts/agent-loop/tests/test_repair_contract.py .agent-loop/repair/SCHEMA.md || echo "No secrets found"
grep -rn "/home/\|/Users/\|/tmp/" scripts/agent-loop/lib/repair_contract.py scripts/agent-loop/tests/test_repair_contract.py .agent-loop/repair/SCHEMA.md || echo "No absolute paths found"

# Git diff check
git diff --check

# Repository status
git status --short --untracked-files=all
git diff --name-status
```

### 15.2 Definition of Done

- Branch created from `origin/main` @ `d715b2c08eb0cfd0924d01c73efc2ff6f8f64262`.
- Implementation confined to the probable file scope in §11.1.
- All AC-01 through AC-33 pass with evidence (test output, harness output,
  lint/mypy output, `git diff --name-status` confirming no forbidden
  modifications).
- README and `next_steps.md` updated to reflect the new state.
- Planning document updated to `IMPLEMENTATION COMPLETE — AWAITING REVIEW`.
- Independent review artifacts produced (not by this WP).
- Product Owner review and merge approval.

---

## 16. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Scope creep into repair adapter | Medium | High | Strict forbidden-files list; stop condition if adapter code appears |
| Ambiguity in path-safety rules | Low | Medium | Explicit gitwildmatch semantics, same as manifest |
| Over-constraining future repair adapter | Low | Medium | Contract defines validation rules, not implementation; adapter has flexibility in how it produces artifacts |
| Confusion between repair success and verification success | Medium | High | Explicit invariant in schema docs and tests: REPAIRED ≠ VERIFIED |
| Sanitization logic duplication | Low | Medium | Narrow import from failure_context.py, same pattern as review contract |
| Test count mismatch (planned vs actual pytest items) | Low | Low | Document planned cases, not guaranteed pytest item count |

---

## 17. Product Owner Decisions

### 17.1 RESOLVED decisions

| ID | Decision | Rationale | Effective date |
|----|----------|-----------|----------------|
| DEC-C4-01 | **Contract validator checks `changed_files` against `allowed_paths`/`forbidden_paths`.** The contract validates artifact claims (JSON structure, identity binding, declared paths vs orchestrator-provided allow/deny rules). It does not prove the actual working tree contains only those changes. Enforcement and reconciliation against the real repository diff belong to the future repair adapter/execution layer. The repair actor cannot define or widen its own `allowed_paths` or `forbidden_paths`. | Defense in depth: contract enforces claims, adapter enforces execution. Repair actor cannot self-authorize. | 2026-08-05 |
| DEC-C4-02 | **No PARTIAL status.** Use only REPAIRED, NO_CHANGE, ERROR. REPAIRED means a repair actor claims permitted changes were produced. It never means verification passed. | Simplicity: partial repairs are either REPAIRED (if any changes) or NO_CHANGE (if none). Orchestrator decides whether to reverify or abort based on post-repair verification result. | 2026-08-05 |
| DEC-C4-03 | **`diagnostics.confidence` is optional.** When present, it must be a string with value "high", "medium", or "low". It must not influence authorization, allowed paths, repair status, or verification outcome. Absence must not make an otherwise valid result invalid. | Not all repair actors can assess confidence; forcing a value leads to noise. Confidence is informational only, not a control signal. | 2026-08-05 |

### 17.2 Decisions already resolved

- Schema version: `"1.0"` (matches review and failure-context schemas).
- Status values: `REPAIRED | NO_CHANGE | ERROR` (minimal set; no PARTIAL).
- Identity binding: run_id, story_id, attempt, source_revision (matches review contract pattern).
- Path safety: gitwildmatch semantics (matches manifest).
- Sanitization: narrow import from failure_context.py (matches review contract).
- No repair execution in this WP (matches WP-AL-1C1 pattern).
- No harness scenarios in this WP (repair execution not implemented).

---

## 18. Implementation Stop Conditions

Stop and report if:

- Any file outside allowed paths is modified.
- Any test in the existing A–X harness suite fails.
- `ruff` or `mypy --strict` reports errors on `repair_contract.py`.
- A sanitizer signature in `failure_context.py` changes or is missing.
- Any secret, absolute path, or path traversal appears in output.
- `run-story.sh`, `verify-story.sh`, or `report-story.sh` is modified.
- `failure_context.py`, `review_contract.py`, `review_adapter.py`, or `mock_reviewer.py` is modified.
- Any LLM or network call is introduced.
- The scope expands into repair adapter, repair execution, or repair integration.
- REPAIRED status is claimed to mean verification passed.

---

## 19. Follow-Up Sequencing

Proposed sequence after this WP:

1. **WP-AL-1C4 (this WP)** — repair contract (schema + validator + builder).
2. **Repair adapter WP** (future) — invokes repair subprocess, produces
   repair artifacts, validates with this contract. Analogous to WP-AL-1C2.
3. **Repair integration WP** (future) — wires repair adapter into
   `run-story.sh`, updates `report-story.sh` to validate `repair-*.json`
   with this contract before counting iterations.
4. **Review invocation bridge WP** (future) — wires reviewer adapter into
   `run-story.sh` (separate from repair work).

The repair contract does not depend on the repair adapter or integration;
it is a pure schema WP analogous to WP-AL-1C1.

---

## 20. Branch Strategy

- Base: `origin/main` @ `d715b2c08eb0cfd0924d01c73efc2ff6f8f64262`.
- Branch name: `feature/agent-loop-repair-contract` (or
  `chore/agent-loop-repair-contract`, PO preference).
- One PR against `main`.
- Merge commit strategy (not squash) to preserve the WP structure.

---

## 21. Commit / PR Strategy

Conventional commits, one logical change per commit:

1. `docs(agent-loop): define WP-AL-1C4 repair contract`
   (this planning document).
2. `feat(agent-loop): add repair-request and repair-result validators`
   (`repair_contract.py`, unit tests).
3. `docs(agent-loop): record WP-AL-1C4 completion`
   (`README.md`, `next_steps.md`, this doc).

PR description references this planning document and lists AC-01…AC-33.

---

## 22. Dependencies and Environment

- Python 3.11+ (per repository baseline).
- pytest 9.0+
- ruff 0.8+
- mypy 1.14+
- Narrow import from `failure_context.py` (`redact_text`, `normalize_utf8`,
  `sanitize_control_characters`, `is_binary_content`, `redact_base64_runs`,
  `truncate_text`) — approved pattern from WP-AL-1C1.
- Narrow import from `harness.py` (`atomic_json_write`) for builder output.
- Gitwildmatch pattern matching (reuse from `scope.py` or `harness.py`).
- No new third-party dependencies.

---

## 23. Explicit Non-Goals

- No LLM invocation.
- No repair agent integration.
- No repair subprocess invocation.
- No implementer (Ralph/OpenCode) invocation.
- No run lifecycle / state machine / resumability changes.
- No concurrency support changes.
- No prompt design.
- No change to any existing schema document (review, failure-context, manifest).
- No change to `gates.json` policy.
- No change to backend or product code.
- No speculative scaffolding for repair adapter or integration.
- No harness scenarios (repair execution not implemented).

---

## 24. Open Decisions

None. All architectural decisions (DEC-C4-01, DEC-C4-02, DEC-C4-03) are
resolved and recorded in §17.1.

---

## 25. Summary

WP-AL-1C4 defines the repair-request and repair-result contracts for the
agent-loop repair phase. It provides structural validators, identity
binding rules, path-safety constraints, and a deterministic builder. It
does not implement repair execution, repair adapter, or orchestrator
wiring. The contract is analogous to WP-AL-1C1 (review contract) and
prepares the foundation for future repair-adapter and repair-integration
work packages.
