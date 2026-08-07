# Repair Adapter Result Schema v1.0

## Purpose

Versioned adapter-result contract for WP-AL-1C5 Minimal Repair Adapter. The
adapter result is a separate artifact produced by the adapter after invoking
the repair actor, validating the WP-AL-1C4 repair result, inspecting the
actual workspace changes, reconciling declared vs actual changes, and
enforcing permissions.

**Key invariants:**
- The adapter result is distinct from the WP-AL-1C4 repair result
- The adapter result contains validated repair-result summary + reconciliation metadata
- The adapter result documents what was inspected and what was not (integrity_scope)
- The adapter does NOT claim complete workspace integrity (ignored files not inspected)
- The adapter does NOT prove workspace integrity — it validates declared claims against observed facts
- REPAIRED status in repair_result_summary does NOT mean verification passed

## Adapter Result Schema v1.0

```json
{
  "schema_version": "1.0",
  "run_id": "string (max 256 bytes, alphanumeric + _ - :)",
  "story_id": "string (max 128 bytes, alphanumeric + _ -)",
  "attempt": "integer >= 1",
  "adapter_status": "ADAPTER_SUCCESS | ADAPTER_DIRTY_BASELINE | ADAPTER_TIMEOUT | ADAPTER_NON_ZERO_EXIT | ADAPTER_MISSING_RESULT | ADAPTER_MALFORMED_RESULT | ADAPTER_CONTRACT_VIOLATION | ADAPTER_IDENTITY_MISMATCH | ADAPTER_SOURCE_REVISION_DRIFT | ADAPTER_FORBIDDEN_CHANGE | ADAPTER_UNDECLARED_CHANGE | ADAPTER_DECLARED_MISSING | ADAPTER_OUTPUT_SIZE_EXCEEDED | ADAPTER_INTERNAL_ERROR",
  "repair_result_summary": {
    "status": "REPAIRED | NO_CHANGE | ERROR",
    "changed": "boolean",
    "changed_files": ["string (repo-relative, no traversal)"],
    "recommended_action": "reverify | abort | human_review",
    "summary": "string (max 2048 bytes)"
  },
  "workspace_changes": {
    "baseline_source_revision": "40-char lowercase hex",
    "post_source_revision": "40-char lowercase hex",
    "source_revision_stable": "boolean",
    "added": ["string (repo-relative, sorted)"],
    "modified": ["string (repo-relative, sorted)"],
    "deleted": ["string (repo-relative, sorted)"],
    "untracked": ["string (repo-relative, sorted)"]
  },
  "reconciliation": {
    "declared_files": ["string (repo-relative, sorted)"],
    "actual_files": ["string (repo-relative, sorted)"],
    "undeclared_changes": ["string (repo-relative, sorted)"],
    "declared_but_missing": ["string (repo-relative, sorted)"],
    "exact_match": "boolean"
  },
  "permission_enforcement": {
    "allowed_violations": ["string (repo-relative)"],
    "forbidden_violations": ["string (repo-relative)"],
    "all_actual_changes_permitted": "boolean"
  },
  "diagnostics": {
    "actor_exit_code": "integer | null",
    "actor_stdout_tail": "string (max 4096 bytes)",
    "actor_stderr_tail": "string (max 4096 bytes)",
    "adapter_error_message": "string | null"
  },
  "sanitization": {
    "redaction_applied": "boolean",
    "redaction_count": "integer >= 0",
    "truncation_applied": "boolean",
    "truncated_fields": ["string (canonical field path, max 64 entries, sorted)"]
  },
  "integrity_scope": {
    "tracked_files_inspected": "boolean (always true)",
    "untracked_non_ignored_inspected": "boolean (always true)",
    "ignored_files_inspected": "boolean (always false in WP-AL-1C5)",
    "advanced_symlink_inspected": "boolean (always false in WP-AL-1C5)",
    "note": "string (short explanation of scope limitations)"
  },
  "completed_at": "2026-08-06T12:00:00Z (ISO-8601 UTC)"
}
```

## Top-Level Required Fields (always present, every status)

Nine fields are always required regardless of `adapter_status`:

| Field | Type | Constraints |
|-------|------|-------------|
| `schema_version` | string | Must be exactly `"1.0"` |
| `run_id` | string | Non-empty, max 256 bytes, alphanumeric + `_` + `-` + `:` only |
| `story_id` | string | Non-empty, max 128 bytes, alphanumeric + `_` + `-` only |
| `attempt` | integer | >= 1, bool not accepted |
| `adapter_status` | string | Closed enum (14 values, see below) |
| `diagnostics` | object | Always present (see nested shape below) |
| `sanitization` | object | Always present (see nested shape below) |
| `integrity_scope` | object | Always present (see nested shape below) |
| `completed_at` | string | ISO-8601 UTC format: `YYYY-MM-DDTHH:MM:SSZ` or with fractional seconds |

## Conditional Fields (status-dependent presence)

Four fields are conditionally present. Presence depends on `adapter_status`
as defined below. For these fields, an explicit JSON `null` value is treated
as absence: validation behaves identically whether the key is missing or its
value is `null`.

| Field | Type |
|-------|------|
| `repair_result_summary` | object \| absent |
| `workspace_changes` | object \| absent |
| `reconciliation` | object \| absent |
| `permission_enforcement` | object \| absent |

## Status-Dependent Presence Rules

The validator enforces the following exact partition over the 14
`adapter_status` values. No status falls through a permissive default.

### ADAPTER_SUCCESS

All four conditional fields are required:

- `repair_result_summary`: required
- `workspace_changes`: required
- `reconciliation`: required
- `permission_enforcement`: required

### Pre-invocation failures (actor was never invoked)

Applies to: `ADAPTER_DIRTY_BASELINE`, `ADAPTER_SOURCE_REVISION_DRIFT`,
`ADAPTER_INTERNAL_ERROR`.

None of the four conditional fields may be present:

- `repair_result_summary`: forbidden
- `workspace_changes`: forbidden
- `reconciliation`: forbidden
- `permission_enforcement`: forbidden

### Post-invocation failures with no valid actor result

Applies to: `ADAPTER_TIMEOUT`, `ADAPTER_NON_ZERO_EXIT`,
`ADAPTER_MISSING_RESULT`, `ADAPTER_MALFORMED_RESULT`,
`ADAPTER_CONTRACT_VIOLATION`, `ADAPTER_IDENTITY_MISMATCH`,
`ADAPTER_OUTPUT_SIZE_EXCEEDED`.

- `repair_result_summary`: forbidden (actor produced no valid WP-AL-1C4 result)
- `workspace_changes`: optional (present when the adapter inspected the
  workspace after invocation; not required)
- `reconciliation`: optional
- `permission_enforcement`: optional

### Post-invocation enforcement failures

Applies to: `ADAPTER_FORBIDDEN_CHANGE`, `ADAPTER_UNDECLARED_CHANGE`,
`ADAPTER_DECLARED_MISSING`.

- `repair_result_summary`: optional (actor may have produced a valid result)
- `workspace_changes`: required (the workspace was inspected)
- `reconciliation`: optional
- `permission_enforcement`: required for `ADAPTER_FORBIDDEN_CHANGE`;
  optional for `ADAPTER_UNDECLARED_CHANGE` and `ADAPTER_DECLARED_MISSING`

## AdapterStatus Enum (14 values)

| Value | Category | Description |
|-------|----------|-------------|
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

## Nested Object Shapes

### repair_result_summary

Present when actor produced a valid WP-AL-1C4 repair result. Contains validated
summary of actor's claim. Does NOT prove workspace integrity.

| Field | Type | Constraints |
|-------|------|-------------|
| `status` | string | `"REPAIRED"` \| `"NO_CHANGE"` \| `"ERROR"` |
| `changed` | boolean | Matches WP-AL-1C4 result |
| `changed_files` | array | Strings, max 50 entries, repo-relative, no traversal |
| `recommended_action` | string | `"reverify"` \| `"abort"` \| `"human_review"` |
| `summary` | string | Max 2048 bytes |

**Cross-field invariants (from WP-AL-1C4):**
- `REPAIRED`: `changed == true`, `len(changed_files) >= 1`, `recommended_action == "reverify"`
- `NO_CHANGE`: `changed == false`, `len(changed_files) == 0`, `recommended_action in ("abort", "human_review")`
- `ERROR`: No constraint on `changed` or `changed_files`, `recommended_action in ("abort", "human_review")`

### workspace_changes

Documents actual workspace changes observed after actor invocation. All path
lists sorted lexicographically.

| Field | Type | Constraints |
|-------|------|-------------|
| `baseline_source_revision` | string | 40-char lowercase hex |
| `post_source_revision` | string | 40-char lowercase hex |
| `source_revision_stable` | boolean | `baseline_source_revision == post_source_revision` |
| `added` | array | Strings, repo-relative, sorted, max 512 bytes each |
| `modified` | array | Strings, repo-relative, sorted, max 512 bytes each |
| `deleted` | array | Strings, repo-relative, sorted, max 512 bytes each |
| `untracked` | array | Strings, repo-relative, sorted, max 512 bytes each |

**Invariants:**
- All paths must be relative (no leading `/`), no `..` traversal, no Windows drive letters
- All path lists must be sorted lexicographically
- No duplicate paths within any single list
- Paths in `added`, `modified`, `deleted` are tracked files (from `git status`)
- Paths in `untracked` are untracked non-ignored files (from `git ls-files --others --exclude-standard`)

### reconciliation

Compares declared `changed_files` from WP-AL-1C4 result against actual workspace
changes. WP-AL-1C5 requires exact match.

| Field | Type | Constraints |
|-------|------|-------------|
| `declared_files` | array | Strings, sorted, from WP-AL-1C4 `changed_files` |
| `actual_files` | array | Strings, sorted, union of all workspace_changes lists |
| `undeclared_changes` | array | Strings, sorted, `actual - declared` |
| `declared_but_missing` | array | Strings, sorted, `declared - actual` |
| `exact_match` | boolean | `declared_files == actual_files` |

**Invariants:**
- `undeclared_changes = actual_files - declared_files` (set difference)
- `declared_but_missing = declared_files - actual_files` (set difference)
- `exact_match == (len(undeclared_changes) == 0 and len(declared_but_missing) == 0)`
- When `exact_match == false`, adapter status is `ADAPTER_UNDECLARED_CHANGE` or `ADAPTER_DECLARED_MISSING`

### permission_enforcement

Documents permission violations on actual workspace changes.

| Field | Type | Constraints |
|-------|------|-------------|
| `allowed_violations` | array | Strings, actual changes not matching any `allowed_paths` pattern |
| `forbidden_violations` | array | Strings, actual changes matching any `forbidden_paths` pattern |
| `all_actual_changes_permitted` | boolean | `len(allowed_violations) == 0 and len(forbidden_violations) == 0` |

**Invariants:**
- Forbidden paths take precedence over allowed paths
- When `all_actual_changes_permitted == false`, adapter status is `ADAPTER_FORBIDDEN_CHANGE`

### diagnostics

Bounded diagnostic output from actor invocation.

| Field | Type | Constraints |
|-------|------|-------------|
| `actor_exit_code` | integer \| null | Exit code from actor subprocess, null if not started |
| `actor_stdout_tail` | string | Max 4096 bytes, sanitized |
| `actor_stderr_tail` | string | Max 4096 bytes, sanitized |
| `adapter_error_message` | string \| null | Human-readable error detail, max 1024 bytes, null on success |

**Invariants:**
- `actor_stdout_tail` and `actor_stderr_tail` are sanitized (no secrets, no absolute paths)
- `adapter_error_message` is sanitized and bounded (max 1024 bytes)

### sanitization

Metadata about sanitization applied to actor output and diagnostics.

| Field | Type | Constraints |
|-------|------|-------------|
| `redaction_applied` | boolean | True if any redaction occurred |
| `redaction_count` | integer | >= 0, total redaction substitutions |
| `truncation_applied` | boolean | True if any field was truncated |
| `truncated_fields` | array | Strings, canonical field paths, max 64 entries, each entry max 256 UTF-8 bytes, sorted |

**Invariants:**
- `truncated_fields` uses dot notation: `"actor_stdout_tail"`, `"actor_stderr_tail"`
- `truncated_fields` sorted lexicographically
- Each `truncated_fields` entry is bounded to 256 UTF-8 bytes
- When `redaction_applied == false`, `redaction_count == 0`
- When `truncation_applied == false`, `len(truncated_fields) == 0`

### integrity_scope

Documents what the adapter inspected and what it did not. Consumers must not
interpret the adapter result as proof of complete workspace integrity.

| Field | Type | Constraints |
|-------|------|-------------|
| `tracked_files_inspected` | boolean | Always `true` in WP-AL-1C5 |
| `untracked_non_ignored_inspected` | boolean | Always `true` in WP-AL-1C5 |
| `ignored_files_inspected` | boolean | Always `false` in WP-AL-1C5 |
| `advanced_symlink_inspected` | boolean | Always `false` in WP-AL-1C5 |
| `note` | string | Short explanation of scope limitations, max 512 UTF-8 bytes |

**Invariants:**
- WP-AL-1C5 does NOT inspect ignored files (`.gitignore`)
- WP-AL-1C5 does NOT perform advanced symlink-target inspection
- The `note` field must explain these limitations
- The `note` field is bounded to 512 UTF-8 bytes
- Consumers must not claim complete workspace integrity based on this result

## Path Safety Rules

All paths in `workspace_changes`, `reconciliation`, and `permission_enforcement`
must be:
- Relative (no leading `/`)
- No `..` traversal components
- No `.` single-dot components
- No empty segments (no `//`)
- No Windows drive letters (`C:`) or UNC paths (`\\server\share`)
- No null bytes
- Max 512 bytes per path string
- No backslashes (use forward slash)

## Determinism Rules

- Builder does not call `datetime.now()`, `time.time()`, or any internal time function
- All timestamps supplied explicitly by caller as ISO-8601 strings
- All path lists sorted lexicographically
- Canonical JSON is deterministic: same inputs produce identical bytes
- Pretty JSON is deterministic: same inputs produce identical string
- Builder does not mutate caller-provided dictionaries or lists

## Canonical Serialization

### Canonical bytes (for determinism tests, digest comparisons)

```python
def canonical_json_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
```

### Pretty JSON (for human-readable artifacts)

```python
def pretty_json_string(obj: dict[str, Any]) -> str:
    text = json.dumps(
        obj,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines) + "\n"
```

## Unknown Field Policy

Unknown fields in adapter-result input are rejected during validation. The
adapter produces a closed schema with no extension points in WP-AL-1C5.

## Relationship to Other Schemas

- WP-AL-1C4 repair result schema: `.agent-loop/repair/SCHEMA.md`
- WP-AL-1C2 review adapter schema: `.agent-loop/review-adapter/SCHEMA.md`
- The adapter result is a separate artifact from the WP-AL-1C4 repair result
- The adapter result may reference a validated summary of the WP-AL-1C4 repair result

## Non-Goals

- No LLM invocation
- No repair agent logic
- No workspace inspection execution (this WP documents the schema only)
- No reconciliation execution (this WP documents the schema only)
- No permission enforcement execution (this WP documents the schema only)
- No atomic file writes (deferred to process-runner slice)
- No subprocess invocation (deferred to process-runner slice)
