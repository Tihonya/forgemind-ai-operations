# Failure Context Schema v1.0

## Purpose

Structured contract emitted by the agent-loop verification phase for downstream
consumers (reviewer, repair, reporter). Provides machine-readable, sanitized
failure evidence with deterministic candidate identity.

## Output Location

`$RUN_DIR/reports/failure-context.json`

## Schema Version

```json
{
  "schema_version": "1.0"
}
```

## Required Top-Level Fields

### Identity

- `run_id`: string (matches passport/run metadata)
- `story_id`: string
- `generated_at`: ISO-8601 timestamp (UTC)

### Candidate Identity

```json
{
  "base_commit": "40-char lowercase hex SHA",
  "candidate_commit": "40-char lowercase hex SHA | null",
  "candidate_state": "committed | working_tree",
  "candidate_diff_digest": "64-char lowercase hex SHA-256"
}
```

**Semantics:**

- `base_commit`: concrete SHA from manifest (never symbolic refs)
- `candidate_commit`:
  - concrete SHA when candidate is committed
  - `null` when verification targets working-tree changes only
- `candidate_state`:
  - `"committed"` when `candidate_commit` is non-null
  - `"working_tree"` when `candidate_commit` is null
- `candidate_diff_digest`: deterministic digest of candidate-diff file inventory
  (see Algorithm below)

**Digest Algorithm:**

1. Enumerate candidate-diff files via `list_candidate_diff_files(repo_root, base_commit)`
   producing a sorted list of repo-relative paths
2. For each path, record `(path, size_bytes, sha256_of_content)`:
   - tracked-and-committed files: content from HEAD
   - untracked files: content from working tree
3. Sort tuples lexicographically by `path`
4. Serialize as newline-delimited lines: `path\tsize\tsha256\n` (UTF-8, LF only)
5. Compute `sha256` over the serialized buffer
6. Result: 64-char lowercase hex digest

### Collection Metadata

```json
{
  "collection_status": "complete | partial | failed",
  "collection_errors": [...]
}
```

**Semantics:**

- `complete`: all source artifacts present and valid
- `partial`: some artifacts missing/malformed but schema-valid output produced
- `failed`: collector could not produce schema-valid output (INFRASTRUCTURE_ERROR, exit 2)
- `collection_errors`: bounded array of structured entries (see §Collection Errors)

### Verification Result

```json
{
  "overall_verification_status": "PASS | FAIL | ERROR | SKIP",
  "gate_verdicts": {
    "<gate_id>": {
      "status": "PASS | FAIL | SKIP | ERROR | DISABLED",
      "summary": "bounded sanitized string",
      "source_artifacts": ["relative/path/to/artifact"],
      "diagnostics": [...]
    }
  },
  "failing_gate_ids": ["gate_id_1", "gate_id_2"]
}
```

**Canonical Gate IDs:**

- `scope`
- `json_syntax`
- `yaml_syntax`
- `targeted_tests`
- `lint`
- `secrets`
- `git_diff_check`

### Diagnostics

```json
{
  "diagnostics": [
    {
      "category": "gate_log | test_output | lint_output | secrets_evidence | ...",
      "severity": "info | warning | error",
      "source_artifact": "relative/path",
      "content": "sanitized bounded excerpt",
      "redaction_applied": true,
      "redaction_count": 5,
      "truncated": true,
      "original_size_bytes": 10000,
      "included_size_bytes": 4096
    }
  ]
}
```

**Rules:**

- Structured diagnostics first; excerpts only after sanitization
- All text UTF-8 normalized (invalid bytes → U+FFFD)
- Bounded by configurable limits (defaults: 50 lines, 4096 bytes per excerpt)
- Truncation marker: `... [truncated: N bytes omitted, source: <path>]`
- No absolute paths
- No raw secret values (see §Sanitization)

### Sanitization Policy

**Mandatory redaction (applied before any field is written):**

1. No raw secret values. Secrets-gate evidence limited to:
   - `rule_id`
   - `relative_file_path`
   - `line_number`
   - `classification` / `status`
2. No environment dumps
3. No command-line arguments containing credentials
4. No raw `Authorization` headers or cookie values
5. No full URLs with query strings (strip query string)
6. No arbitrary binary or base64 content
7. All text UTF-8 normalized; invalid bytes → U+FFFD
8. Excerpts bounded by line/byte limits
9. Each diagnostic carries `redaction_applied` and `redaction_count`

**Redaction classes:**

- Common token/password/api-key assignments
- Bearer/Basic authorization values
- URL query strings
- Private-key blocks
- Control characters unsafe for JSON/log display

### Repair Guidance

```json
{
  "repair_guidance": ["pass-through from manifest"]
}
```

### Artifact References

```json
{
  "artifact_refs": {
    "verify_result": "reports/verify-result.json",
    "gate_logs": [
      "verify/scope.log",
      "verify/tests.log",
      ...
    ]
  }
}
```

### Limits Metadata

```json
{
  "limits": {
    "max_excerpt_lines": 50,
    "max_excerpt_bytes": 4096,
    "max_diagnostics_per_gate": 10,
    "max_total_diagnostics": 50
  }
}
```

### Redaction Metadata

```json
{
  "redaction_applied": true,
  "redaction_count": 42
}
```

Top-level aggregate of all redactions applied across diagnostics.

## Collection Errors

```json
{
  "collection_errors": [
    {
      "artifact_id": "verify/pytest-report.xml",
      "error_code": "MISSING | MALFORMED | UNREADABLE",
      "safe_summary": "bounded description without sensitive data"
    }
  ]
}
```

**Rules:**

- Bounded array (max 20 entries)
- Deterministic ordering (by `artifact_id`)
- No raw exception messages (may contain paths/secrets)
- `safe_summary`: human-readable but sanitized

## Collector Failure Semantics

- Collector failure → overall run becomes `INFRASTRUCTURE_ERROR`, exit code 2
- Existing gate evidence in `verify-result.json` and per-gate logs preserved
- Collector failure never reported as `VERIFICATION_FAILED` or `REVIEW_REJECTED`
- Emit minimal safe infrastructure-error artifact via existing `atomic_write` mechanism
- No recursive collector invocation

## Example: Successful Verification

```json
{
  "schema_version": "1.0",
  "run_id": "US-002_20260804_120000_123456789_7890",
  "story_id": "US-002",
  "generated_at": "2026-08-04T12:05:30.123456Z",
  "candidate_identity": {
    "base_commit": "10b0e1bf8a0ba4ced62cec585cb291f3b4c9697b",
    "candidate_commit": "63507773b673676eb1033a9b4bb501dfbc773764",
    "candidate_state": "committed",
    "candidate_diff_digest": "a1b2c3d4e5f6..."
  },
  "collection_status": "complete",
  "collection_errors": [],
  "overall_verification_status": "PASS",
  "gate_verdicts": {
    "scope": {
      "status": "PASS",
      "summary": "",
      "source_artifacts": ["verify/scope.log"],
      "diagnostics": []
    },
    "targeted_tests": {
      "status": "PASS",
      "summary": "12 tests passed",
      "source_artifacts": ["verify/tests.log", "verify/pytest-report.xml"],
      "diagnostics": []
    }
  },
  "failing_gate_ids": [],
  "repair_guidance": [],
  "artifact_refs": {
    "verify_result": "reports/verify-result.json",
    "gate_logs": ["verify/scope.log", "verify/tests.log", ...]
  },
  "limits": {
    "max_excerpt_lines": 50,
    "max_excerpt_bytes": 4096,
    "max_diagnostics_per_gate": 10,
    "max_total_diagnostics": 50
  },
  "redaction_applied": false,
  "redaction_count": 0
}
```

## Example: Failed Verification

```json
{
  "schema_version": "1.0",
  "run_id": "US-003_20260804_130000_987654321_1234",
  "story_id": "US-003",
  "generated_at": "2026-08-04T13:05:45.654321Z",
  "candidate_identity": {
    "base_commit": "10b0e1bf8a0ba4ced62cec585cb291f3b4c9697b",
    "candidate_commit": null,
    "candidate_state": "working_tree",
    "candidate_diff_digest": "f6e5d4c3b2a1..."
  },
  "collection_status": "complete",
  "collection_errors": [],
  "overall_verification_status": "FAIL",
  "gate_verdicts": {
    "targeted_tests": {
      "status": "FAIL",
      "summary": "3 tests failed, 9 passed",
      "source_artifacts": ["verify/tests.log", "verify/pytest-report.xml"],
      "diagnostics": [
        {
          "category": "test_output",
          "severity": "error",
          "source_artifact": "verify/tests.log",
          "content": "FAILED test_foo.py::test_bar\nAssertionError: expected 42 got 43\n... [truncated: 2048 bytes omitted, source: verify/tests.log]",
          "redaction_applied": false,
          "redaction_count": 0,
          "truncated": true,
          "original_size_bytes": 8192,
          "included_size_bytes": 4096
        }
      ]
    }
  },
  "failing_gate_ids": ["targeted_tests"],
  "repair_guidance": ["fix the failing assertion"],
  "artifact_refs": {
    "verify_result": "reports/verify-result.json",
    "gate_logs": ["verify/scope.log", "verify/tests.log", ...]
  },
  "limits": {...},
  "redaction_applied": false,
  "redaction_count": 0
}
```

## Determinism Guarantees

- `candidate_diff_digest` is deterministic (same input → same digest)
- Gate verdicts ordered by canonical gate ID (lexicographic)
- `failing_gate_ids` ordered lexicographically
- `collection_errors` ordered by `artifact_id`
- Stable JSON formatting (indent=2, sort_keys=False — preserve insertion order)

## Relationship to Manifest Schema

- This schema is **separate** from `.agent-loop/manifests/SCHEMA.md` (story manifest)
- Manifest schema v1.0 field table and semantics are **unchanged**
- At most a short cross-reference may be added to manifest SCHEMA.md

## Non-Goals

- No LLM invocation
- No reviewer/repair agent logic
- No run lifecycle / state machine
- No concurrency support
- No prompt design
