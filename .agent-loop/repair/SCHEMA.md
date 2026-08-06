# Repair Contract Schema v1.0

## Purpose

Versioned repair-request and repair-result contracts for the repair phase of
the agent loop. Provides structural validators, identity binding rules,
path-safety constraints, and a deterministic builder. No repair execution, no
adapter, no orchestrator wiring, no LLM invocation.

**Key invariants:**
- REPAIRED does NOT mean verification passed (repair success ≠ verification success)
- Contract validation does NOT prove workspace integrity (only validates artifact claims)
- The repair actor cannot define or expand allowed_paths or forbidden_paths
- No PARTIAL status; only REPAIRED, NO_CHANGE, ERROR

## Repair Request Schema v1.0

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

## Repair Result Schema v1.0

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

## REPAIRED | NO_CHANGE | ERROR Semantics

- **REPAIRED**: repair actor made changes. Requires `changed == true` AND
  `len(changed_files) >= 1` AND `recommended_action == "reverify"`.
- **NO_CHANGE**: repair actor chose not to change anything. Requires
  `changed == false` AND `len(changed_files) == 0` AND
  `recommended_action in ("abort", "human_review")`.
- **ERROR**: repair actor infrastructure failure. No constraint on `changed`
  or `changed_files`. Requires `recommended_action in ("abort", "human_review")`.

**Critical invariant**: REPAIRED status does NOT mean verification passed.
Repair success and post-repair verification are distinct. The orchestrator
must re-run verification after REPAIRED to determine whether the repair
actually fixed the problem.

### Cross-Field Rules

**REPAIRED:**
- `changed` must be `true`
- `changed_files` must be non-empty
- `recommended_action` must be `"reverify"`

**NO_CHANGE:**
- `changed` must be `false`
- `changed_files` must be empty
- `recommended_action` must be `"abort"` or `"human_review"`

**ERROR:**
- No constraint on `changed` or `changed_files` (may be indeterminate)
- `recommended_action` must be `"abort"` or `"human_review"`

**Request cross-field rules:**
- If `failure_class == "review_fail"` then `review_result_ref` must be non-null
- If `failure_class == "verification_fail"` then `review_result_ref` may be null
- If `requested_action == "fix_review_findings"` then `failure_class` must be `"review_fail"`

## Path-Base Rules

| Path field | Resolved relative to |
|---|---|
| `failure_context_ref.path` | `run_dir` |
| `verification_result_ref.path` | `run_dir` |
| `review_result_ref.path` | `run_dir` |
| `allowed_paths[]` | `repo_root` |
| `forbidden_paths[]` | `repo_root` |
| `changed_files[]` | `repo_root` |

All paths must be relative (no leading `/`), no `..` traversal, no Windows
drive letters or UNC paths.

## Exact-Byte SHA-256 Binding

- `failure_context_ref.sha256` = SHA-256 of exact failure-context file bytes on disk
- `verification_result_ref.sha256` = SHA-256 of exact verify-result file bytes on disk
- `review_result_ref.sha256` = SHA-256 of exact review-result file bytes on disk (if present)

Referential validation computes the hash from the file and compares to the
declared digest. Any mismatch is a contract violation.

## Identity Binding Rules

| Result field | Bound to |
|---|---|
| `result.run_id` | request `run_id` |
| `result.story_id` | request `story_id` |
| `result.attempt` | request `attempt` |
| `result.source_revision` | request `source_revision` |

## Path Safety Rules

### Repository-Root Containment

- All paths in `changed_files`, `allowed_paths`, `forbidden_paths`, and
  `*_ref.path` must be normalized:
  - No leading `/` (must be relative)
  - No `..` traversal components
  - No `.` single-dot components
  - No empty segments (no `//`)
  - No Windows drive letters (`C:`) or UNC paths (`\\server\share`)
  - No null bytes
  - Max 512 bytes per path string

### Forbidden-Path Protection

- `forbidden_paths` use gitwildmatch semantics (same as manifest)
- A `changed_files` entry matching any `forbidden_paths` pattern is a
  contract violation
- Forbidden paths take precedence over allowed paths

### Allowed-Path Allowlist

- `allowed_paths` use gitwildmatch semantics
- A `changed_files` entry must match at least one `allowed_paths` pattern
  (if `allowed_paths` is non-empty)
- If `allowed_paths` is empty, all non-forbidden paths are allowed
  (defensive; manifest should always provide allowed_paths)

### Duplicate Detection

- `changed_files` must not contain duplicate entries (exact string match
  after normalization)

### Maximum Changed-File Count

- `changed_files` array: max 50 entries

## Structural Validation Rules

### Request (no filesystem access)

- `schema_version` must be exactly `"1.0"`
- `run_id` non-empty string, max 256 bytes, alphanumeric + underscores + hyphens + colons only
- `story_id` non-empty string, max 128 bytes, alphanumeric + underscores + hyphens only
- `attempt` integer >= 1
- `max_attempts` integer >= 1, `max_attempts >= attempt`
- `source_revision` 40-char lowercase hex
- `failure_class` must be `"verification_fail"` or `"review_fail"`
- `failure_summary` string, max 2048 bytes
- `failure_context_ref` object with `path`, `schema_version`, `sha256`
- `verification_result_ref` object with `path`, `schema_version`, `sha256`
- `review_result_ref` object with `path`, `schema_version`, `sha256` or null
- If `failure_class == "review_fail"` then `review_result_ref` must be non-null
- `allowed_paths` array of strings, each repo-relative, no `..`, no leading `/`
- `forbidden_paths` array of strings, each repo-relative, no `..`, no leading `/`
- `repair_guidance` array of strings, max 10 entries, each max 256 bytes
- `requested_action` must be `"fix_verification"` or `"fix_review_findings"`
- If `requested_action == "fix_review_findings"` then `failure_class` must be `"review_fail"`
- `generated_at` ISO-8601 UTC format

### Result (no filesystem access)

- `schema_version` must be exactly `"1.0"`
- `run_id` non-empty string, max 256 bytes, alphanumeric + underscores + hyphens + colons only
- `story_id` non-empty string, max 128 bytes, alphanumeric + underscores + hyphens only
- `attempt` integer >= 1
- `source_revision` 40-char lowercase hex
- `status` must be `"REPAIRED"`, `"NO_CHANGE"`, or `"ERROR"`
- `changed` boolean
- `changed_files` array of strings, each repo-relative, no `..`, no leading `/`, max 50 entries
- `changed_files` entries must be unique (no duplicates)
- `summary` string, max 2048 bytes
- `diagnostics` object with bounded sub-fields (optional)
  - `actions_taken` array, max 20 entries, each max 512 bytes
  - `obstacles_encountered` array, max 10 entries, each max 512 bytes
  - `confidence` optional, must be `"high"`, `"medium"`, or `"low"` if present
- `recommended_action` must be `"reverify"`, `"abort"`, or `"human_review"`
- `sanitization` object with `redaction_applied`, `redaction_count`, `truncation_applied`, `truncated_fields`
- `completed_at` ISO-8601 UTC format
- REPAIRED/NO_CHANGE/ERROR cross-field rules (see above)

## Referential Validation Rules

Requires filesystem access and two root paths.

- `failure_context_ref.path` resolved relative to `run_dir`
- Resolved failure-context file must exist
- Resolved failure-context file SHA-256 must match `failure_context_ref.sha256` (exact bytes)
- Resolved failure-context must be valid JSON
- Resolved failure-context must have `schema_version` == `"1.0"`
- `run_id` must equal failure-context `run_id`
- `story_id` must equal failure-context `story_id`
- `verification_result_ref.path` resolved relative to `run_dir`
- Resolved verify-result file must exist
- Resolved verify-result file SHA-256 must match `verification_result_ref.sha256` (exact bytes)
- Resolved verify-result must be valid JSON
- Resolved verify-result must have `schema_version` == `"1.0"`
- `review_result_ref.path` resolved relative to `run_dir` (if non-null)
- Resolved review-result file must exist (if review_result_ref is non-null)
- Resolved review-result file SHA-256 must match `review_result_ref.sha256` (if non-null)
- Resolved review-result must be valid JSON (if non-null)
- Resolved review-result must have `schema_version` == `"1.0"` (if non-null)

## Sanitization Metadata

```json
{
  "redaction_applied": boolean,
  "redaction_count": "integer >= 0",
  "truncation_applied": boolean,
  "truncated_fields": ["canonical.field.path"]
}
```

- `redaction_applied`: true if any redaction occurred in any field
- `redaction_count`: total number of redaction substitutions across all fields
- `truncation_applied`: true if any field was truncated
- `truncated_fields`: canonical field paths that were truncated (max 64 entries)
- Canonical field paths use dot notation: `"failure_summary"`,
  `"repair_guidance[0]"`, `"diagnostics.actions_taken[0]"`
- Array ordered lexicographically
- No removed content included in output
- No absolute filesystem paths

### Sanitization Pipeline (applied in order)

1. UTF-8 normalization (NFC form, invalid bytes replaced with U+FFFD)
2. Binary content detection (>30% non-printable in first 1KB → `"[REDACTED:binary_content]"`)
3. Control character removal (preserve `\n`, `\t`, `\r`; remove C0/C1 except DEL)
4. Base64 run detection (100+ alphanumeric+/+= → `"[REDACTED:base64_payload]"`)
5. Secret pattern redaction (stripe keys, GitHub tokens, AWS keys, Bearer/Basic auth, password/api_key/secret assignments, private key blocks)
6. URL query string stripping (preserve scheme+host+path, remove `?query`)
7. Byte truncation (per-field limits from bounded-field table)
8. Truncation marker: `"... [truncated: N bytes omitted]"`

**Rationale**: Binary content detection must run before control character removal because `is_binary_content()` checks for non-printable characters (including control characters like null bytes). If control characters were removed first, binary content detection would fail to identify actual binary data.

## Bounded Fields

| Field | Max bytes |
|---|---|
| `run_id` | 256 |
| `story_id` | 128 |
| `failure_summary` | 2048 |
| `failure_context_ref.path` | 512 |
| `verification_result_ref.path` | 512 |
| `review_result_ref.path` | 512 |
| `repair_guidance[]` | 256 |
| `summary` | 2048 |
| `diagnostics.actions_taken[]` | 512 |
| `diagnostics.obstacles_encountered[]` | 512 |

| Array field | Max entries |
|---|---|
| `repair_guidance` | 10 |
| `changed_files` | 50 |
| `diagnostics.actions_taken` | 20 |
| `diagnostics.obstacles_encountered` | 10 |
| `sanitization.truncated_fields` | 64 |

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

### Determinism Rules

- Builder does not call `datetime.now()`, `time.time()`, or any internal time function
- All timestamps supplied explicitly by caller as ISO-8601 strings
- Canonical bytes are deterministic: same explicit inputs produce identical bytes
- Pretty JSON is deterministic: same explicit inputs produce identical string
- `changed_files` array ordered lexicographically (for result)
- `sanitization.truncated_fields` array ordered lexicographically
- `allowed_paths` array order preserved from manifest
- `forbidden_paths` array order preserved from manifest
- `repair_guidance` array order preserved from manifest

## Two-Layer Validation Architecture

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

## Relationship to Other Schemas

- Manifest schema: `.agent-loop/manifests/SCHEMA.md` (unchanged)
- Failure-context schema: `.agent-loop/failure-context/SCHEMA.md` (unchanged)
- Review schema: `.agent-loop/review/SCHEMA.md` (unchanged)
- Repair schema: this document (`.agent-loop/repair/SCHEMA.md`)

## Non-Goals

- No LLM invocation
- No repair agent logic
- No run lifecycle / state machine
- No concurrency support
- No prompt design
- No adapter code
- No orchestrator wiring
- No modification to run-story.sh, verify-story.sh, or report-story.sh
- No harness scenarios (repair execution not implemented)
