# Review Contract Schema v1.0

## Purpose

Versioned review-request and review-result contracts for the human-review phase
of the agent loop. Provides structural validators, a two-root referential
validator, and a deterministic builder. No LLM invocation, no adapter, no
repair, no orchestration.

## Review Request Schema v1.0

```json
{
  "schema_version": "1.0",
  "run_id": "string",
  "story_id": "string",
  "review_iteration": 1,
  "repair_iteration": 0,
  "triggered_by": "initial_verify_pass | post_repair_verify_pass",
  "generated_at": "2026-08-04T12:00:00Z",
  "reviewer_id": "mock-reviewer",
  "manifest_ref": {
    "path": "scripts/agent-loop/templates/story-prd.json",
    "schema_version": "1.0",
    "sha256": "64-char lowercase hex"
  },
  "manifest_excerpt": {
    "title": "string (max 256 bytes)",
    "description": "string (max 2048 bytes)",
    "acceptance_criteria": ["string (max 512 bytes each, max 20 entries)"],
    "repair_guidance": ["string (max 256 bytes each, max 10 entries)"],
    "allowed_paths": ["string (repo-relative, no traversal)"],
    "forbidden_paths": ["string (repo-relative, no traversal)"]
  },
  "failure_context_ref": {
    "path": "reports/failure-context.json",
    "schema_version": "1.0",
    "sha256": "64-char lowercase hex"
  },
  "candidate_identity": {
    "base_commit": "40-char lowercase hex",
    "candidate_commit": "40-char lowercase hex | null",
    "candidate_state": "committed | working_tree",
    "candidate_diff_digest": "64-char lowercase hex"
  },
  "sanitization": {
    "redaction_applied": false,
    "redaction_count": 0,
    "truncation_applied": false,
    "truncated_fields": []
  }
}
```

## Review Result Schema v1.0

```json
{
  "schema_version": "1.0",
  "run_id": "string",
  "story_id": "string",
  "review_iteration": 1,
  "repair_iteration": 0,
  "status": "PASS | FAIL | ERROR",
  "status_generated_at": "2026-08-04T12:05:00Z",
  "reviewer_id": "mock-reviewer",
  "findings": [
    {
      "finding_id": "deterministic-id",
      "severity": "BLOCKER | MAJOR | MINOR | INFO",
      "category": "string (max 64 bytes)",
      "summary": "string (max 1024 bytes)",
      "evidence_refs": ["relative/path/to/artifact"],
      "recommended_fix": "string (max 512 bytes)"
    }
  ],
  "decision_rationale": "string (max 2048 bytes)",
  "recommended_action": "none | repair | human_review",
  "sanitization": {
    "redaction_applied": false,
    "redaction_count": 0,
    "truncation_applied": false,
    "truncated_fields": []
  }
}
```

## PASS | FAIL | ERROR Semantics

- **PASS**: accepted review outcome, implementation is acceptable.
- **FAIL**: rejected review outcome, one or more actionable findings exist.
- **ERROR**: reviewer/adapter infrastructure or contract failure, review could
  not be completed reliably.

**ERROR must never fall through to VERIFIED.** ERROR is reserved for
adapter/runtime failures, not implementation quality. ERROR must never be
interpreted as successful verification or successful review.

### Report Compatibility (report-story.sh lines 97-107)

- PASS/FAIL: compatible (matches existing semantics).
- ERROR: requires future integration; WP-AL-1C1 does not modify
  report-story.sh and does not add ERROR handling to it.

### Cross-Field Rules

**PASS:**
- `recommended_action` must be `"none"`
- findings must be empty or contain only MINOR/INFO severity

**FAIL:**
- `recommended_action` must be `"repair"` or `"human_review"`
- at least one finding with severity BLOCKER or MAJOR

**ERROR:**
- `recommended_action` must be `"human_review"`
- must never be treated as PASS or VERIFIED

## Path-Base Rules

| Path field | Resolved relative to |
|---|---|
| `manifest_ref.path` | `repo_root` |
| `failure_context_ref.path` | `run_dir` |
| `manifest_excerpt.allowed_paths[]` | `repo_root` |
| `manifest_excerpt.forbidden_paths[]` | `repo_root` |
| `findings[].evidence_refs[]` | `run_dir` |

All paths must be relative (no leading `/`), no `..` traversal, no Windows
drive letters or UNC paths.

## Exact-Byte SHA-256 Binding

- `manifest_ref.sha256` = SHA-256 of exact manifest file bytes on disk
- `failure_context_ref.sha256` = SHA-256 of exact failure-context file bytes on disk

Referential validation computes the hash from the file and compares to the
declared digest. Any mismatch is a contract violation.

## Field Binding Rules

| Request field | Bound to |
|---|---|
| `request.story_id` | manifest `story_id` |
| `request.run_id` | failure-context `run_id` |
| `request.story_id` | failure-context `story_id` |
| `request.candidate_identity` | failure-context `candidate_identity` (exact match) |

No `run_id` derivation from manifest `story_id`. The binding for `run_id` is
exclusively `request.run_id` ↔ `failure-context.run_id`.

Failure-context `overall_verification_status` must be `"PASS"` (review only
runs after successful verification).

## Iteration Invariants

- `review_iteration` >= 1
- `repair_iteration` >= 0
- `review_iteration` == `repair_iteration + 1`
- If `triggered_by` == `"initial_verify_pass"` then `repair_iteration` == 0
- If `triggered_by` == `"post_repair_verify_pass"` then `repair_iteration` >= 1

## Structural Validation Rules

### Request (no filesystem access)

- `schema_version` must be exactly `"1.0"`
- `run_id` non-empty string, max 256 bytes, alphanumeric + underscores + hyphens + colons only
- `story_id` non-empty string, max 128 bytes, alphanumeric + underscores + hyphens only
- `review_iteration` integer >= 1
- `repair_iteration` integer >= 0
- `review_iteration` must equal `repair_iteration + 1`
- `triggered_by` must be `"initial_verify_pass"` or `"post_repair_verify_pass"`
- If `triggered_by` == `"initial_verify_pass"` then `repair_iteration` == 0
- If `triggered_by` == `"post_repair_verify_pass"` then `repair_iteration` >= 1
- `generated_at` ISO-8601 UTC format
- `reviewer_id` non-empty string, max 128 bytes, alphanumeric + hyphens + underscores only
- `manifest_ref.path` repo-relative, no `..`, no leading `/`, max 512 bytes
- `manifest_ref.schema_version` must be `"1.0"`
- `manifest_ref.sha256` 64-char lowercase hex
- `manifest_excerpt.title` max 256 bytes
- `manifest_excerpt.description` max 2048 bytes
- `manifest_excerpt.acceptance_criteria` array, max 20 entries, each max 512 bytes
- `manifest_excerpt.repair_guidance` array, max 10 entries, each max 256 bytes
- `manifest_excerpt.allowed_paths` array, each repo-relative, no `..`, no leading `/`
- `manifest_excerpt.forbidden_paths` array, each repo-relative, no `..`, no leading `/`
- `failure_context_ref.path` run_dir-relative, no `..`, no leading `/`, max 512 bytes
- `failure_context_ref.schema_version` must be `"1.0"`
- `failure_context_ref.sha256` 64-char lowercase hex
- `candidate_identity.base_commit` 40-char lowercase hex
- `candidate_identity.candidate_commit` 40-char lowercase hex or null
- `candidate_identity.candidate_state` `"committed"` or `"working_tree"`
- If `candidate_state` == `"committed"` then `candidate_commit` is non-null
- If `candidate_state` == `"working_tree"` then `candidate_commit` is null
- `candidate_identity.candidate_diff_digest` 64-char lowercase hex
- `sanitization.redaction_applied` boolean
- `sanitization.redaction_count` integer >= 0
- `sanitization.truncation_applied` boolean
- `sanitization.truncated_fields` array, max 64 entries, each string max 256 bytes

### Result (no filesystem access)

- `schema_version` must be exactly `"1.0"`
- `run_id` non-empty string, max 256 bytes
- `story_id` non-empty string, max 128 bytes
- `review_iteration` integer >= 1
- `repair_iteration` integer >= 0
- `review_iteration` must equal `repair_iteration + 1`
- `status` must be `"PASS"`, `"FAIL"`, or `"ERROR"`
- `status_generated_at` ISO-8601 UTC format
- `reviewer_id` non-empty string, max 128 bytes
- `findings` is array
- Each finding:
    - `finding_id` non-empty string, max 128 bytes
    - `severity` must be `"BLOCKER"`, `"MAJOR"`, `"MINOR"`, or `"INFO"`
    - `category` non-empty string, max 64 bytes
    - `summary` non-empty string, max 1024 bytes
    - `evidence_refs` array, each run_dir-relative, no `..`, no leading `/`, max 20 entries
    - `recommended_fix` string, max 512 bytes
- `findings[].finding_id` unique within result
- `findings` array ordered by `finding_id` (lexicographic)
- `decision_rationale` string, max 2048 bytes
- `recommended_action` must be `"none"`, `"repair"`, or `"human_review"`
- `sanitization` object with same structure as request
- PASS/FAIL/ERROR cross-field rules (see above)

## Referential Validation Rules

Requires filesystem access and two root paths.

- `manifest_ref.path` resolved relative to `repo_root`
- Resolved manifest file must exist
- Resolved manifest file SHA-256 must match `manifest_ref.sha256` (exact bytes)
- Resolved manifest must be valid JSON
- Resolved manifest must have `schema_version` == `"1.0"`
- `manifest_excerpt.title` must equal manifest `title` after sanitization
- `manifest_excerpt.description` must equal manifest `description` after sanitization
- `manifest_excerpt.acceptance_criteria` must equal manifest `acceptance_criteria` after sanitization
- `manifest_excerpt.repair_guidance` must equal manifest `repair_guidance` after sanitization (if present)
- `manifest_excerpt.allowed_paths` must equal manifest `allowed_paths`
- `manifest_excerpt.forbidden_paths` must equal manifest `forbidden_paths`
- `story_id` must equal manifest `story_id`
- `failure_context_ref.path` resolved relative to `run_dir`
- Resolved failure-context file must exist
- Resolved failure-context file SHA-256 must match `failure_context_ref.sha256` (exact bytes)
- Resolved failure-context must be valid JSON
- Resolved failure-context must have `schema_version` == `"1.0"`
- `run_id` must equal failure-context `run_id`
- `story_id` must equal failure-context `story_id`
- `candidate_identity` must exactly equal failure-context `candidate_identity`
- Failure-context `overall_verification_status` must be `"PASS"`

## Sanitization Metadata

```json
{
  "redaction_applied": boolean,
  "redaction_count": "integer >= 0",
  "truncation_applied": boolean,
  "truncated_fields": ["canonical.field.path"]
}
```

- `redaction_applied`: true if any redaction occurred in any field.
- `redaction_count`: total number of redaction substitutions across all fields.
- `truncation_applied`: true if any field was truncated.
- `truncated_fields`: canonical field paths that were truncated (max 64 entries).
- Canonical field paths use dot notation: `"manifest_excerpt.title"`,
  `"manifest_excerpt.acceptance_criteria[0]"`.
- Array ordered lexicographically.
- No removed content included in output.
- No absolute filesystem paths.

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
| `reviewer_id` | 128 |
| `manifest_ref.path` | 512 |
| `failure_context_ref.path` | 512 |
| `manifest_excerpt.title` | 256 |
| `manifest_excerpt.description` | 2048 |
| `manifest_excerpt.acceptance_criteria[]` | 512 |
| `manifest_excerpt.repair_guidance[]` | 256 |
| `findings[].finding_id` | 128 |
| `findings[].category` | 64 |
| `findings[].summary` | 1024 |
| `findings[].recommended_fix` | 512 |
| `decision_rationale` | 2048 |

| Array field | Max entries |
|---|---|
| `manifest_excerpt.acceptance_criteria` | 20 |
| `manifest_excerpt.repair_guidance` | 10 |
| `findings[].evidence_refs` | 20 |
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

- Builder does not call `datetime.now()`, `time.time()`, or any internal time function.
- All timestamps supplied explicitly by caller as ISO-8601 strings.
- Canonical bytes are deterministic: same explicit inputs produce identical bytes.
- Pretty JSON is deterministic: same explicit inputs produce identical string.
- `findings` array ordered by `finding_id` (lexicographic).
- `findings[].evidence_refs` array ordered lexicographically.
- `sanitization.truncated_fields` array ordered lexicographically.
- `manifest_excerpt.acceptance_criteria` order preserved from manifest.
- `manifest_excerpt.repair_guidance` order preserved from manifest.
- `manifest_excerpt.allowed_paths` order preserved from manifest.
- `manifest_excerpt.forbidden_paths` order preserved from manifest.

## ERROR Compatibility Limitation

ERROR is defined in the review-result schema but is NOT integrated into
`report-story.sh`. Until ERROR integration exists, an ERROR review result
must not enter the normal final-report production path. The expected future
mapping for ERROR is `final_status` == `"INFRASTRUCTURE_ERROR"` or
`"HUMAN_REVIEW_REQUIRED"` (never `"VERIFIED"`).

## Relationship to Other Schemas

- Manifest schema: `.agent-loop/manifests/SCHEMA.md` (unchanged)
- Failure-context schema: `.agent-loop/failure-context/SCHEMA.md` (unchanged)
- Review schema: this document (`.agent-loop/review/SCHEMA.md`)

## Non-Goals

- No LLM invocation
- No reviewer/repair agent logic
- No run lifecycle / state machine
- No concurrency support
- No prompt design
- No adapter code
- No orchestrator wiring
- No modification to report-story.sh
