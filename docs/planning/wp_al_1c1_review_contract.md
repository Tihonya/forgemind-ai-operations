# WP-AL-1C1 — Review Contract

**Status:** APPROVED FOR IMPLEMENTATION PLANNING, NOT STARTED

**Branch:** `chore/agent-loop-review-contract`
**Base:** `origin/main` @ `95d441da99c31b6f811ce3ba5ca9d75af607285c`

---

## 1. Objective

Define and implement a versioned review-request and review-result contract
(schema v1.0) for the human-review phase of the agent loop, including
structural validators, a two-root referential validator, and a deterministic
builder. No LLM invocation, no adapter, no repair, no orchestration work.

## 2. Review Request Schema v1.0

```json
{
  "schema_version": "1.0",
  "run_id": "string",
  "story_id": "string",
  "review_iteration": 1,
  "repair_iteration": 0,
  "triggered_by": "initial_verify_pass",
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
    "base_commit": "40-char hex",
    "candidate_commit": "40-char hex | null",
    "candidate_state": "committed | working_tree",
    "candidate_diff_digest": "64-char hex"
  },
  "sanitization": {
    "redaction_applied": false,
    "redaction_count": 0,
    "truncation_applied": false,
    "truncated_fields": []
  }
}
```

## 3. Review Result Schema v1.0

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

## 4. PASS | FAIL | ERROR Semantics

- **PASS**: accepted review outcome, implementation is acceptable.
- **FAIL**: rejected review outcome, one or more actionable findings exist.
- **ERROR**: reviewer/adapter infrastructure or contract failure, review could
  not be completed reliably.

**ERROR must never fall through to VERIFIED.** ERROR is reserved for
adapter/runtime failures, not implementation quality. ERROR must never be
interpreted as successful verification or successful review.

Until ERROR integration exists in report-story.sh, an ERROR review result
must not enter the normal final-report production path. The expected future
mapping for ERROR is `final_status` == `"INFRASTRUCTURE_ERROR"` or
`"HUMAN_REVIEW_REQUIRED"` (never `"VERIFIED"`).

### Report Compatibility (report-story.sh lines 97-107)

```python
if report.get("review") and report["review"].get("status") == "PASS":
    report["final_status"] = "ACCEPTED"
elif report.get("review") and report["review"].get("status") == "FAIL":
    report["final_status"] = "REVIEW_REJECTED"
else:
    report["final_status"] = "VERIFIED"
```

- PASS/FAIL: compatible (matches existing semantics).
- ERROR: requires future integration; WP-AL-1C1 does not modify
  report-story.sh and does not add ERROR handling to it.

## 5. Structural Validation APIs

Structural validation requires no filesystem access.

### validate_review_request

```python
def validate_review_request(request: dict[str, Any]) -> None:
    """
    Validate review-request structural invariants.
    Raises ReviewContractError on any violation.
    No filesystem access.
    """
```

### validate_review_result

```python
def validate_review_result(result: dict[str, Any]) -> None:
    """
    Validate review-result structural invariants.
    Raises ReviewContractError on any violation.
    No filesystem access.
    """
```

## 6. Referential Validation API

Referential validation requires filesystem access and two root paths.

### validate_review_request_references

```python
def validate_review_request_references(
    request: dict[str, Any],
    repo_root: Path,
    run_dir: Path,
) -> None:
    """
    Validate review-request referential invariants against filesystem.

    repo_root: repository root (manifest_ref.path resolved relative to this)
    run_dir:   current run's artifact directory (failure_context_ref.path resolved relative to this)

    Raises ReviewContractError on any violation.
    """
```

## 7. Builder API

```python
def build_review_request(
    repo_root: Path,
    run_dir: Path,
    manifest_path: Path,
    failure_context_path: Path,
    run_id: str,
    story_id: str,
    review_iteration: int,
    repair_iteration: int,
    triggered_by: str,
    generated_at: str,
    reviewer_id: str,
) -> dict[str, Any]:
    """
    Build review request with both structural and referential validation.

    manifest_path: absolute path to manifest (must be under repo_root)
    failure_context_path: absolute path to failure-context (must be under run_dir)
    generated_at: ISO-8601 timestamp supplied by caller (no internal time call)
    """
```

## 8. Path-Base Rules

| Path field | Resolved relative to |
|---|---|
| `manifest_ref.path` | `repo_root` |
| `failure_context_ref.path` | `run_dir` |
| `manifest_excerpt.allowed_paths[]` | `repo_root` |
| `manifest_excerpt.forbidden_paths[]` | `repo_root` |
| `findings[].evidence_refs[]` | `run_dir` |

All paths must be relative (no leading `/`), no `..` traversal, no Windows
drive letters or UNC paths.

## 9. Exact-Byte SHA-256 Binding

- `manifest_ref.sha256` = SHA-256 of exact manifest file bytes on disk
- `failure_context_ref.sha256` = SHA-256 of exact failure-context file bytes on disk

Referential validation computes the hash from the file and compares to the
declared digest. Any mismatch is a contract violation.

## 10. Field Binding Rules

| Request field | Bound to |
|---|---|
| `request.story_id` | manifest `story_id` |
| `request.run_id` | failure-context `run_id` |
| `request.story_id` | failure-context `story_id` |
| `request.candidate_identity` | failure-context `candidate_identity` (exact match) |

**No run_id derivation from manifest story_id.** The binding for `run_id` is
exclusively `request.run_id` ↔ `failure-context.run_id`.

Failure-context `overall_verification_status` must be `"PASS"` (review only
runs after successful verification).

## 11. Iteration Rules

- `review_iteration` >= 1
- `repair_iteration` >= 0
- `review_iteration` == `repair_iteration + 1`
- If `triggered_by` == `"initial_verify_pass"` then `repair_iteration` == 0
- If `triggered_by` == `"post_repair_verify_pass"` then `repair_iteration` >= 1

## 12. Structural Invariants

### Request structural validation (no filesystem access)

- `schema_version` must be exactly `"1.0"`
- `run_id` non-empty string, max 256 bytes, alphanumeric + underscores + hyphens + colons only
- `story_id` non-empty string, max 128 bytes, alphanumeric + underscores + hyphens only
- `review_iteration` integer >= 1
- `repair_iteration` integer >= 0
- `review_iteration` must equal `repair_iteration + 1`
- `triggered_by` must be `"initial_verify_pass"` or `"post_repair_verify_pass"`
- If `triggered_by` == `"initial_verify_pass"` then `repair_iteration` == 0
- If `triggered_by` == `"post_repair_verify_pass"` then `repair_iteration` >= 1
- `generated_at` ISO-8601 UTC format (`YYYY-MM-DDTHH:MM:SS.sssZ` or `YYYY-MM-DDTHH:MM:SSZ`)
- `reviewer_id` non-empty string, max 128 bytes, alphanumeric + hyphens + underscores only
- `manifest_ref.path` is repo-relative (no leading `/`), no `..` traversal, max 512 bytes
- `manifest_ref.schema_version` must be `"1.0"`
- `manifest_ref.sha256` is 64-char lowercase hex
- `manifest_excerpt.title` max 256 bytes after sanitization
- `manifest_excerpt.description` max 2048 bytes after sanitization
- `manifest_excerpt.acceptance_criteria` array, max 20 entries, each max 512 bytes
- `manifest_excerpt.repair_guidance` array, max 10 entries, each max 256 bytes
- `manifest_excerpt.allowed_paths` array, each repo-relative, no `..`, no leading `/`
- `manifest_excerpt.forbidden_paths` array, each repo-relative, no `..`, no leading `/`
- `failure_context_ref.path` is run_dir-relative (no leading `/`), no `..` traversal, max 512 bytes
- `failure_context_ref.schema_version` must be `"1.0"`
- `failure_context_ref.sha256` is 64-char lowercase hex
- `candidate_identity.base_commit` is 40-char lowercase hex
- `candidate_identity.candidate_commit` is 40-char lowercase hex or null
- `candidate_identity.candidate_state` is `"committed"` or `"working_tree"`
- If `candidate_state` == `"committed"` then `candidate_commit` is non-null
- If `candidate_state` == `"working_tree"` then `candidate_commit` is null
- `candidate_identity.candidate_diff_digest` is 64-char lowercase hex
- `sanitization.redaction_applied` is boolean
- `sanitization.redaction_count` is integer >= 0
- `sanitization.truncation_applied` is boolean
- `sanitization.truncated_fields` is array, max 64 entries, each string max 256 bytes

### Result structural validation (no filesystem access)

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

### Referential validation (filesystem required, two-root)

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

## 13. Canonical Serialization

### Canonical bytes (for determinism tests, digest comparisons, exact-output comparisons)

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

### Determinism rules

- Builder does not call `datetime.now()`, `time.time()`, or any internal time function.
- All timestamps supplied explicitly by caller as ISO-8601 strings.
- Canonical bytes are deterministic: same explicit inputs produce identical bytes.
- Pretty JSON is deterministic: same explicit inputs produce identical string.
- `findings` array ordered by `finding_id` (lexicographic).
- `findings[].evidence_refs` array ordered lexicographically.
- `sanitization.truncated_fields` array ordered lexicographically.
- `manifest_excerpt.acceptance_criteria` array order preserved from manifest.
- `manifest_excerpt.repair_guidance` array order preserved from manifest.
- `manifest_excerpt.allowed_paths` array order preserved from manifest.
- `manifest_excerpt.forbidden_paths` array order preserved from manifest.

## 14. Sanitization Metadata Contract

### Request-level and result-level `sanitization` object

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
- `truncated_fields`: array of canonical field paths that were truncated (max 64 entries).
- Canonical field paths use dot notation: `"manifest_excerpt.title"`, `"manifest_excerpt.acceptance_criteria[0]"`.
- Array ordered lexicographically.
- No removed content included in output.
- No absolute filesystem paths.
- Builder computes sanitization metadata before publication.

### Sanitization pipeline (applied in order)

1. UTF-8 normalization (NFC form, invalid bytes replaced with U+FFFD)
2. Control character removal (preserve `\n`, `\t`, `\r`; remove C0/C1 except DEL)
3. Binary content detection (if >30% non-printable in first 1KB, replace with `"[REDACTED:binary_content]"`)
4. Base64 run detection (runs of 100+ alphanumeric+/+=, replace with `"[REDACTED:base64_payload]"`)
5. Secret pattern redaction (stripe keys, GitHub tokens, AWS keys, Bearer/Basic auth, password/api_key/secret assignments, private key blocks)
6. URL query string stripping (preserve scheme+host+path, remove `?query`)
7. Byte truncation (per-field limits from bounded-field table)
8. Truncation marker: `"... [truncated: N bytes omitted]"`

## 15. Reusable Sanitizer API Signatures

Existing module-level functions from `scripts/agent-loop/lib/failure_context.py`,
approved as a narrow dependency for WP-AL-1C1. These are not a stable public
repository API; they are reused here under a narrow import contract.

```python
def normalize_utf8(text: str) -> str:
    """Normalize to NFC, replace invalid bytes with U+FFFD."""

def sanitize_control_characters(text: str) -> str:
    """Remove or replace non-printable control characters, preserve \\n\\t\\r."""

def is_binary_content(text: str, threshold: float = 0.3) -> bool:
    """Detect if content appears to be binary (high ratio of non-printable chars)."""

def redact_base64_runs(text: str, min_length: int = 100) -> tuple[str, int]:
    """Detect and redact long base64-like strings. Returns (redacted_text, count)."""

def redact_text(text: str) -> tuple[str, int]:
    """Apply redaction patterns and safety sanitization. Returns (sanitized_text, count)."""

def truncate_text(text: str, max_lines: int, max_bytes: int, source_artifact: str) -> dict[str, Any]:
    """Truncate text to line/byte limits. Returns metadata dict."""
```

### Import in review_contract.py

```python
from failure_context import (
    normalize_utf8,
    sanitize_control_characters,
    is_binary_content,
    redact_base64_runs,
    redact_text,
    truncate_text,
)
```

No modification to `failure_context.py`. No duplication of sanitization logic.
No private (underscore-prefixed) function imports.

## 16. Test Matrix

### Structural validation tests (no filesystem) — 30 cases

| ID | Case | Expected |
|----|------|----------|
| S01 | Valid review request (all fields, no sanitization needed) | validator returns OK |
| S02 | Valid review result (PASS, no findings) | validator returns OK |
| S03 | Valid review result (FAIL, one BLOCKER finding) | validator returns OK |
| S04 | Valid review result (ERROR, infrastructure finding) | validator returns OK |
| S05 | Missing schema_version | validator rejects |
| S06 | Invalid status value ("ACCEPT") | validator rejects |
| S07 | Oversized decision_rationale (2049 bytes) | validator rejects |
| S08 | Oversized findings[].summary (1025 bytes) | validator rejects |
| S09 | Too many acceptance_criteria (21 entries) | validator rejects |
| S10 | Path traversal in failure_context_ref.path ("../reports/fc.json") | validator rejects |
| S11 | Absolute path in failure_context_ref.path ("/abs/path") | validator rejects |
| S12 | Invalid sha256 (not 64-char hex) | validator rejects |
| S13 | triggered_by="initial_verify_pass" with repair_iteration=1 | validator rejects |
| S14 | triggered_by="post_repair_verify_pass" with repair_iteration=0 | validator rejects |
| S15 | review_iteration=0 (must be >= 1) | validator rejects |
| S16 | review_iteration=2 with repair_iteration=0 (must equal repair_iteration + 1) | validator rejects |
| S17 | review_iteration=3 with repair_iteration=1 (must equal repair_iteration + 1) | validator rejects |
| S18 | status="PASS" with recommended_action="repair" | validator rejects |
| S19 | status="PASS" with BLOCKER finding | validator rejects |
| S20 | status="FAIL" with no BLOCKER/MAJOR findings | validator rejects |
| S21 | status="FAIL" with recommended_action="none" | validator rejects |
| S22 | status="ERROR" with recommended_action="repair" | validator rejects |
| S23 | status="ERROR" with recommended_action="none" | validator rejects |
| S24 | Duplicate finding_id | validator rejects |
| S25 | Findings not ordered by finding_id | validator rejects |
| S26 | Too many truncated_fields (65 entries) | validator rejects |
| S27 | Invalid sanitization.redaction_count (negative) | validator rejects |
| S28 | Oversized reviewer_id (129 bytes) | validator rejects |
| S29 | Invalid run_id format (contains invalid chars) | validator rejects |
| S30 | Invalid generated_at format (not ISO-8601) | validator rejects |

### Referential validation tests (filesystem required) — 20 cases

| ID | Case | Expected |
|----|------|----------|
| R01 | Valid referential validation (all matches) | validator returns OK |
| R02 | Manifest file does not exist | validator rejects |
| R03 | Manifest SHA-256 mismatch | validator rejects |
| R04 | Manifest schema_version mismatch | validator rejects |
| R05 | Manifest excerpt title does not match manifest after sanitization | validator rejects |
| R06 | Manifest excerpt description does not match manifest after sanitization | validator rejects |
| R07 | Manifest excerpt acceptance_criteria does not match manifest | validator rejects |
| R08 | Manifest excerpt allowed_paths does not match manifest | validator rejects |
| R09 | Failure-context file does not exist | validator rejects |
| R10 | Failure-context SHA-256 mismatch | validator rejects |
| R11 | Failure-context schema_version mismatch | validator rejects |
| R12 | run_id mismatch between request and failure-context | validator rejects |
| R13 | story_id mismatch between request and failure-context | validator rejects |
| R14 | candidate_identity mismatch between request and failure-context | validator rejects |
| R15 | Failure-context overall_verification_status is not "PASS" | validator rejects |
| R16 | manifest_ref.path is absolute | validator rejects |
| R17 | failure_context_ref.path is absolute | validator rejects |
| R18 | manifest_ref.path contains traversal | validator rejects |
| R19 | failure_context_ref.path contains traversal | validator rejects |
| R20 | Path base confusion (manifest_ref.path treated as run_dir-relative) | validator rejects |

### Builder tests — 20 cases

| ID | Case | Expected |
|----|------|----------|
| B01 | Builder from valid failure-context + manifest | produces valid request |
| B02 | Builder computes manifest_ref.sha256 correctly | matches manual sha256sum |
| B03 | Builder computes failure_context_ref.sha256 correctly | matches manual sha256sum |
| B04 | Builder with missing manifest file | raises error |
| B05 | Builder with invalid manifest schema | raises error |
| B06 | Builder with missing failure-context file | raises error |
| B07 | Builder with invalid failure-context schema | raises error |
| B08 | Builder sanitizes manifest title (secret pattern) | redacted in output |
| B09 | Builder sanitizes manifest description (URL query) | query stripped |
| B10 | Builder sanitizes acceptance_criteria (control chars) | removed |
| B11 | Builder sanitizes repair_guidance (binary content) | "[REDACTED:binary_content]" |
| B12 | Builder truncates oversized title (300 bytes to 256 bytes) | truncated + marker + in truncated_fields |
| B13 | Builder with UTF-8 invalid bytes | replaced with U+FFFD |
| B14 | Builder populates sanitization metadata accurately | redaction_count, truncation_applied, truncated_fields correct |
| B15 | Builder with no sanitization needed | redaction_applied=false, redaction_count=0, truncation_applied=false, truncated_fields=[] |
| B16 | Builder deterministic output (same inputs twice) | identical canonical bytes |
| B17 | Builder canonical bytes (sort_keys=True, separators=(",", ":")) | matches expected format |
| B18 | Builder pretty JSON (indent=2, one terminal newline, no trailing whitespace) | matches expected format |
| B19 | Builder without explicit timestamp | raises error (no internal time call) |
| B20 | Builder validates its own output before publish | structural + referential validation pass |

### Serialization tests — 8 cases

| ID | Case | Expected |
|----|------|----------|
| C01 | Canonical bytes deterministic (same dict, different insertion order) | identical bytes |
| C02 | Canonical bytes use sort_keys=True | keys sorted alphabetically |
| C03 | Canonical bytes use compact separators | no spaces after : or , |
| C04 | Canonical bytes preserve UTF-8 | ensure_ascii=False |
| C05 | Pretty JSON has indent=2 | formatted with 2-space indent |
| C06 | Pretty JSON has exactly one terminal newline | ends with "\n" |
| C07 | Pretty JSON has no trailing whitespace on any line | all lines rstrip() |
| C08 | Pretty JSON uses sort_keys=True | keys sorted alphabetically |

### Sanitization tests — 16 cases

| ID | Case | Expected |
|----|------|----------|
| D01 | Redact stripe key pattern | "[REDACTED:stripe_key]" |
| D02 | Redact GitHub token pattern | "[REDACTED:github_token]" |
| D03 | Redact AWS key pattern | "[REDACTED:aws_key]" |
| D04 | Redact Bearer token | "[REDACTED:bearer_token]" |
| D05 | Redact Basic auth | "[REDACTED:basic_auth]" |
| D06 | Redact password assignment | "[REDACTED:password]" |
| D07 | Redact api_key assignment | "[REDACTED:api_key]" |
| D08 | Redact secret assignment | "[REDACTED:secret]" |
| D09 | Redact private key block | "[REDACTED:private_key]" |
| D10 | Strip URL query string | query removed, path preserved |
| D11 | Detect binary content | "[REDACTED:binary_content]" |
| D12 | Redact base64 run (100+ chars) | "[REDACTED:base64_payload]" |
| D13 | Remove control characters (preserve \n\t\r) | control chars removed |
| D14 | UTF-8 normalize invalid bytes | replaced with U+FFFD |
| D15 | Truncation marker format | "... [truncated: N bytes omitted]" |
| D16 | Redaction count accurate | matches number of substitutions |

### Integration / static checks — 3 cases

| ID | Case | Expected |
|----|------|----------|
| I01 | ruff check | 0 errors |
| I02 | mypy --strict | 0 errors |
| I03 | Harness scenarios A-T | 20/20 PASS (no regressions) |

### Test counts

- **94 planned unit-test cases** (S01-S30 + R01-R20 + B01-B20 + C01-C08 + D01-D16)
- **3 integration/static checks** (I01-I03)
- **20 A-T regression scenarios** (existing harness, must remain PASS)

These are planned cases, not guaranteed pytest item count. Actual pytest
collection may differ based on parametrization and fixture grouping.

## 17. Exact Scope

### Allowed paths

- `docs/planning/wp_al_1c1_review_contract.md` (this planning document)
- `.agent-loop/review/SCHEMA.md` (NEW — request + result schemas v1.0)
- `scripts/agent-loop/lib/review_contract.py` (NEW — validator + builder)
- `scripts/agent-loop/tests/test_review_contract.py` (NEW — 94 planned unit tests)
- `scripts/agent-loop/README.md` (status update)
- `docs/next_steps.md` (status update)

### Forbidden paths

- All WP-AL-1B3 deliverables (failure-context schema, collector, tests)
- `scripts/agent-loop/lib/failure_context.py` (read-only import)
- `scripts/agent-loop/run-story.sh` (no orchestrator changes)
- `scripts/agent-loop/verify-story.sh` (no verification changes)
- `scripts/agent-loop/report-story.sh` (no report changes, ERROR integration deferred)
- Gate implementations (`lib/{scope.sh,tests.sh,harness.py,manifest_loader.py,config_loader.py,guard.sh,passport.py}`)
- `.agent-loop/project.json`, `.agent-loop/gates.json`
- `.agent-loop/manifests/SCHEMA.md` (no manifest schema changes)
- `.agent-loop/failure-context/SCHEMA.md` (no failure-context schema changes)
- `backend/`, `frontend/`, `docker*`, `forgemind_project_source_of_truth/`
- Any LLM invocation, prompt design, or agent adapter code
- `.env`, `.env.*`, `*.pem`, `*.key`
- Any new sanitization module (use narrow public API from failure_context.py)

## 18. Implementation Stop Conditions

Stop and report if:

- Any file outside allowed paths is modified.
- Any test in the existing A-T harness suite fails.
- ruff or mypy strict reports errors on review_contract.py.
- A sanitizer signature in failure_context.py changes or is missing.
- Any secret, absolute path, or path traversal appears in output.
- report-story.sh is modified.
- failure_context.py is modified.
- Any LLM or network call is introduced.

## 19. Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-1 | Review-request schema v1.0 documented at `.agent-loop/review/SCHEMA.md` |
| AC-2 | Review-result schema v1.0 documented at `.agent-loop/review/SCHEMA.md` with PASS/FAIL/ERROR semantics |
| AC-3 | `validate_review_request(request)` — structural validation, no filesystem |
| AC-4 | `validate_review_result(result)` — structural validation, no filesystem |
| AC-5 | `validate_review_request_references(request, repo_root, run_dir)` — referential validation, two-root |
| AC-6 | Builder produces schema-valid request with structural + referential validation |
| AC-7 | Builder computes `manifest_ref.sha256` from exact manifest bytes |
| AC-8 | Builder computes `failure_context_ref.sha256` from exact failure-context bytes |
| AC-9 | Builder validates manifest file exists and schema before extraction |
| AC-10 | Builder validates failure-context file exists and schema before reference |
| AC-11 | Builder sanitizes all manifest excerpt fields |
| AC-12 | Builder populates sanitization metadata accurately |
| AC-13 | Validator rejects invalid fields, oversized strings, path traversal, bad iterations |
| AC-14 | Cross-field invariants enforced (triggered_by, iteration semantics, status+action) |
| AC-15 | Referential validation checks run_id/story_id/candidate_identity match |
| AC-16 | Referential validation checks manifest excerpt matches referenced manifest |
| AC-17 | Path-base rules enforced (manifest_ref relative to repo_root, failure_context_ref relative to run_dir) |
| AC-18 | Canonical JSON deterministic (sort_keys=True, separators=(",", ":"), ensure_ascii=False) |
| AC-19 | Pretty JSON has exactly one terminal newline, no trailing whitespace |
| AC-20 | No internal time calls; all timestamps supplied by caller |
| AC-21 | Sanitization imports narrow API from failure_context.py |
| AC-22 | No duplication of sanitization logic, no private function imports |
| AC-23 | Result status uses PASS/FAIL/ERROR (PASS/FAIL compatible with report-story.sh) |
| AC-24 | ERROR defined in schema but not integrated into report-story.sh |
| AC-25 | No raw secret values, no absolute paths, no path traversal in output |
| AC-26 | 94 planned unit-test cases covering all invariants |
| AC-27 | Existing harness scenarios A-T remain 20/20 PASS |
| AC-28 | ruff + mypy strict clean on review_contract.py |
| AC-29 | No LLM invocation, no network access, no shell interpolation |
| AC-30 | No modification to failure_context.py, run-story.sh, verify-story.sh, or report-story.sh |
| AC-31 | Planning document approved before implementation |

## 20. Resolved Decisions

- DEC-C1: status values PASS | FAIL | ERROR
- DEC-C2: failure_context_ref with path + sha256
- DEC-C3: triggered_by enum + repair_iteration
- DEC-C4: reviewer_id string
- ERROR semantics: defined but not integrated into report-story.sh
- Structural vs referential validation: 3 separate APIs
- Manifest reference: manifest_ref + manifest_excerpt
- Sanitization metadata: request-level and result-level
- Iteration semantics: review_iteration >= 1, review_iteration = repair_iteration + 1
- Canonical serialization: sort_keys=True, separators=(",", ":")
- Sanitization API: narrow public API from failure_context.py
- Report compatibility: PASS/FAIL compatible, ERROR deferred
- Two-root referential API: validate_review_request_references(request, repo_root, run_dir)
- No run_id derivation from manifest story_id
