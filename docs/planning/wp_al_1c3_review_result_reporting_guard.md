# WP-AL-1C3 — Review-Result Reporting Guard

**Status:** IMPLEMENTATION COMPLETE — AWAITING REVIEW
**Work Package:** WP-AL-1C3
**Priority:** High
**Depends on:** WP-AL-1C1, WP-AL-1C2
**Precedes:** review invocation bridge (future), WP-AL-1C4 (Repair Contract)
**Estimated Effort:** 1–2 days

---

## 1. Motivation

`report-story.sh` consumes `$RUN_DIR/reports/review-result.json` to determine
the final status of a run. Its current decision tree handles two branches:

```python
if report["verification"]:
    verify_status = report["verification"].get("overall_status", "UNKNOWN")
    if verify_status == "PASS":
        if report.get("review") and report["review"].get("status") == "PASS":
            report["final_status"] = "ACCEPTED"
        elif report.get("review") and report["review"].get("status") == "FAIL":
            report["final_status"] = "REVIEW_REJECTED"
        else:
            report["final_status"] = "VERIFIED"   # <-- defect
    ...
```

This produces three silent fall-through paths to `VERIFIED` that violate
`.agent-loop/review/SCHEMA.md`:

1. A review result with `status == "ERROR"` → `VERIFIED`
   (schema explicitly forbids this: "ERROR must never be treated as PASS or
   VERIFIED").
2. A review result with an unknown status value → `VERIFIED`.
3. A malformed JSON review-result file → `json.load` raises, the `except`
   block silently passes, `report["review"]` remains `None`, and the same
   `else` branch assigns `VERIFIED`.

Although the adapter is not yet wired into `run-story.sh` and review is not
yet executed as a lifecycle phase, the reporting guard must be closed
**before** the review invocation bridge is implemented. Leaving the defect
open while adding invocation would widen the blast radius: a single ERROR
review could produce a final report claiming ACCEPTED or VERIFIED.

This work package closes the defect at the aggregation boundary without
changing the review lifecycle, the review contract, the adapter, the mock
reviewer, or the schemas.

---

## 2. Product Owner Decisions (Recorded as Approved)

1. **WP-AL-1C3** is the review-result reporting guard.
2. The previously proposed Repair Contract is renumbered to **WP-AL-1C4**
   and is **not** in scope for this work package.
3. **Final-status mapping for review results:**

   | Review state                                                       | `final_status`          |
   |--------------------------------------------------------------------|--------------------------|
   | Valid, `status == "PASS"`                                          | `ACCEPTED`               |
   | Valid, `status == "FAIL"`                                          | `REVIEW_REJECTED`        |
   | Valid, `status == "ERROR"` + `recommended_action == "human_review"`| `HUMAN_REVIEW_REQUIRED`  |
   | Valid, `status == "ERROR"` + any other/missing action              | `INFRASTRUCTURE_ERROR`   |
   | Malformed JSON                                                     | `INFRASTRUCTURE_ERROR`   |
   | Valid JSON, schema-invalid                                         | `INFRASTRUCTURE_ERROR`   |
   | Valid JSON, missing or wrong-typed `status`                        | `INFRASTRUCTURE_ERROR`   |
   | Valid JSON, unknown `status` value                                 | `INFRASTRUCTURE_ERROR`   |
   | Unreadable file (type error, permissions)                          | `INFRASTRUCTURE_ERROR`   |
   | File absent                                                        | `VERIFIED`               |

   Under this WP, only complete file absence represents optional review.
   No existing review-result file may silently yield `VERIFIED` unless it
   is structurally and semantically an explicitly supported no-review
   condition.

4. **Missing `review-result.json`** continues to map to `VERIFIED` for
   this WP because review is still optional and is not yet wired into
   `run-story.sh`. This behavior must be revisited when the review
   invocation bridge is implemented (a later WP).

---

## 3. Scope Boundary

### 3.1 In scope

- Safe loading and classification of `$RUN_DIR/reports/review-result.json`.
- Distinction between **absent**, **valid-PASS**, **valid-FAIL**,
  **valid-ERROR-human-review**, **valid-ERROR-other**, and **invalid**.
- Explicit handling of malformed JSON, schema-invalid content, wrong
  types, unknown status values, and unreadable files.
- Final-status mapping consistent with the table in §2.
- A narrow typed Python helper under `scripts/agent-loop/lib/` that
  reuses the existing `validate_review_result()` API.
- Deterministic unit and integration tests for the helper.
- Integration with `report-story.sh` via CLI invocation of the helper.
- Harness scenarios **W** and **X**.
- README and `next_steps.md` status updates.

### 3.2 Out of scope

- Invoking the reviewer adapter from `run-story.sh` (review bridge).
- Reviewer configuration or command rendering.
- Repair contract or repair execution (WP-AL-1C4).
- Real LLM or provider integration.
- Changes to the review-request or review-result schemas.
- Changes to `review_adapter.py` or `mock_reviewer.py`.
- Changes to `review_contract.py` (the validator is consumed, not modified).
- Changes to `verify-story.sh` or the verification gates.
- Changes to `run-story.sh` lifecycle orchestration.
- Precedence rework for verification-failure or infrastructure-error paths.

---

## 4. Status Mapping

### 4.1 Precedence preserved

The existing aggregation precedence remains unchanged. WP-AL-1C3 only
refines the branch executed when `verification.overall_status == "PASS"`.

Current precedence order:

1. **Verification infrastructure error** (no `verification` object, `error`
   key present): `INFRASTRUCTURE_ERROR`.
2. **Verification fail + repair iterations > 0**: `REPAIR_EXHAUSTED`.
3. **Verification fail + repair iterations == 0**: `VERIFICATION_FAILED`.
4. **Verification pass**: review branch (refined by this WP).

### 4.2 Review-branch decision table (after WP-AL-1C3)

When `verification.overall_status == "PASS"`:

| Review artifact state       | `final_status`          |
|-----------------------------|--------------------------|
| ABSENT (file does not exist)| `VERIFIED`               |
| PASS                        | `ACCEPTED`               |
| FAIL                        | `REVIEW_REJECTED`        |
| ERROR_HUMAN_REVIEW          | `HUMAN_REVIEW_REQUIRED`  |
| ERROR_OTHER                 | `INFRASTRUCTURE_ERROR`   |
| INVALID                     | `INFRASTRUCTURE_ERROR`   |

### 4.3 Coverage of all aggregation states

The full decision table (verification present/absent × review state × error
flag) after WP-AL-1C3:

| verification present | verification status  | review state         | error key | `final_status`          |
|----------------------|----------------------|----------------------|-----------|--------------------------|
| yes                  | PASS                 | ABSENT               | —         | `VERIFIED`               |
| yes                  | PASS                 | PASS                 | —         | `ACCEPTED`               |
| yes                  | PASS                 | FAIL                 | —         | `REVIEW_REJECTED`        |
| yes                  | PASS                 | ERROR_HUMAN_REVIEW   | —         | `HUMAN_REVIEW_REQUIRED`  |
| yes                  | PASS                 | ERROR_OTHER          | —         | `INFRASTRUCTURE_ERROR`   |
| yes                  | PASS                 | INVALID              | —         | `INFRASTRUCTURE_ERROR`   |
| yes                  | not PASS             | any / absent         | —         | `REPAIR_EXHAUSTED` or    |
|                      |                      |                      |           | `VERIFICATION_FAILED`    |
| no                   | —                    | —                    | present   | `INFRASTRUCTURE_ERROR`   |
| no                   | —                    | —                    | absent    | `UNKNOWN` (default)      |

The last row is the pre-existing default from `report-story.sh` when
neither verification nor error information is available. WP-AL-1C3 does not
modify this case.

`ERROR_HUMAN_REVIEW` is the state in which `status == "ERROR"` AND
`recommended_action == "human_review"` are both valid according to
`validate_review_result()`. `ERROR_OTHER` is any other ERROR that is still
schema-valid (defensive; current schema requires `human_review` for ERROR).

### 4.4 Invariants

- `VERIFIED` is produced **only** when the review-result file is absent.
- `ACCEPTED` is produced **only** when the review-result file is present,
  schema-valid, and `status == "PASS"`.
- `REVIEW_REJECTED` is produced **only** when the review-result file is
  present, schema-valid, and `status == "FAIL"`.
- `HUMAN_REVIEW_REQUIRED` is produced **only** when the review-result file
  is present, schema-valid, `status == "ERROR"`, and
  `recommended_action == "human_review"`.
- `INFRASTRUCTURE_ERROR` is produced for every other review-state: ERROR
  without `human_review`, malformed JSON, schema-invalid content, unknown
  status, unreadable file, wrong type.

---

## 5. Validation Approach

### 5.1 Architecture

A narrow Python helper module:

```
scripts/agent-loop/lib/review_result_reporting.py
```

Responsibilities:

- Read the optional path.
- Distinguish **ABSENT** from **INVALID** from **valid**.
- Parse JSON safely.
- Call the existing `validate_review_result()` API from `review_contract.py`
  for schema validation.
- Classify the result into one of six categories.
- Map the category to a final_status string.
- Return bounded, sanitized diagnostics.

`report-story.sh` remains aggregation glue. It invokes the helper via CLI
and consumes the JSON classification. Bash does **not** duplicate any
schema rule. `review_contract.py` is consumed, not modified.

### 5.2 Proposed API

```python
from dataclasses import dataclass
from pathlib import Path

REVIEW_CATEGORY_ABSENT              = "ABSENT"
REVIEW_CATEGORY_PASS                = "PASS"
REVIEW_CATEGORY_FAIL                = "FAIL"
REVIEW_CATEGORY_ERROR_HUMAN_REVIEW  = "ERROR_HUMAN_REVIEW"
REVIEW_CATEGORY_ERROR_OTHER         = "ERROR_OTHER"
REVIEW_CATEGORY_INVALID             = "INVALID"

@dataclass(frozen=True)
class ReviewClassification:
    category: str                    # one of the six REVIEW_CATEGORY_* constants
    final_status: str                # one of the mapped final_status values
    status_value: str | None         # raw status field if readable, else None
    recommended_action: str | None   # raw recommended_action if readable, else None
    detail: str                      # bounded sanitized detail; empty on success

def classify_review_result(path: Path | None) -> ReviewClassification:
    """Classify an optional review-result file for final-report aggregation.

    - If path is None or the file does not exist: ABSENT.
    - If the file cannot be read (permissions, wrong type): INVALID.
    - If JSON parsing fails: INVALID.
    - If validate_review_result() raises: INVALID.
    - If status == "PASS": PASS.
    - If status == "FAIL": FAIL.
    - If status == "ERROR" and recommended_action == "human_review": ERROR_HUMAN_REVIEW.
    - If status == "ERROR" with any other action: ERROR_OTHER.
    - Otherwise (unknown status): INVALID.
    """
```

### 5.3 CLI behavior

```bash
python3 scripts/agent-loop/lib/review_result_reporting.py \
    classify [--path <file>]

# stdout: JSON object with keys category, final_status, status_value,
#         recommended_action, detail
# exit 0 always — classification is the output, not a success signal
```

If `--path` is omitted, the helper treats the file as absent. If the path
is provided but the file does not exist, ABSENT. If the path is provided
but unreadable, INVALID with sanitized detail.

### 5.4 Diagnostic bounds

- `detail` is capped at 1024 bytes after sanitization.
- `redact_text()` from `failure_context.py` is applied before any content
  reaches `detail` (narrow, approved import).
- `detail` never contains absolute filesystem paths, raw malformed JSON,
  secrets, or untrusted payloads.
- On `INVALID`, `detail` contains a short human-readable reason
  (e.g. `"JSON parse failed"`, `"schema validation failed: missing status"`,
  `"unreadable file"`) — not the underlying exception message.

### 5.5 Integration in report-story.sh

The report-story.sh Python heredoc will replace the existing
`review-result.json` handling with:

```python
from review_result_reporting import classify_review_result

review_path = reports_dir / "review-result.json"
classification = classify_review_result(review_path if review_path.exists() else None)

report["review_classification"] = classification.category
if classification.category != "ABSENT":
    report["review"] = {
        "status": classification.status_value,
        "recommended_action": classification.recommended_action,
        "classification": classification.category,
    }
    if classification.detail:
        report["review"]["detail"] = classification.detail
```

Final-status resolution will then branch on `classification.final_status`
inside the `verify_status == "PASS"` block, replacing the current three-way
`if / elif / else` with an explicit dispatch over the six categories.

The existing `report["review"]` field is preserved for backward
compatibility where it was populated; new consumers should prefer
`review_classification`.

---

## 6. Probable File Scope

### 6.1 New files

| File                                                          | Purpose                                              |
|---------------------------------------------------------------|------------------------------------------------------|
| `scripts/agent-loop/lib/review_result_reporting.py`           | Narrow classification helper + CLI.                  |
| `scripts/agent-loop/tests/test_review_result_reporting.py`    | Unit and integration tests for the helper.           |

### 6.2 Modified files

| File                                                          | Purpose                                              |
|---------------------------------------------------------------|------------------------------------------------------|
| `scripts/agent-loop/report-story.sh`                          | Replace inline review handling with helper call.     |
| `scripts/agent-loop/tests/run_harness_scenarios.sh`           | Add scenarios W and X.                               |
| `scripts/agent-loop/README.md`                                | Status update.                                       |
| `docs/next_steps.md`                                          | Mark WP-AL-1C3 complete; renumber Repair Contract.   |
| `docs/planning/wp_al_1c3_review_result_reporting_guard.md`    | This document (updated to completion status).        |

### 6.3 Justification for each change

- **`review_result_reporting.py`**: new module because the classification
  logic is a distinct concern from `review_contract.py` (which is pure
  schema validation) and from `review_adapter.py` (which invokes the
  reviewer subprocess). The helper sits between the adapter's published
  artifact and the final report.
- **`test_review_result_reporting.py`**: new test module because the
  helper has its own classification contract, distinct from both the
  review-contract validator tests and the adapter tests.
- **`report-story.sh`**: only the review-branch aggregation is touched;
  verification/repair/infrastructure-error branches are unchanged.
- **`run_harness_scenarios.sh`**: adds W and X to the 22-scenario
  sequence; final count becomes 24 (A through X).
- **`README.md`**: status update documenting the new capability.
- **`docs/next_steps.md`**: records WP-AL-1C3 as complete, renumbers the
  Repair Contract proposal to WP-AL-1C4.

---

## 7. Forbidden Implementation Paths

The following files and paths must **not** be modified by this work package:

- `scripts/agent-loop/run-story.sh`
- `scripts/agent-loop/verify-story.sh`
- `scripts/agent-loop/lib/review_adapter.py`
- `scripts/agent-loop/lib/mock_reviewer.py`
- `scripts/agent-loop/lib/review_contract.py`
- `scripts/agent-loop/lib/failure_context.py` (consumed via narrow import only)
- `.agent-loop/review/SCHEMA.md`
- `.agent-loop/review-adapter/SCHEMA.md`
- `.agent-loop/manifests/SCHEMA.md`
- `.agent-loop/failure-context/SCHEMA.md`
- `.agent-loop/gates.json`
- `.agent-loop/project.json`
- `backend/**`
- `frontend/**`
- `docker/**`
- `forgemind_project_source_of_truth/**`
- `.env`, `.env.*`, `*.pem`, `*.key`
- Gate implementations in `lib/{scope.sh,tests.sh,harness.py,
  manifest_loader.py,config_loader.py,guard.sh,passport.py}`

Any modification to a forbidden path is a scope violation and a stop
condition.

---

## 8. Precedence Rules

The final-status resolution in `report-story.sh` after WP-AL-1C3 follows
this decision ordering. The review branch is refined; every other branch
is unchanged.

```
1. if report.verification is absent AND report.error is set:
       INFRASTRUCTURE_ERROR

2. elif report.verification.overall_status == "PASS":
       review_classification = classify(path)
       switch review_classification.final_status:
           "VERIFIED"                → VERIFIED                (review absent)
           "ACCEPTED"                → ACCEPTED                (review PASS)
           "REVIEW_REJECTED"         → REVIEW_REJECTED         (review FAIL)
           "HUMAN_REVIEW_REQUIRED"   → HUMAN_REVIEW_REQUIRED   (review ERROR+human_review)
           "INFRASTRUCTURE_ERROR"    → INFRASTRUCTURE_ERROR    (review ERROR-other or INVALID)

3. elif report.verification.overall_status != "PASS":
       if report.repair.iterations > 0:
           REPAIR_EXHAUSTED
       else:
           VERIFICATION_FAILED
```

No existing precedence is inverted. The verification-failure and
infrastructure-error branches are untouched.

---

## 9. Artifact Handling

- **`review-result.json`** is read-only. The helper never writes, moves,
  deletes, or replaces it.
- No source artifact under `$RUN_DIR/` is deleted or mutated by this WP.
- No replacement review-result file is created.
- **`final-report.json`** continues to be emitted atomically via the
  existing `atomic_json_write` mechanism; no change to its write path.
- Diagnostics inside `final-report.json` and `review.detail` are bounded,
  sanitized, and contain no absolute paths, no raw malformed JSON, no
  secrets, no untrusted payloads.
- The existing `report["review"]` field retains its shape for PASS/FAIL
  cases (backward compatibility); new cases populate
  `report["review_classification"]` plus a minimal `report["review"]`
  envelope containing `status`, `recommended_action`, `classification`,
  and optional `detail`.

---

## 10. Proposed Tests

### 10.1 Unit tests: `scripts/agent-loop/tests/test_review_result_reporting.py`

Meaningful planned IDs with distinct ownership:

| ID  | Case                                                           | Expected category            | Expected `final_status`       |
|-----|----------------------------------------------------------------|------------------------------|-------------------------------|
| U01 | File path is `None`                                            | `ABSENT`                     | `VERIFIED`                    |
| U02 | File does not exist                                            | `ABSENT`                     | `VERIFIED`                    |
| U03 | Valid schema-valid `status == "PASS"`                          | `PASS`                       | `ACCEPTED`                    |
| U04 | Valid schema-valid `status == "FAIL"`                          | `FAIL`                       | `REVIEW_REJECTED`             |
| U05 | Valid ERROR + `recommended_action == "human_review"`           | `ERROR_HUMAN_REVIEW`         | `HUMAN_REVIEW_REQUIRED`       |
| U06 | Valid ERROR + `recommended_action == "none"`                   | `ERROR_OTHER`                | `INFRASTRUCTURE_ERROR`        |
| U07 | Valid ERROR + `recommended_action == "repair"`                 | `ERROR_OTHER`                | `INFRASTRUCTURE_ERROR`        |
| U08 | Valid ERROR + missing `recommended_action`                     | `ERROR_OTHER`                | `INFRASTRUCTURE_ERROR`        |
| U09 | Malformed JSON (e.g. `{ invalid }`)                            | `INVALID`                    | `INFRASTRUCTURE_ERROR`        |
| U10 | Valid JSON but schema-invalid (missing required field)         | `INVALID`                    | `INFRASTRUCTURE_ERROR`        |
| U11 | Missing `status` field                                         | `INVALID`                    | `INFRASTRUCTURE_ERROR`        |
| U12 | `status` is wrong type (integer instead of string)             | `INVALID`                    | `INFRASTRUCTURE_ERROR`        |
| U13 | Unknown `status` value (e.g. `"ACCEPT"`)                       | `INVALID`                    | `INFRASTRUCTURE_ERROR`        |
| U14 | Unreadable path (e.g. FIFO / directory / permissions error)    | `INVALID`                    | `INFRASTRUCTURE_ERROR`        |
| U15 | Existing `error` key present + review absent                   | helper returns `ABSENT`      | report: `INFRASTRUCTURE_ERROR`|
| U16 | Verification fail + review present (any category)              | helper invoked only if verify PASS; otherwise precedence unchanged | `VERIFICATION_FAILED` / `REPAIR_EXHAUSTED` |
| U17 | Deterministic: classify same input twice → identical output    | identical                    | identical                     |
| U18 | `detail` never contains raw malformed JSON                     | —                            | —                             |
| U19 | `detail` never contains absolute filesystem paths              | —                            | —                             |
| U20 | `detail` never contains secret patterns                        | —                            | —                             |

U15–U16 exercise precedence at the `report-story.sh` level; the helper
remains pure.

### 10.2 Harness scenarios

Added to `scripts/agent-loop/tests/run_harness_scenarios.sh`:

- **Scenario W**: valid mock-reviewer ERROR result + `recommended_action == "human_review"`
  → `final_status == "HUMAN_REVIEW_REQUIRED"`.
  - Uses `mock_reviewer.py --mode ERROR`.
  - Adapter publishes schema-valid `review-result.json` via existing
    WP-AL-1C2 path (already produces `recommended_action == "human_review"`
    for ERROR).
  - Assert `final-report.json` has `final_status == "HUMAN_REVIEW_REQUIRED"`.

- **Scenario X**: malformed `review-result.json` in place
  → `final_status == "INFRASTRUCTURE_ERROR"`.
  - Writes `{ invalid json }` to `$RUN_DIR/reports/review-result.json`
    directly (bypassing adapter; tests the reporting guard, not the
    adapter).
  - Assert `final-report.json` has `final_status == "INFRASTRUCTURE_ERROR"`.

Existing scenarios **A–V** remain unchanged and must all pass.

Final expected harness range: **A through X = 24 scenarios, 24/24 PASS**.

---

## 11. Acceptance Criteria

| ID    | Criterion                                                                                               |
|-------|---------------------------------------------------------------------------------------------------------|
| AC-01 | A review result with `status == "ERROR"` never produces `final_status == "VERIFIED"` or `"ACCEPTED"`.   |
| AC-02 | A review result with an unknown status value never produces `final_status == "VERIFIED"`.                |
| AC-03 | A malformed JSON review-result file never produces `final_status == "VERIFIED"`.                         |
| AC-04 | A schema-invalid review-result file never produces `final_status == "VERIFIED"`.                         |
| AC-05 | An unreadable review-result file never produces `final_status == "VERIFIED"`.                            |
| AC-06 | A review result with `status == "ERROR"` and `recommended_action == "human_review"` produces            |
|       | `final_status == "HUMAN_REVIEW_REQUIRED"`.                                                              |
| AC-07 | A review result with `status == "ERROR"` and any other/missing `recommended_action` produces            |
|       | `final_status == "INFRASTRUCTURE_ERROR"`.                                                               |
| AC-08 | Absence of `review-result.json` produces `final_status == "VERIFIED"` (unchanged optional review).      |
| AC-09 | Valid `status == "PASS"` produces `final_status == "ACCEPTED"` (unchanged).                             |
| AC-10 | Valid `status == "FAIL"` produces `final_status == "REVIEW_REJECTED"` (unchanged).                      |
| AC-11 | Verification-failure and repair-exhausted precedence are unchanged.                                     |
| AC-12 | Infrastructure-error precedence is unchanged.                                                           |
| AC-13 | No review schema rule is duplicated in Bash or `jq`. Validation reuses `validate_review_result()`.      |
| AC-14 | The helper's `detail` field is bounded (≤1024 bytes), sanitized via `redact_text()`, and contains no    |
|       | absolute paths, raw malformed JSON, or secrets.                                                         |
| AC-15 | Harness scenarios A–X (24 scenarios) pass 24/24.                                                        |
| AC-16 | Existing pytest regression (`test_review_contract.py`, `test_review_adapter.py`, `test_mock_reviewer.py`)|
|       | remains green.                                                                                          |
| AC-17 | `ruff check` clean for new/modified Python files.                                                       |
| AC-18 | `mypy --strict` clean for new/modified Python files.                                                    |
| AC-19 | `shellcheck` / compile-clean for `report-story.sh`.                                                     |
| AC-20 | `detect-secrets` scan clean on the diff.                                                                |
| AC-21 | No forbidden path is modified (see §7).                                                                 |
| AC-22 | The `review-result.json` source artifact is never written, moved, or deleted by the helper.             |
| AC-23 | Classification is deterministic: identical input produces identical `ReviewClassification` on repeated  |
|       | execution.                                                                                              |
| AC-24 | `docs/next_steps.md` reflects WP-AL-1C3 complete and the Repair Contract renumbered to WP-AL-1C4.       |

---

## 12. Definition of Done

- Branch created from `origin/main` @ `b9f6a0ee638b6732cb41989ff9d7bb5cc4e9a183`.
- Implementation confined to the probable file scope in §6.
- All AC-01 through AC-24 pass with evidence (test output, harness output,
  lint/mypy output, `git diff --name-status` confirming no forbidden
  modifications).
- README and `next_steps.md` updated to reflect the new state.
- Planning document updated to `IMPLEMENTATION COMPLETE — AWAITING REVIEW`.
- Independent review artifacts produced (not by this WP).
- Product Owner review and merge approval.

---

## 13. Stop Conditions

Stop and report without further action if:

- Any regression in harness scenarios A–V.
- Any regression in `test_review_contract.py`, `test_review_adapter.py`,
  or `test_mock_reviewer.py`.
- Any modification to a forbidden path (§7).
- Any secret value or absolute filesystem path appearing in a test
  fixture, diagnostic, or `final-report.json`.
- `validate_review_result()` is modified rather than consumed.
- A malformed review result can still produce `final_status == "VERIFIED"`.
- The precedence of verification-failure or infrastructure-error branches
  is altered.
- `run-story.sh` is modified.
- The scope expands into review invocation, reviewer configuration, or
  repair (WP-AL-1C4).

---

## 14. Known Limitations

- The reviewer adapter is still **not** invoked from `run-story.sh`. The
  review lifecycle bridge is a separate future WP.
- Absence of `review-result.json` remains mapped to `VERIFIED`. This
  behavior is correct only while review is optional; it must be revisited
  by the review invocation bridge.
- The verification-failure branch's handling of `overall_status == "ERROR"`
  is a pre-existing concern outside the scope of this WP. It is not
  modified here.
- The repair contract is deferred to **WP-AL-1C4** and is not
  implemented, designed, or speculatively scaffolded in this WP.
- Real LLM / provider integration is deferred indefinitely and is not
  addressed by this WP.

---

## 15. Follow-up Sequencing

Proposed sequence after this WP:

1. **WP-AL-1C3 (this WP)** — review-result reporting guard.
2. **Review invocation / configuration bridge** — wires the adapter into
   `run-story.sh`, provides reviewer-command configuration from
   `project.json` or the manifest, and (necessarily) revisits the
   "absent → VERIFIED" behavior from §2.4, because once review is an
   executed lifecycle phase, absence is no longer "optional review" but
   "review phase did not produce a result."
3. **WP-AL-1C4 — Repair Contract** — defines the repair-request and
   repair-result schemas with structural validators. Renumbered from the
   previously-proposed WP-AL-1C3. Subject to later PO confirmation of
   timing and scope.

The repair contract does **not** depend on the reporting guard or the
review bridge — it is a pure schema WP analogous to WP-AL-1C1 — but
logically it belongs after the review lifecycle is fully closed, so that
the repair loop has a stable consumer for its input.

---

## 16. Branch Strategy

- Base: `origin/main` @ `b9f6a0ee638b6732cb41989ff9d7bb5cc4e9a183`.
- Branch name: `feature/agent-loop-reporting-guard` (or
  `chore/agent-loop-reporting-guard`, PO preference).
- One PR against `main`.
- Merge commit strategy (not squash) to preserve the WP structure.

---

## 17. Commit / PR Strategy

Conventional commits, one logical change per commit:

1. `docs(agent-loop): define WP-AL-1C3 review-result reporting guard`
   (this planning document).
2. `feat(agent-loop): add review-result classification helper`
   (`review_result_reporting.py`, unit tests).
3. `feat(agent-loop): wire reporting guard into report-story.sh`
   (`report-story.sh`, scenario W/X in harness).
4. `docs(agent-loop): record WP-AL-1C3 completion; renumber Repair`
   `Contract to WP-AL-1C4` (`README.md`, `next_steps.md`, this doc).

PR description references this planning document and lists AC-01…AC-24.

---

## 18. Dependencies and Environment

- Python 3.11+ (per repository baseline).
- pytest 9.0+
- ruff 0.8+
- mypy 1.14+
- Narrow import from `failure_context.py` (`redact_text`) — approved
  pattern from WP-AL-1C1.
- Narrow import from `review_contract.py` (`validate_review_result`,
  `ReviewContractError`) — consumed, not modified.
- No new third-party dependencies.

---

## 19. Test Matrix Summary

- **Unit tests (planned):** 20 cases (U01–U20).
- **Harness scenarios (new):** W, X.
- **Harness total after implementation:** 24 scenarios (A through X),
  24/24 PASS.
- **Regression suites:** all existing pytest suites (`test_review_contract`,
  `test_review_adapter`, `test_mock_reviewer`, harness regression A–V)
  remain green.

---

## 20. Explicit Non-Goals

- No LLM invocation.
- No reviewer agent integration.
- No repair agent integration.
- No implementer (Ralph/OpenCode) invocation.
- No run lifecycle / state machine / resumability changes.
- No concurrency support changes.
- No prompt design.
- No change to any schema document.
- No change to `gates.json` policy.
- No change to backend or product code.
- No speculative scaffolding for WP-AL-1C4.

---

## 21. Open Decisions

None. All architectural decisions referenced in this document are
approved and recorded in §2:

- WP-AL-1C3 label: review-result reporting guard.
- Repair Contract renumbered to WP-AL-1C4.
- ERROR + `human_review` → `HUMAN_REVIEW_REQUIRED`.
- ERROR + other/missing action → `INFRASTRUCTURE_ERROR`.
- Invalid / malformed / unknown / unreadable → `INFRASTRUCTURE_ERROR`.
- Absent → `VERIFIED` (to be revisited by review bridge).
