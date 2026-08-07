# WP-AL-1C6 — Minimal Orchestration Wiring

**Status:** REMEDIATED — AWAITING PO APPROVAL (post-review)

**Branch (proposed):** `feature/agent-loop-orchestration-wiring`
**Base:** `origin/main` @ `764ca3e5b1b38e7a97370c478113e28588d152f8`
**Depends on:** WP-AL-1B3, WP-AL-1C1, WP-AL-1C2, WP-AL-1C3, WP-AL-1C4, WP-AL-1C5
**Precedes:** production review/repair hardening (later WP)

---

## 1. Status

**Status:** REMEDIATED — AWAITING PO APPROVAL (post-review)

**Title:** WP-AL-1C6 — Minimal Orchestration Wiring

**Branch (proposed):** `feature/agent-loop-orchestration-wiring`

**Base:** `origin/main` @ `764ca3e5b1b38e7a97370c478113e28588d152f8`

**Depends on:**
- WP-AL-1B3 (Failure Context Contract — merged PR #45)
- WP-AL-1C1 (Review Contract — merged PR #48)
- WP-AL-1C2 (Reviewer Adapter — merged PR #49)
- WP-AL-1C3 (Review-Result Reporting Guard — merged PR #52)
- WP-AL-1C4 (Repair Contract — merged PR #55)
- WP-AL-1C5 (Repair Adapter — merged PR #56)

**Precedes:** production review/repair hardening (later WP)

**Product Owner Approval:** APPROVED on 2026-08-07 (initial); REMEDIATED per independent review

**Supersedes:** The previous `docs/next_steps.md` statement that "review invocation/configuration bridge" would remain a separate future WP. For the minimum wiring required by WP-AL-1C5 §29, WP-AL-1C6 includes the minimum review invocation bridge. No general production reviewer configuration is introduced.

**Remediation:** This document was remediated to address independent review findings (REQUEST CHANGES). Three new architectural decisions (DEC-C6-02, DEC-C6-03, DEC-C6-04) were added. Five non-blocking findings (N1–N5) resolved.

---

## 2. Objective

Wire the existing review adapter and repair adapter into `run-story.sh` to enable the minimal supervised end-to-end cycle:

```
implement (committed candidate) → verify → review → optional one repair → reverify → human handoff
```

The WP delivers the orchestration glue that connects the six completed adapter
contracts (WP-AL-1B3 through WP-AL-1C5) into one bounded supervised flow.

This WP does NOT deliver:
- Autonomous retry loops
- Real LLM/provider integration
- Production hardening
- Automatic commit/push/merge
- Implementation-agent checkpoint mechanism

---

## 3. Authoritative Predecessor State

### 3.1 Completed adapters (all merged to origin/main @ 764ca3e5)

| WP | Component | Script | CLI entry |
|----|-----------|--------|-----------|
| WP-AL-1B3 | Failure Context | `lib/failure_context.py` | `collect --run-dir ...` |
| WP-AL-1C1 | Review Contract | `lib/review_contract.py` | `build-request --manifest ...` |
| WP-AL-1C2 | Reviewer Adapter | `lib/review_adapter.py` | `--repo-root ... --reviewer-command ...` |
| WP-AL-1C3 | Review-Result Reporting | `lib/review_result_reporting.py` | `classify --path ...` |
| WP-AL-1C4 | Repair Contract | `lib/repair_contract.py` | `build-request --failure-context ...` |
| WP-AL-1C5 | Repair Adapter | `lib/repair_adapter.py` | `--repo-root ... --actor-command ...` |

### 3.2 Orchestration scripts (existing, to be modified)

| Script | Current role |
|--------|-------------|
| `run-story.sh` | Main orchestrator (implement → verify → review/repair loop → report) |
| `verify-story.sh` | Deterministic verification (gates, failure-context collection) |
| `report-story.sh` | Final report generation |

### 3.3 Mock components (existing, to be reused)

| Component | Purpose |
|-----------|---------|
| `lib/mock_reviewer.py` | Deterministic mock reviewer (PASS/FAIL/ERROR modes) |
| `lib/mock_repair_actor.py` | Deterministic mock repair actor (REPAIRED/NO_CHANGE/ERROR modes) |

---

## 4. Superseded Older Review-Bridge Wording

`docs/next_steps.md` previously stated:

> "Review invocation/configuration bridge (separate future WP, NOT PLANNED)"

This is now **superseded** for the minimum wiring required by the dogfooding milestone. WP-AL-1C6 includes the minimum review invocation bridge — wiring `review_adapter.py` into `run-story.sh` after verification — but does NOT introduce general production reviewer configuration (provider selection, credential management, multi-reviewer fan-out, etc.).

The superseded text remains in `docs/next_steps.md` for historical reference but is overridden by this WP-AL-1C6 specification.

---

## 5. Exact State Machine

### 5.1 High-level state machine

```
START
  │
  ├─ pre-flight: verify committed candidate + clean tracked baseline
  │   ├─ dirty baseline → report (DIRTY_BASELINE) → END_HUMAN
  │   └─ clean → continue
  │
  ├─ implement (candidate already committed externally or by harness fixture)
  │
  ├─ verify [INITIAL]
  │   ├─ snapshot: verify-result.initial.json, failure-context.initial.json
  │   └─ exit code captured
  │
  ├─ verify exit 2 (ERROR) → report (INFRASTRUCTURE_ERROR) → END_FAIL
  │
  ├─ [verify result?]
  │   ├─ PASS ──► review (triggered_by=initial_verify_pass)
  │   │            │
  │   │            ├─ [review PASS?]
  │   │            │   └─ YES ──► report (ACCEPTED) ──► END_SUCCESS
  │   │            │
  │   │            ├─ [review FAIL?]
  │   │            │   ├─ action=repair ──► repair (attempt=1)
  │   │            │   │                    (see repair path below)
  │   │            │   ├─ action=human_review ──► report (HUMAN_REVIEW_REQUIRED) → END_HUMAN
  │   │            │   └─ action=none ──► report (REVIEW_REJECTED) → END_FAIL
  │   │            │
  │   │            └─ [review ERROR / INVALID?]
  │   │                ├─ ERROR + human_review ──► report (HUMAN_REVIEW_REQUIRED) → END_HUMAN
  │   │                ├─ ERROR (other) ──► report (INFRASTRUCTURE_ERROR) → END_FAIL
  │   │                └─ INVALID ──► report (INFRASTRUCTURE_ERROR) → END_FAIL
  │   │
  │   └─ FAIL ──► review (triggered_by=initial_verify_fail)
  │                │
  │                ├─ [review PASS?]
  │                │   └─ YES ──► report (VERIFICATION_FAILED) → END_FAIL
  │                │       (reviewer did not recommend repair; verification failure stands)
  │                │
  │                ├─ [review FAIL?]
  │                │   ├─ action=repair ──► [clean baseline confirmed?]
  │                │   │                     ├─ YES ──► repair (attempt=1)
  │                │   │                     └─ NO ──► report (DIRTY_BASELINE) → END_HUMAN
  │                │   ├─ action=human_review ──► report (HUMAN_REVIEW_REQUIRED) → END_HUMAN
  │                │   └─ action=none ──► report (VERIFICATION_FAILED) → END_FAIL
  │                │
  │                └─ [review ERROR / INVALID?]
  │                    ├─ ERROR + human_review ──► report (HUMAN_REVIEW_REQUIRED) → END_HUMAN
  │                    ├─ ERROR (other) ──► report (INFRASTRUCTURE_ERROR) → END_FAIL
  │                    └─ INVALID ──► report (INFRASTRUCTURE_ERROR) → END_FAIL
  │
  ├─ REPAIR PATH (from review FAIL + action=repair):
  │   ├─ repair adapter invoked (attempt=1, max_attempts=1)
  │   ├─ [adapter_status == ADAPTER_SUCCESS AND status == REPAIRED?]
  │   │   ├─ YES ──► snapshot immutable initial artifacts remain valid
  │   │   │          verify [REVERIFY]
  │   │   │            ├─ exit 0 (PASS) → report (VERIFIED_AFTER_REPAIR) → END_SUCCESS
  │   │   │            ├─ exit 1 (FAIL) → report (REPAIR_FAILED_REVERIFY) → END_FAIL
  │   │   │            └─ exit 2 (ERROR) → report (INFRASTRUCTURE_ERROR) → END_FAIL
  │   │   │
  │   │   └─ NO ──► report (REPAIR_ADAPTER_FAILURE) → END_FAIL
  │   │
  │   └─ No further repair permitted after attempt=1
  │
  └─ VERIFIED_AFTER_REPAIR requires ALL of:
      - valid repair adapter result (ADAPTER_SUCCESS + REPAIRED)
      - identity bindings match current run/story/attempt/source revision
      - reconciliation exact-match evidence valid
      - permission enforcement evidence valid
      - exactly one reverify actually executed
      - reverify result is valid and PASS
```

### 5.2 triggered_by value mapping

The review-request schema defines exactly three values for `triggered_by`:
- `"initial_verify_pass"` — review after verification PASS on iteration 0
- `"initial_verify_fail"` — review after verification FAIL on iteration 0
- `"post_repair_verify_pass"` — review after re-verification PASS following repair (reserved for future multi-iteration WPs)

The review-request builder uses:

- Verify PASS path: `triggered_by = "initial_verify_pass"`, `repair_iteration = 0`
- Verify FAIL path: `triggered_by = "initial_verify_fail"`, `repair_iteration = 0`

Note: In WP-AL-1C6, the post-repair path does not invoke review (reverify outcome goes directly to report). The `"post_repair_verify_pass"` value is reserved for future multi-iteration repair WPs.

### 5.3 Iteration semantics

WP-AL-1C6 enforces **maximum one repair attempt**. The existing
`MAX_REPAIR_ITERATIONS` variable (default 3) is overridden to 1 at the
orchestration level. The manifest's `repair_budget` may further narrow this
but cannot widen it beyond 1.

The orchestrator maintains a single `REPAIR_ATTEMPT` counter:
- Initial value: 0
- After repair adapter invocation completes: 1
- If `REPAIR_ATTEMPT >= 1`, no further repair is permitted

### 5.4 Initial verify vs reverify distinction

WP-AL-1C6 distinguishes initial verification from re-verification using the
smallest compatible mechanism: a **verify-context file**.

**Artifact:** `$RUN_DIR/reports/verify-context.json`

```json
{
  "schema_version": "1.0",
  "run_id": "...",
  "story_id": "...",
  "verify_type": "initial | reverify",
  "attempt": 0,
  "generated_at": "..."
}
```

**Authoritative fields:**
- `verify_type` — `"initial"` or `"reverify"` (string enum)
- `attempt` — integer (0 for initial, 1 for reverify)
- `run_id` — must match current run identity
- `story_id` — must match current story identity

**Deterministic semantics for verify-context handling:**

**ABSENT verify-context (file does not exist):**
- Backward-compatible default: `verify_type = "initial"`, `attempt = 0`
- Only where absence is explicitly permitted (existing harness scenarios)

**PRESENT but invalid/malformed verify-context (file exists):**
- Malformed JSON → `INFRASTRUCTURE_ERROR`, no success path
- Invalid `verify_type` value (not "initial" or "reverify") → `INFRASTRUCTURE_ERROR`
- Invalid `attempt` binding:
  - `verify_type = "initial"` with `attempt != 0` → `INFRASTRUCTURE_ERROR`
  - `verify_type = "reverify"` with `attempt != 1` → `INFRASTRUCTURE_ERROR`
- Identity mismatch (`run_id` or `story_id` does not match current run) → `INFRASTRUCTURE_ERROR`
- Missing required fields → `INFRASTRUCTURE_ERROR`

**Authoritative attempt bindings:**
- `verify_type = "initial"` requires `attempt = 0`
- `verify_type = "reverify"` requires `attempt = 1`
- Any other combination → `INFRASTRUCTURE_ERROR`

Before each verify-story.sh invocation, the orchestrator writes this file.
`verify-story.sh` reads it and includes `verify_context` in the verify-result.json
output under a new optional field `verify_context`.

Existing verify-result schema is extended with one optional field:
- `verify_context` (optional object): `verify_type`, `attempt`, `run_id`, `story_id`

This does NOT break existing scenarios because the field is optional and absent
in existing harness tests.

### 5.5 DEC-C6-02: Verification remains authoritative

**Rule:** A reviewer must NEVER override a failed verification.

Final outcome depends on BOTH initial verification status AND review status:

| Initial Verify | Review | Outcome |
|----------------|--------|---------|
| PASS | PASS | ACCEPTED (exit 0) |
| PASS | FAIL + repair | repair path |
| PASS | FAIL + human_review | HUMAN_REVIEW_REQUIRED |
| PASS | FAIL + none | REVIEW_REJECTED |
| PASS | ERROR/INVALID | fail-closed per §5.1 |
| FAIL | PASS | VERIFICATION_FAILED (exit 1) — review PASS does not override verify FAIL |
| FAIL | FAIL + repair | repair path |
| FAIL | FAIL + human_review | HUMAN_REVIEW_REQUIRED |
| FAIL | FAIL + none | VERIFICATION_FAILED |
| FAIL | ERROR/INVALID | fail-closed per §5.1 |

**Explicit regression:** initial verify FAIL + review PASS MUST NOT produce ACCEPTED or VERIFIED_AFTER_REPAIR.

### 5.6 DEC-C6-03: Immutable verification evidence

**Rule:** Initial verify/review/repair evidence must remain byte-stable after reverify.

**Problem:** verify-story.sh writes to `$RUN_DIR/reports/verify-result.json` and `$RUN_DIR/reports/failure-context.json`. If reverify overwrites these, downstream request artifacts (review-request, repair-request) that contain SHA-256 hashes and path references to the original files become invalid.

**Solution:** Immutable per-phase snapshots.

After initial verification completes (regardless of PASS/FAIL), the orchestrator MUST:
1. Copy `verify-result.json` → `verify-result.initial.json`
2. If `failure-context.json` exists, copy → `failure-context.initial.json`
3. Compute SHA-256 of each immutable snapshot
4. All downstream review-request and repair-request references target the immutable paths

After reverify completes:
1. Copy `verify-result.json` → `verify-result.reverify.json`
2. If failure-context was collected during reverify, copy → `failure-context.reverify.json`

The canonical working filenames (`verify-result.json`, `failure-context.json`) MAY continue to be used during verify-story.sh execution. run-story.sh owns snapshot publication.

**Failure semantics:** Inability to preserve required immutable evidence (e.g., snapshot copy failure, hash mismatch) → `INFRASTRUCTURE_ERROR`, no repair/reverify success path.

### 5.7 DEC-C6-04: Clean committed candidate precondition

**Rule:** WP-AL-1C5 repair adapter requires a clean tracked baseline. WP-AL-1C6 MUST NOT solve this by automatically committing implementation changes.

**Precondition for repair-capable flow:** The candidate implementation must already exist as a committed candidate revision with a clean tracked worktree before initial verification begins.

**Source of committed candidate:** External/supervised implementer, harness fixture, or manual commit. This is NOT automatic runtime commit behavior.

**Orchestrator pre-flight check:** Before entering a repair-capable flow (i.e., before invoking verify-story.sh when repair might be needed), the orchestrator verifies:
1. `git status --porcelain` shows no untracked or modified tracked files
2. `git diff --cached --name-status` is empty (nothing staged)
3. HEAD points to a valid commit

**If dirty baseline detected before verify:**
- If repair_budget > 0 (repair might be needed): report `DIRTY_BASELINE` → human handoff, repair actor NOT invoked
- If repair_budget == 0 (no repair possible): proceed with verify (repair not needed)

**Harness repair scenarios** must:
1. Create a disposable repository
2. Create the candidate implementation
3. Commit it
4. Verify tracked worktree is clean
5. Run initial verification
6. Enter review/repair/reverify
7. Prove actor invocation was not rejected merely because the candidate was left as uncommitted dirty baseline

---

## 6. Transition Table

| Current State | Event | Next State | Action |
|---------------|-------|------------|--------|
| START | begin | preflight | check committed candidate + clean baseline |
| preflight | dirty baseline | report_dirty | report DIRTY_BASELINE |
| preflight | clean baseline | verify_initial | invoke verify-story.sh |
| verify_initial | exit 0 (PASS) | snapshot_initial | preserve verify-result.initial.json, failure-context.initial.json |
| verify_initial | exit 1 (FAIL) | snapshot_initial | preserve verify-result.initial.json, failure-context.initial.json |
| verify_initial | exit 2 (ERROR) | infrastructure_error | report INFRASTRUCTURE_ERROR |
| snapshot_initial | snapshot OK | review | build review-request referencing immutable artifacts |
| snapshot_initial | snapshot FAIL | infrastructure_error | report INFRASTRUCTURE_ERROR |
| review (initial PASS) | status=PASS | report_accepted | report ACCEPTED |
| review (initial PASS) | status=FAIL, action=repair | repair | build repair-request, invoke repair_adapter.py |
| review (initial PASS) | status=FAIL, action=human_review | report_human | report HUMAN_REVIEW_REQUIRED |
| review (initial PASS) | status=FAIL, action=none | report_rejected | report REVIEW_REJECTED |
| review (initial FAIL) | status=PASS | report_verification_failed | report VERIFICATION_FAILED (verify FAIL stands) |
| review (initial FAIL) | status=FAIL, action=repair | pre_repair_check | verify clean baseline for repair |
| review (initial FAIL) | status=FAIL, action=human_review | report_human | report HUMAN_REVIEW_REQUIRED |
| review (initial FAIL) | status=FAIL, action=none | report_verification_failed | report VERIFICATION_FAILED |
| review | adapter ERROR + human_review | report_human | report HUMAN_REVIEW_REQUIRED |
| review | adapter ERROR (other) | report_infra | report INFRASTRUCTURE_ERROR |
| review | adapter INVALID | report_infra | report INFRASTRUCTURE_ERROR |
| pre_repair_check | clean baseline | repair | invoke repair_adapter.py |
| pre_repair_check | dirty baseline | report_dirty | report DIRTY_BASELINE |
| repair | adapter_status=ADAPTER_SUCCESS, status=REPAIRED | reverify | invoke verify-story.sh |
| repair | adapter_status=ADAPTER_SUCCESS, status=NO_CHANGE | report_no_change | report REPAIR_NO_CHANGE |
| repair | adapter_status=ADAPTER_SUCCESS, status=ERROR | report_infra | report INFRASTRUCTURE_ERROR |
| repair | adapter_status=non-success | report_adapter_fail | report REPAIR_ADAPTER_FAILURE |
| reverify | exit 0 (PASS) | validate_evidence | check all adapter-success evidence valid |
| reverify | exit 1 (FAIL) | report_repair_fail | report REPAIR_FAILED_REVERIFY |
| reverify | exit 2 (ERROR) | report_infra | report INFRASTRUCTURE_ERROR |
| validate_evidence | all evidence valid + reverify PASS | report_verified | report VERIFIED_AFTER_REPAIR |
| validate_evidence | evidence invalid | report_infra | report INFRASTRUCTURE_ERROR |

---

## 7. Artifact Ownership

| Artifact | Written by | Path | Immutable? |
|----------|-----------|------|------------|
| verify-context.json | run-story.sh | `$RUN_DIR/reports/verify-context.json` | No (overwritten per verify) |
| verify-result.json | verify-story.sh | `$RUN_DIR/reports/verify-result.json` | Working copy |
| verify-result.initial.json | run-story.sh (snapshot) | `$RUN_DIR/reports/verify-result.initial.json` | YES |
| verify-result.reverify.json | run-story.sh (snapshot) | `$RUN_DIR/reports/verify-result.reverify.json` | YES |
| failure-context.json | verify-story.sh | `$RUN_DIR/reports/failure-context.json` | Working copy |
| failure-context.initial.json | run-story.sh (snapshot) | `$RUN_DIR/reports/failure-context.initial.json` | YES |
| failure-context.reverify.json | run-story.sh (snapshot) | `$RUN_DIR/reports/failure-context.reverify.json` | YES |
| review-request.json | review_adapter.py | `$RUN_DIR/review/review-request.json` | No |
| review-result.json | review_adapter.py | `$RUN_DIR/reports/review-result.json` | No |
| repair-request.json | repair_adapter.py | `$RUN_DIR/repair/repair-request.json` | No |
| repair-result.json | repair actor | `$RUN_DIR/repair/repair-result.json` | No |
| repair-adapter-result.json | repair_adapter.py | `$RUN_DIR/repair/repair-adapter-result.json` | No |
| final-report.json | report-story.sh | `$RUN_DIR/reports/final-report.json` | No |

---

## 8. Initial Verify vs Reverify Semantics

### 8.1 Verify-context file

Before each `verify-story.sh` invocation, `run-story.sh` writes
`$RUN_DIR/reports/verify-context.json` with:

- `verify_type`: `"initial"` (first invocation) or `"reverify"` (after repair)
- `attempt`: 0 (initial), 1 (reverify after first repair)

### 8.2 verify-story.sh behavior

`verify-story.sh` reads `verify-context.json` if present and:
1. Includes `verify_context.verify_type` in verify-result.json output
2. Uses the same gate logic regardless of verify_type
3. Always collects failure-context on failure (existing behavior)

If `verify-context.json` does not exist (backward compatibility for existing
harness scenarios), verify-story.sh defaults to `verify_type = "initial"` and
`attempt = 0`.

### 8.3 Snapshot publication (DEC-C6-03)

After verify-story.sh completes, run-story.sh:
1. Copies `verify-result.json` → `verify-result.{initial|reverify}.json`
2. Copies `failure-context.json` → `failure-context.{initial|reverify}.json` (if present)
3. Computes SHA-256 of each immutable snapshot
4. Verifies snapshot integrity

If snapshot publication fails → INFRASTRUCTURE_ERROR, no further processing.

### 8.4 report-story.sh distinction

`report-story.sh` reads `verify_context` from verify-result.json and uses it
to determine the correct `final_status`:

- `verify_type = "initial"`, PASS → use review classification for final_status
- `verify_type = "initial"`, FAIL, review PASS → `VERIFICATION_FAILED` (DEC-C6-02)
- `verify_type = "reverify"`, PASS, all adapter evidence valid → `VERIFIED_AFTER_REPAIR`
- `verify_type = "reverify"`, PASS, evidence invalid → `INFRASTRUCTURE_ERROR`
- `verify_type = "reverify"`, FAIL → `REPAIR_FAILED_REVERIFY`
- `verify_type = "initial"`, FAIL, no repair → `VERIFICATION_FAILED`
- `verify_type = "initial"`, FAIL, repair attempted, reverify not done → depends on repair outcome

---

## 9. Review Invocation Protocol

### 9.1 When to invoke review

Review is invoked in two paths:
1. **After initial verify PASS** — standard review
2. **After initial verify FAIL** — review to determine if repair is possible

In both cases, the immutable failure-context snapshot must exist and be valid.

### 9.2 Failure-context requirement (N1)

The review-request schema REQUIRES `failure_context_ref` (path, schema_version,
sha256).

**DEC-C6-01 (REVISED):** The `failure_context_ref.overall_verification_status` field is conditionally validated based on `triggered_by`:
- `triggered_by = "initial_verify_pass"` requires `overall_verification_status = "PASS"`
- `triggered_by = "initial_verify_fail"` requires `overall_verification_status = "FAIL"`
- `triggered_by = "post_repair_verify_pass"` requires `overall_verification_status = "PASS"`

**Failure-context existence and validity:**
- For BOTH initial_verify_pass and initial_verify_fail, a valid failure-context artifact MUST exist.
- verify-story.sh collects failure-context on both PASS and FAIL exits.
- On PASS: failure-context has `overall_verification_status = "PASS"` (or equivalent pass-state).
- On FAIL: failure-context has `overall_verification_status = "FAIL"`.
- The orchestrator creates the immutable snapshot `failure-context.initial.json` after verify completes.
- Review adapter references the immutable snapshot path.

**If failure-context is missing, malformed, unreadable, identity-mismatched, or hash-invalid:**
→ `INFRASTRUCTURE_ERROR`
→ Reviewer must NOT be invoked with an invalid/missing required context.

**Contract extension scope:** The review contract (`review_contract.py`) validator is extended to enforce these conditional bindings. No schema changes are required — the conditional logic is added to the referential validation layer only.

### 9.3 Review adapter CLI invocation (verify PASS path)

```bash
"$PYTHON_BIN" "$SCRIPT_DIR/lib/review_adapter.py" \
  --repo-root "$REPO_ROOT" \
  --run-dir "$RUN_DIR" \
  --manifest "$STORY_MANIFEST" \
  --failure-context "$RUN_DIR/reports/failure-context.initial.json" \
  --run-id "$RUN_ID" \
  --story-id "$STORY_ID" \
  --review-iteration 1 \
  --repair-iteration 0 \
  --triggered-by "initial_verify_pass" \
  --generated-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --reviewer-id "$REVIEWER_ID" \
  --timeout-seconds "$REVIEW_TIMEOUT" \
  --reviewer-command "$REVIEWER_BIN" \
  --reviewer-arg "--mode" \
  --reviewer-arg "$REVIEWER_MODE"
```

Where:
- `REVIEWER_BIN`: reviewer executable (e.g., `"$PYTHON_BIN"` for mock_reviewer.py)
- `REVIEWER_MODE`: e.g., `"PASS"` or `"FAIL"` or `"ERROR"`
- `REVIEWER_ID`: e.g., `"mock-reviewer"`
- `REVIEW_TIMEOUT`: seconds (default 30, max 600)

The adapter appends `--request <path> --output <path>` to the reviewer command.

Note: `--failure-context` references the immutable snapshot `failure-context.initial.json`, not the working copy.

### 9.4 Reviewer executable configuration

For WP-AL-1C6, the reviewer executable is supplied through environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `REVIEWER_BIN` | Reviewer executable path | `""` (must be set) |
| `REVIEWER_MODE` | Mock reviewer mode (PASS/FAIL/ERROR) | `"PASS"` |
| `REVIEWER_ID` | Reviewer identifier | `"mock-reviewer"` |
| `REVIEW_TIMEOUT` | Review timeout in seconds | `30` |

These environment variables are the smallest deterministic configuration
mechanism compatible with the existing adapter and harness. No configuration
file or provider selection is introduced.

### 9.5 Review result interpretation

After review adapter invocation:
1. Check adapter exit code (0 = OK, 2 = ERROR)
2. If exit code != 0 → review adapter ERROR → fail closed
3. If exit code == 0 → read `$RUN_DIR/reports/review-result.json`
4. Classify using `review_result_reporting.py` (existing WP-AL-1C3 logic)
5. Based on classification:

**After initial verify PASS:**
   - PASS → ACCEPTED (proceed to report)
   - FAIL + recommended_action=repair → proceed to repair
   - FAIL + recommended_action=human_review → HUMAN_REVIEW_REQUIRED
   - FAIL + recommended_action=none → REVIEW_REJECTED
   - ERROR + recommended_action=human_review → HUMAN_REVIEW_REQUIRED
   - ERROR (other) → INFRASTRUCTURE_ERROR
   - INVALID → INFRASTRUCTURE_ERROR

**After initial verify FAIL (DEC-C6-02):**
   - PASS → VERIFICATION_FAILED (reviewer did not recommend repair; verify FAIL stands)
   - FAIL + recommended_action=repair → proceed to pre-repair baseline check
   - FAIL + recommended_action=human_review → HUMAN_REVIEW_REQUIRED
   - FAIL + recommended_action=none → VERIFICATION_FAILED
   - ERROR + recommended_action=human_review → HUMAN_REVIEW_REQUIRED
   - ERROR (other) → INFRASTRUCTURE_ERROR
   - INVALID → INFRASTRUCTURE_ERROR

---

## 10. Repair Invocation Protocol

### 10.1 When to invoke repair

Repair is invoked when:
- Review status = FAIL AND recommended_action = "repair"

For WP-AL-1C6, the only repair trigger is: review FAIL + action=repair.

### 10.2 Pre-repair baseline check (DEC-C6-04)

Before invoking repair_adapter.py, the orchestrator MUST verify:
1. `git status --porcelain` shows clean tracked worktree
2. `git diff --cached --name-status` is empty
3. HEAD points to a valid commit

If any check fails → `DIRTY_BASELINE` → human handoff, repair NOT invoked.

### 10.3 Repair adapter CLI invocation

```bash
"$PYTHON_BIN" "$SCRIPT_DIR/lib/repair_adapter.py" \
  --repo-root "$REPO_ROOT" \
  --run-dir "$RUN_DIR" \
  --manifest "$STORY_MANIFEST" \
  --failure-context "$RUN_DIR/reports/failure-context.initial.json" \
  --verify-result "$RUN_DIR/reports/verify-result.initial.json" \
  --review-result "$RUN_DIR/reports/review-result.json" \
  --run-id "$RUN_ID" \
  --story-id "$STORY_ID" \
  --attempt 1 \
  --max-attempts 1 \
  --source-revision "$(git rev-parse HEAD)" \
  --actor-command "$REPAIR_ACTOR_BIN" \
  --actor-arg "--mode" \
  --actor-arg "$REPAIR_ACTOR_MODE" \
  --timeout-seconds "$REPAIR_TIMEOUT" \
  --max-output-bytes 4096
```

Note: `--failure-context` and `--verify-result` reference immutable snapshots, not working copies.

Where:
- `REPAIR_ACTOR_BIN`: repair actor executable (e.g., `"$PYTHON_BIN"` for mock_repair_actor.py)
- `REPAIR_ACTOR_MODE`: e.g., `"REPAIRED"` or `"NO_CHANGE"` or `"ERROR"`
- `REPAIR_TIMEOUT`: seconds (default 120, max 600)

### 10.4 Repair actor executable configuration

For WP-AL-1C6, the repair actor executable is supplied through environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `REPAIR_ACTOR_BIN` | Repair actor executable path | `""` (must be set) |
| `REPAIR_ACTOR_MODE` | Mock actor mode (REPAIRED/NO_CHANGE/ERROR) | `"REPAIRED"` |
| `REPAIR_TIMEOUT` | Repair timeout in seconds | `120` |

### 10.5 Repair result interpretation

After repair adapter invocation:
1. Read `$RUN_DIR/repair/repair-adapter-result.json`
2. Check `adapter_status`:
   - `ADAPTER_SUCCESS` → continue to check `repair_result_summary`
   - Any other status → REPAIR_ADAPTER_FAILURE → fail closed
3. If `ADAPTER_SUCCESS`, check `repair_result_summary.status`:
   - `REPAIRED` → proceed to reverify
   - `NO_CHANGE` → REPAIR_NO_CHANGE → fail closed
   - `ERROR` → INFRASTRUCTURE_ERROR → fail closed
4. If `REPAIRED`, also check `reconciliation.exact_match == true` and
   `permission_enforcement.all_actual_changes_permitted == true`
   (these are already enforced by the adapter; if adapter_status=ADAPTER_SUCCESS,
   they are guaranteed)

### 10.6 Which adapter statuses allow reverify

Only `ADAPTER_SUCCESS` with `repair_result_summary.status == "REPAIRED"`
allows reverify. All other adapter statuses result in fail-closed reporting.

---

## 11. Human-Handoff Semantics

Human handoff occurs when the orchestrator cannot proceed autonomously:

| Condition | final_status | Meaning |
|-----------|-------------|---------|
| Initial verify FAIL + review PASS | `VERIFICATION_FAILED` | Verification failure stands; reviewer did not recommend repair |
| Review ERROR + action=human_review | `HUMAN_REVIEW_REQUIRED` | Reviewer infrastructure failed, human must decide |
| Review FAIL + action=human_review | `HUMAN_REVIEW_REQUIRED` | Reviewer rejected but asked for human |
| Review adapter ERROR (infrastructure) | `INFRASTRUCTURE_ERROR` | Review infrastructure failed |
| Repair adapter failure | `REPAIR_ADAPTER_FAILURE` | Repair infrastructure failed |
| Repair NO_CHANGE | `REPAIR_NO_CHANGE` | Actor chose not to repair |
| Repair REPAIRED + reverify FAIL | `REPAIR_FAILED_REVERIFY` | Repair did not fix the issue |
| Dirty baseline before repair | `DIRTY_BASELINE` | Tracked worktree not clean; repair adapter cannot proceed |
| Snapshot publication failure | `INFRASTRUCTURE_ERROR` | Immutable evidence could not be preserved |

In all handoff cases:
- No automatic retry
- No Git mutating commands (commit/push/merge/rebase/reset/clean/stash/branch-delete/force-ops)
- Final report includes all artifacts for human inspection
- Exit code is non-zero (failure)

---

## 12. Exit-Code Semantics

| Exit Code | Meaning |
|-----------|---------|
| 0 | ACCEPTED or VERIFIED_AFTER_REPAIR (success) |
| 1 | All failure cases (verification failed, review rejected, repair failed, infrastructure error) |
| 2 | Bootstrap guard failure or critical infrastructure error |

The orchestrator returns exit 0 only for the two success states:
- Initial verify PASS + review PASS → ACCEPTED
- Repair REPAIRED + valid evidence + reverify PASS → VERIFIED_AFTER_REPAIR

All other states return exit 1.

---

## 13. Passport Phase Transitions

The passport tracks phase progression. WP-AL-1C6 introduces one new orchestration phase:

| Phase | Role | Workspace Type | Status |
|-------|------|----------------|--------|
| `allocate` | `implementer` | `control-plane` | Existing |
| `implement` | `implementer` | `source` | Existing |
| `verify` | `verifier` | `validation` | Existing |
| `review` | `reviewer` | `validation` | Existing (now wired into orchestration) |
| `repair` | `repair` | `source` | Existing (now wired into orchestration) |
| `reverify` | `verifier` | `validation` | **New** — introduced by WP-AL-1C6 |
| `report` | `reporter` | `control-plane` | Existing |

### 13.1 Guard policy extensions (N5)

The existing guard policy (`lib/guard.sh`) must be extended to:

1. Accept the new `reverify` phase: role=`verifier`, workspace=`validation`
2. Enforce strict role/workspace binding for all review/repair/reverify phases:

| Phase | Required Role | Required Workspace | Guard Behavior |
|-------|--------------|-------------------|----------------|
| `review` | `reviewer` | `validation` | Accept correct; reject wrong role; reject wrong workspace |
| `repair` | `repair` | `source` | Accept correct; reject wrong role; reject wrong workspace |
| `reverify` | `verifier` | `validation` | Accept correct; reject wrong role; reject wrong workspace |

**Guard semantics:**
- Wrong role for a phase → guard rejects → `INFRASTRUCTURE_ERROR`
- Wrong workspace_type for a phase → guard rejects → `INFRASTRUCTURE_ERROR`
- Unknown phase (not in the table above) → guard rejects → `INFRASTRUCTURE_ERROR`

The guard must NOT permissively accept unknown phases. It must explicitly enumerate allowed phase/role/workspace combinations and reject all others.

These are already defined in `.agent-loop/project.json`:
- `roles.allowed`: `["manager", "implementer", "verifier", "reviewer", "repair", "reporter"]`
- `workspaces.allowed_types`: `["source", "validation", "control-plane"]`

The guard policy must accept ONLY the specified combinations and reject all others.

---

## 14. Exact File Allowlist

### 14.1 New files

| Path | Purpose |
|------|---------|
| `docs/planning/wp_al_1c6_orchestration_wiring.md` | This planning document |
| `docs/planning/wp_al_1c6_completion_report.md` | Completion report (after implementation) |
| `scripts/agent-loop/tests/test_orchestration_wiring.py` | Unit/integration tests for orchestration |

### 14.2 Modified files

| Path | Change |
|------|--------|
| `scripts/agent-loop/run-story.sh` | Wire review/repair/reverify invocation; snapshot publication; pre-flight checks |
| `scripts/agent-loop/report-story.sh` | Extend final report with repair adapter result, reverify result, verify_context, immutable artifact references |
| `scripts/agent-loop/verify-story.sh` | Read verify-context.json, include verify_context in verify-result.json |
| `scripts/agent-loop/lib/guard.sh` | Accept new phases with strict role/workspace enforcement |
| `scripts/agent-loop/tests/run_harness_scenarios.sh` | Add scenarios AB onward |
| `scripts/agent-loop/README.md` | Document WP-AL-1C6 completion |
| `docs/next_steps.md` | Record WP-AL-1C6 complete, supersede review-bridge wording |
| `.agent-loop/review/SCHEMA.md` | Add `triggered_by = "initial_verify_fail"` and conditional binding rules |
| `scripts/agent-loop/lib/review_contract.py` | Extend validator: accept new `triggered_by` value; conditional `overall_verification_status` check |
| `scripts/agent-loop/tests/test_review_contract.py` | Add tests for `initial_verify_fail` trigger and conditional binding |

**Note:** `scripts/agent-loop/lib/review_adapter.py` is NOT modified. The adapter already passes `triggered_by` as an opaque string to the review-request builder; enum/binding validation is enforced in `review_contract.py`.

**File counts:** 3 new files + 10 modified files = 13 total planned file changes

---

## 15. Forbidden Scope

The following files and concerns are explicitly OUT OF SCOPE:

- No real LLM/provider integration
- No production reviewer provider configuration
- No multiple repair iterations
- No generic retry engine
- No rollback
- No sandbox/container isolation
- No concurrency/parallel workers
- No automatic commit (runtime)
- No automatic push
- No automatic PR
- No automatic merge
- No branch lifecycle automation
- No ignored-file inspection
- No full filesystem snapshot
- No unrelated ForgeMind product code
- No changes to verify-story.sh gate logic
- No changes to review_adapter.py (adapter passes `triggered_by` as string through to builder; no enum validation in adapter code)
- No changes to repair_adapter.py
- No changes to review_contract.py or repair_contract.py **schema definitions** (only the referential validation layer in `review_contract.py` is extended with conditional binding rules)
- No changes to failure_context.py
- No changes to mock_reviewer.py or mock_repair_actor.py
- No Git mutating commands invoked by orchestration runtime (see §16.2 for permitted read-only operations)

---

## 16. Acceptance Criteria

### 16.1 Orchestration flow

| AC | Criterion |
|----|-----------|
| AC-01 | After initial verify PASS, reviewer adapter is invoked with correct parameters |
| AC-02 | After initial verify PASS + review PASS, final_status = ACCEPTED, exit 0 |
| AC-03 | After review FAIL + action=repair, repair adapter is invoked |
| AC-04 | After repair REPAIRED + adapter ADAPTER_SUCCESS + all evidence valid, exactly one reverify is invoked |
| AC-05 | After valid reverify PASS with all adapter evidence valid, final_status = VERIFIED_AFTER_REPAIR, exit 0 |
| AC-06 | After reverify FAIL, final_status = REPAIR_FAILED_REVERIFY, exit 1 |
| AC-07 | After repair adapter failure (non-ADAPTER_SUCCESS), fail closed |
| AC-08 | After review adapter ERROR + action=human_review, final_status = HUMAN_REVIEW_REQUIRED |
| AC-09 | After review adapter ERROR (other), final_status = INFRASTRUCTURE_ERROR |
| AC-10 | Maximum one repair attempt enforced (second repair never invoked) |
| AC-11 | No Git mutating/publishing/history-rewriting commands invoked by orchestration runtime |
| AC-12 | verify-context.json written before each verify-story.sh invocation |
| AC-13 | verify-result.json includes verify_context when present |
| AC-14 | report-story.sh distinguishes initial verify from reverify |
| AC-15 | Passport transitions through review, repair, reverify phases correctly |
| AC-16 | Guard policy accepts correct phase/role/workspace combinations AND rejects incorrect ones |
| AC-17 | After initial verify FAIL, reviewer adapter is invoked with triggered_by="initial_verify_fail" |
| AC-18 | Review contract extension: triggered_by="initial_verify_fail" requires overall_verification_status="FAIL" |
| AC-19 | Review contract extension: mismatched trigger/status combinations are rejected |
| AC-20 | Review adapter successfully invokes mock reviewer for verify-FAIL-triggered request |
| AC-21 | Initial verify FAIL + review PASS → VERIFICATION_FAILED (not ACCEPTED) |
| AC-22 | Immutable initial snapshots created before reverify |
| AC-23 | Immutable snapshot hashes remain valid after reverify |
| AC-24 | Reverify does not destroy initial evidence |
| AC-25 | Final report references both initial and reverify evidence |
| AC-26 | Repair-request references immutable artifacts (not working copies) |
| AC-27 | Committed candidate + clean baseline precondition verified before repair |
| AC-28 | Dirty baseline before repair → DIRTY_BASELINE, human handoff |
| AC-29 | VERIFIED_AFTER_REPAIR requires all adapter-success evidence valid |
| AC-30 | Missing/malformed/invalid failure-context → INFRASTRUCTURE_ERROR |

### 16.2 Fail-closed behavior

| AC | Criterion |
|----|-----------|
| AC-31 | Malformed review-result → INFRASTRUCTURE_ERROR, exit 1 |
| AC-32 | Malformed repair-result → INFRASTRUCTURE_ERROR, exit 1 |
| AC-33 | Review adapter invocation failure → fail closed, exit 1 |
| AC-34 | Repair adapter invocation failure → fail closed, exit 1 |
| AC-35 | Repair REPAIRED but adapter reconciliation failure → fail closed, exit 1 |
| AC-36 | Repair NO_CHANGE → REPAIR_NO_CHANGE, exit 1 |
| AC-37 | Snapshot publication failure → INFRASTRUCTURE_ERROR, exit 1 |
| AC-38 | Initial verify infrastructure ERROR → INFRASTRUCTURE_ERROR, exit 1 |
| AC-39 | Reverify infrastructure ERROR → INFRASTRUCTURE_ERROR, exit 1 |
| AC-40 | Wrong role for phase → INFRASTRUCTURE_ERROR, exit 1 |
| AC-41 | Wrong workspace_type for phase → INFRASTRUCTURE_ERROR, exit 1 |

### 16.3 Regression

| AC | Criterion |
|----|-----------|
| AC-42 | Existing harness scenarios A-AA (27 scenarios) all pass |
| AC-43 | Existing unit tests all pass |
| AC-44 | Dry-run mode unchanged |
| AC-45 | Bootstrap guard unchanged |
| AC-46 | Existing report-story.sh behavior preserved for absent review/repair |

### 16.4 Testing

| AC | Criterion |
|----|-----------|
| AC-47 | New unit tests cover orchestration transitions |
| AC-48 | New harness scenarios AB+ cover end-to-end paths |
| AC-49 | All new tests pass with evidence |
| AC-50 | Ruff clean for new/modified Python files |
| AC-51 | mypy --strict clean for new/modified Python files |

### 16.5 Documentation

| AC | Criterion |
|----|-----------|
| AC-52 | Planning document committed on planning branch |
| AC-53 | Completion report produced |
| AC-54 | README updated |
| AC-55 | next_steps.md updated |

**Total: 55 acceptance criteria (AC-01 through AC-55)**

### 16.6 Git safety semantics (N2)

The orchestration runtime MUST NOT invoke Git mutating/publishing/history-rewriting commands:

**Prohibited runtime actions:**
- `git commit`
- `git push`
- `git merge`
- `git rebase`
- `git reset` (with `--hard` or `--mixed`)
- `git clean`
- `git stash` (save/pop/drop)
- `git checkout` / `git switch` (branch mutations)
- `git branch -d` / `git branch -D` (branch deletion)
- Any force operations (`--force`, `--force-with-lease`)

**Permitted read-only operations** (used by guards/adapters):
- `git rev-parse HEAD`
- `git status --porcelain` (read-only inspection)
- `git diff --cached --name-status` (read-only inspection)
- `git log --oneline` (read-only)
- `git show` (read-only)

---

## 17. Deterministic Unit/Integration Test Matrix

### 17.1 New test file: `test_orchestration_wiring.py`

| Test ID | Description | Expected outcome |
|---------|-------------|------------------|
| OW-01 | run-story.sh invokes reviewer after initial verify PASS (triggered_by=initial_verify_pass) | Review adapter called with correct triggered_by |
| OW-02 | run-story.sh invokes reviewer after initial verify FAIL (triggered_by=initial_verify_fail) | Review adapter called with triggered_by=initial_verify_fail |
| OW-03 | initial_verify_fail trigger requires overall_verification_status=FAIL; PASS mismatch → reject at contract layer | Validator rejects mismatched trigger/status |
| OW-04 | initial_verify_pass trigger requires overall_verification_status=PASS; FAIL mismatch → reject | Validator rejects mismatched trigger/status |
| OW-05 | post_repair_verify_pass trigger requires overall_verification_status=PASS | Validator accepts match |
| OW-06 | Unknown triggered_by value → reject | Validator rejects |
| OW-07 | run-story.sh enforces max 1 repair (second repair blocked) | Second repair not invoked |
| OW-08 | run-story.sh invokes repair after review FAIL+action=repair | Repair adapter called |
| OW-09 | run-story.sh does not invoke repair after review PASS | Repair adapter not called |
| OW-10 | run-story.sh invokes reverify after repair REPAIRED | verify-story.sh called again |
| OW-11 | run-story.sh does not invoke reverify after repair NO_CHANGE | verify-story.sh not called |
| OW-12 | Repair REPAIRED + reverify PASS + all evidence valid → VERIFIED_AFTER_REPAIR, exit 0 | Correct final_status |
| OW-13 | Repair REPAIRED + reverify FAIL → REPAIR_FAILED_REVERIFY, exit 1 | Correct final_status |
| OW-14 | Repair adapter failure (non-ADAPTER_SUCCESS) → fail closed | REPAIR_ADAPTER_FAILURE |
| OW-15 | Repair NO_CHANGE → REPAIR_NO_CHANGE, exit 1 | Correct final_status |
| OW-16 | Review adapter ERROR + action=human_review → HUMAN_REVIEW_REQUIRED | Correct final_status |
| OW-17 | Review adapter ERROR (other) → INFRASTRUCTURE_ERROR | Correct final_status |
| OW-18 | Malformed review-result → INFRASTRUCTURE_ERROR | Correct final_status |
| OW-19 | Malformed repair-result → INFRASTRUCTURE_ERROR | Correct final_status |
| OW-20 | verify-context.json written with verify_type=initial before initial verify | File exists, correct content |
| OW-21 | verify-context.json written with verify_type=reverify after repair | File exists, correct content |
| OW-22 | verify-context with invalid verify_type value | INFRASTRUCTURE_ERROR, no success path |
| OW-23 | verify-context attempt binding mismatch: (a) verify_type="initial" with attempt != 0 → INFRASTRUCTURE_ERROR; (b) verify_type="reverify" with attempt != 1 → INFRASTRUCTURE_ERROR | Fail closed for both directions |
| OW-24 | verify-context identity mismatch: (a) run_id does not match current run → INFRASTRUCTURE_ERROR; (b) story_id does not match current story → INFRASTRUCTURE_ERROR | Fail closed for both identities |
| OW-25 | verify-context with malformed JSON | INFRASTRUCTURE_ERROR |
| OW-26 | verify-story.sh includes verify_context in verify-result when file present | Field present |
| OW-27 | report-story.sh distinguishes initial verify from reverify | Correct final_status |
| OW-28 | report-story.sh handles repair adapter result | repair field present |
| OW-29 | report-story.sh handles reverify result | reverify field present |
| OW-30 | Passport phase transition: verify→review | Phase updated |
| OW-31 | Passport phase transition: review→repair | Phase updated |
| OW-32 | Passport phase transition: repair→reverify | Phase updated |
| OW-33 | Guard accepts review phase with correct role+workspace | Guard passes |
| OW-34 | Guard accepts repair phase with correct role+workspace | Guard passes |
| OW-35 | Guard accepts reverify phase with correct role+workspace | Guard passes |
| OW-36 | Guard rejects review phase with wrong role | Guard rejects |
| OW-37 | Guard rejects review phase with wrong workspace_type | Guard rejects |
| OW-38 | Guard rejects reverify phase with wrong role | Guard rejects |
| OW-39 | Guard rejects reverify phase with wrong workspace_type | Guard rejects |
| OW-40 | End-to-end: verify FAIL → review(initial_verify_fail) → repair REPAIRED → reverify PASS → VERIFIED_AFTER_REPAIR | All adapters invoked in sequence, correct final_status |
| OW-41 | End-to-end: verify FAIL → review FAIL with action≠repair → VERIFICATION_FAILED (no repair) | Orchestrator does not invoke repair |
| OW-42 | Initial verify FAIL + review PASS → VERIFICATION_FAILED (not ACCEPTED) | Regression: verify FAIL stands |
| OW-43 | Dry-run mode skips review/repair | No adapter invocation |
| OW-44 | No Git mutating commands invoked by runtime | No commit/push/merge/rebase/reset/clean/stash/checkout/branch-delete/force-ops |
| OW-45 | Existing scenarios A-AA unaffected | All pass |
| OW-46 | Immutable initial snapshots created after verify | verify-result.initial.json, failure-context.initial.json exist |
| OW-47 | Immutable snapshot SHA-256 remains valid after reverify | Hash unchanged |
| OW-48 | Reverify creates separate snapshot | verify-result.reverify.json exists |
| OW-49 | Reverify does not destroy initial evidence | Initial snapshots still present and valid |
| OW-50 | Final report references both initial and reverify evidence | Both referenced |
| OW-51 | Repair-request references immutable verify-result.initial.json | Path correct |
| OW-52 | Review-request references immutable failure-context.initial.json | Path correct |
| OW-53 | Snapshot publication failure → INFRASTRUCTURE_ERROR | Correct final_status |
| OW-54 | Committed candidate + clean baseline → pre-flight passes | Orchestrator proceeds |
| OW-55 | Dirty tracked worktree before repair → DIRTY_BASELINE | Correct final_status |
| OW-56 | Missing failure-context before review → INFRASTRUCTURE_ERROR | Reviewer not invoked |
| OW-57 | Malformed failure-context before review → INFRASTRUCTURE_ERROR | Reviewer not invoked |
| OW-58 | Identity-mismatched failure-context → INFRASTRUCTURE_ERROR | Reviewer not invoked |
| OW-59 | Initial verify infrastructure ERROR → INFRASTRUCTURE_ERROR | Correct final_status |
| OW-60 | Reverify infrastructure ERROR → INFRASTRUCTURE_ERROR | Correct final_status |
| OW-61 | verify-context file ABSENT → backward-compatible defaults: verify_type=initial, attempt=0 | Backward compatible (existing harness scenarios) |
| OW-62 | verify-context PRESENT but malformed JSON → INFRASTRUCTURE_ERROR | Fail closed, no success path |
| OW-63 | repair_budget=0 + review recommends repair → VERIFICATION_FAILED, exit 1, no actor/reverify invoked | final_status=VERIFICATION_FAILED, exit 1 |
| OW-64 | Bare reverify PASS without valid adapter evidence → INFRASTRUCTURE_ERROR | VERIFIED_AFTER_REPAIR not produced |
| OW-65 | Reconciliation evidence invalid → INFRASTRUCTURE_ERROR | VERIFIED_AFTER_REPAIR not produced |
| OW-66 | Permission enforcement evidence invalid → INFRASTRUCTURE_ERROR | VERIFIED_AFTER_REPAIR not produced |

**Total: 66 new orchestration test cases**

### 17.2 Extended test file: `test_review_contract.py`

| Test ID | Description | Expected outcome |
|---------|-------------|------------------|
| RC-01 | triggered_by="initial_verify_fail" + overall_verification_status="FAIL" → valid | Validator accepts |
| RC-02 | triggered_by="initial_verify_fail" + overall_verification_status="PASS" → reject | Validator rejects |
| RC-03 | triggered_by="initial_verify_pass" + overall_verification_status="FAIL" → reject | Validator rejects (existing behavior preserved) |
| RC-04 | triggered_by="initial_verify_pass" + overall_verification_status="PASS" → valid | Validator accepts (existing behavior preserved) |
| RC-05 | triggered_by="post_repair_verify_pass" + overall_verification_status="PASS" → valid | Validator accepts |
| RC-06 | triggered_by="unknown_value" → reject | Validator rejects |
| RC-07 | build_review_request supports triggered_by="initial_verify_fail" | Builder produces valid request |
| RC-08 | Review adapter invokes mock reviewer for FAIL-triggered request | Mock reviewer called with initial_verify_fail |

**Total: 8 new review-contract test cases**

**Combined planned unit/integration test total: 66 + 8 = 74**

---

## 18. New Harness Scenarios

### 18.1 Scenario AB — Verify PASS + Review PASS

**Purpose:** Verify PASS + review PASS → ACCEPTED

**Setup:**
- Workspace with passing implementation (committed, clean baseline)
- Mock reviewer in PASS mode

**Expected:**
- verify-story.sh exits 0
- Immutable snapshots created
- Review adapter invoked with triggered_by=initial_verify_pass
- review-result.json status=PASS
- final_status=ACCEPTED, exit 0

### 18.2 Scenario AC — Verify FAIL + Review FAIL + Repair REPAIRED + Reverify PASS

**Purpose:** Full cycle with successful repair after verify FAIL

**Setup:**
- Workspace with failing implementation (committed, clean baseline)
- Mock reviewer in FAIL mode with action=repair
- Mock repair actor in REPAIRED mode

**Expected:**
- verify-story.sh exits 1
- Immutable snapshots created
- Review adapter invoked with triggered_by=initial_verify_fail
- review-result.json status=FAIL, action=repair
- Pre-repair baseline check passes
- Repair adapter invoked
- repair-adapter-result.json status=REPAIRED
- Reverify snapshots created
- verify-story.sh exits 0 (reverify)
- All adapter evidence valid
- final_status=VERIFIED_AFTER_REPAIR, exit 0

### 18.3 Scenario AD — Verify FAIL + Review FAIL + Repair Actor ERROR

**Purpose:** Repair actor returns ERROR; adapter publishes valid result; orchestrator fails closed

**Setup:**
- Workspace with failing implementation (committed, clean baseline)
- Mock reviewer in FAIL mode with action=repair
- Mock repair actor in ERROR mode

**Expected:**
- verify-story.sh exits 1
- Review adapter invoked with triggered_by=initial_verify_fail
- Pre-repair baseline check passes
- Repair adapter invoked
- repair-adapter-result.json adapter_status == ADAPTER_SUCCESS
- repair_result_summary.status == ERROR (actor returned ERROR; adapter published it)
- final_status == INFRASTRUCTURE_ERROR, exit 1
- No reverify invoked

### 18.4 Scenario AE — Verify PASS + Review ERROR + Human Review

**Purpose:** Review infrastructure error with human handoff

**Setup:**
- Workspace with passing implementation (committed, clean baseline)
- Mock reviewer in ERROR mode

**Expected:**
- verify-story.sh exits 0
- Review adapter invoked
- review-result.json status=ERROR, action=human_review
- final_status=HUMAN_REVIEW_REQUIRED, exit 1

### 18.5 Scenario AF — Verify FAIL + Review FAIL + Repair NO_CHANGE

**Purpose:** Repair actor chooses not to repair

**Setup:**
- Workspace with failing implementation (committed, clean baseline)
- Mock reviewer in FAIL mode with action=repair
- Mock repair actor in NO_CHANGE mode

**Expected:**
- verify-story.sh exits 1
- Review adapter invoked with triggered_by=initial_verify_fail
- Pre-repair baseline check passes
- Repair adapter invoked
- repair-adapter-result.json status=NO_CHANGE
- final_status=REPAIR_NO_CHANGE, exit 1

### 18.6 Scenario AG — Verify FAIL + Review FAIL + Repair REPAIRED + Reverify FAIL

**Purpose:** Repair succeeds but reverify still fails

**Setup:**
- Workspace with failing implementation (committed, clean baseline)
- Mock reviewer in FAIL mode with action=repair
- Mock repair actor in REPAIRED mode (but changes don't fix the issue)

**Expected:**
- verify-story.sh exits 1 (initial)
- Review adapter invoked with triggered_by=initial_verify_fail
- Pre-repair baseline check passes
- Repair adapter invoked
- Reverify snapshots created
- verify-story.sh exits 1 (reverify)
- final_status=REPAIR_FAILED_REVERIFY, exit 1

### 18.7 Scenario AH — Malformed Review Artifact

**Purpose:** Malformed review-result.json

**Setup:**
- Manually write malformed review-result.json

**Expected:**
- report-story.sh classifies as INVALID
- final_status=INFRASTRUCTURE_ERROR, exit 1

### 18.8 Scenario AI — Repair Adapter Enforcement Failure

**Purpose:** Repair adapter rejection

**Setup:**
- Mock repair actor makes undeclared changes

**Expected:**
- repair-adapter-result.json status=ADAPTER_UNDECLARED_CHANGE
- final_status=REPAIR_ADAPTER_FAILURE, exit 1

### 18.9 Scenario AJ — Max One Repair Enforced

**Purpose:** Prove that maximum one repair attempt is enforced regardless of outcome

**Setup:**
- Workspace with failing implementation (committed, clean baseline)
- Mock reviewer in FAIL mode with action=repair
- Mock repair actor in REPAIRED mode
- Orchestrator configured to attempt second repair after first repair completes

**Expected:**
- verify-story.sh exits 1 (initial)
- Review adapter invoked with triggered_by=initial_verify_fail
- Pre-repair baseline check passes
- Repair adapter invoked (attempt=1)
- repair-adapter-result.json adapter_status=ADAPTER_SUCCESS, status=REPAIRED
- Reverify invoked, exits 1 (FAIL)
- Orchestrator attempts second repair (forced by test configuration)
- Orchestrator blocks second repair attempt (REPAIR_ATTEMPT >= 1)
- Repair actor invocation count = 1 (proves only one execution)
- Repair adapter invocation count = 1 (proves only one invocation)
- final_status=REPAIR_FAILED_REVERIFY, exit 1

### 18.10 Scenario AK — Verify FAIL + Review PASS

**Purpose:** Regression: review PASS after verify FAIL must NOT produce ACCEPTED

**Setup:**
- Workspace with failing implementation (committed, clean baseline)
- Mock reviewer in PASS mode

**Expected:**
- verify-story.sh exits 1
- Review adapter invoked with triggered_by=initial_verify_fail
- review-result.json status=PASS
- final_status=VERIFICATION_FAILED, exit 1
- NOT ACCEPTED, NOT VERIFIED_AFTER_REPAIR

### 18.11 Scenario AL — Dirty Baseline Before Repair

**Purpose:** Repair blocked by dirty tracked worktree

**Setup:**
- Workspace with failing implementation
- Uncommitted tracked file modifications present
- Mock reviewer in FAIL mode with action=repair

**Expected:**
- verify-story.sh exits 1
- Review adapter invoked with triggered_by=initial_verify_fail
- review-result.json status=FAIL, action=repair
- Pre-repair baseline check fails (dirty worktree)
- Repair adapter NOT invoked
- final_status=DIRTY_BASELINE, exit 1

### 18.12 Scenario AM — Immutable Snapshot Integrity

**Purpose:** Initial snapshots survive reverify

**Setup:**
- Full repair cycle (verify FAIL → review FAIL → repair REPAIRED → reverify)

**Expected:**
- verify-result.initial.json exists and SHA-256 valid after reverify
- failure-context.initial.json exists and SHA-256 valid after reverify
- verify-result.reverify.json exists (separate from initial)
- Final report references both initial and reverify evidence
- final_status=VERIFIED_AFTER_REPAIR, exit 0

### 18.13 Scenario AN — Reverify Without Valid Adapter Evidence

**Purpose:** Bare reverify PASS must NOT produce VERIFIED_AFTER_REPAIR

**Setup:**
- Simulate reverify PASS without valid repair-adapter-result

**Expected:**
- verify-story.sh exits 0 (reverify)
- Adapter evidence validation fails
- final_status=INFRASTRUCTURE_ERROR, exit 1

**Total new harness scenarios: 13 (AB through AN)**
**Total harness scenarios after WP-AL-1C6: 40 (A through AN)**

---

## 19. Regression Expectations

All existing scenarios A-AA (27 scenarios) must remain green:
- A-O: 15 scenarios (WP-AL-1B2)
- P-S: 4 scenarios (WP-AL-1A)
- T: 1 scenario (WP-AL-1B3)
- U-V: 2 scenarios (WP-AL-1C2)
- W-X: 2 scenarios (WP-AL-1C3)
- Y-AA: 3 scenarios (WP-AL-1C5)

**Total existing: 27 scenarios (A through AA inclusive)**

All must pass without modification.

---

## 20. Rollback and Non-Goals

### 20.1 Non-goals (explicitly NOT delivered)

- Autonomous retry loop
- Real LLM/provider integration
- Production reviewer configuration
- Multiple repair iterations
- Generic retry engine
- Rollback
- Sandbox/container isolation
- Concurrency/parallel workers
- Automatic runtime commit/push/merge
- Branch lifecycle automation
- Ignored-file inspection
- Full filesystem snapshot
- Implementation-agent checkpoint mechanism

### 20.2 Rollback strategy

If WP-AL-1C6 implementation fails:
- Revert the feature branch
- All existing scenarios A-AA remain green
- No data loss (all artifacts under $RUN_DIR)
- No infrastructure changes

---

## 21. Dogfooding Exit Criterion

WP-AL-1C6 achieves the dogfooding milestone when:

1. The orchestrator can invoke review adapter after verification (PASS or FAIL)
2. The orchestrator enforces verification authority (review PASS after verify FAIL → VERIFICATION_FAILED)
3. The orchestrator can invoke repair adapter after review FAIL + action=repair
4. The orchestrator preserves immutable verification evidence
5. The orchestrator can re-invoke verify-story.sh after repair
6. The final report incorporates all artifacts (initial, review, repair, reverify)
7. Maximum one repair attempt is enforced
8. All fail-closed paths work correctly
9. Clean committed candidate precondition enforced
10. All harness scenarios (A through AN) pass
11. ForgeMind can be developed through one supervised Ralph-style agent cycle

The dogfooding cycle is **supervised**, not autonomous. A human observes the
cycle and approves the final result. No automatic commit/push/merge.

---

## 22. Definition of Done

- Branch created from `origin/main` @ `764ca3e5b1b38e7a97370c478113e28588d152f8`
- Implementation confined to the expected file scope in §14 (3 new + 10 modified files)
- All AC-01 through AC-55 pass with evidence
- All 74 new unit/integration tests pass (66 orchestration + 8 review-contract extension)
- All 13 new harness scenarios (AB-AN) pass
- All 27 existing harness scenarios (A-AA) pass
- Ruff clean for new/modified Python files
- mypy --strict clean for new/modified Python files
- README and next_steps.md updated
- Planning document updated to IMPLEMENTATION COMPLETE — AWAITING REVIEW
- Independent review artifacts produced (not by this WP)
- Product Owner review and merge approval

---

## 23. Architectural Decisions

All architectural decisions are RESOLVED.

### DEC-C6-01: Review after verify FAIL — Contract Extension

**Decision:** Review may be triggered after either initial verification PASS or
initial verification FAIL. This requires a narrow additive extension to the
review contract's `triggered_by` enum and the conditional validation of
`failure_context.overall_verification_status`.

**Additive review trigger:**

| `triggered_by` | Required `overall_verification_status` |
|----------------|---------------------------------------|
| `"initial_verify_pass"` | `"PASS"` |
| `"initial_verify_fail"` | `"FAIL"` |
| `"post_repair_verify_pass"` | `"PASS"` |

**Contract extension scope:**

- `.agent-loop/review/SCHEMA.md` — document the new `triggered_by` value and conditional binding rules
- `scripts/agent-loop/lib/review_contract.py` — extend structural validator to accept `"initial_verify_fail"` in `triggered_by`; replace unconditional `overall_verification_status == "PASS"` check with conditional check based on `triggered_by`
- `scripts/agent-loop/tests/test_review_contract.py` — add tests for new enum value and conditional binding
- `scripts/agent-loop/lib/review_adapter.py` — **NO changes required** (adapter passes `triggered_by` as string through to builder; no enum validation in adapter code)

**Backward compatibility:**

- All existing PASS-review behavior (`triggered_by="initial_verify_pass"` + `overall_verification_status="PASS"`) remains exactly unchanged
- All existing referential validation invariants preserved (identity, hash, path, sanitization, result-binding)
- Existing test R15 (`overall_verification_status` not PASS for `initial_verify_pass` trigger) continues to reject — same behavior
- No reviewer authorization semantics are added; reviewer still cannot override verification evidence

**Superseded:** The previous WP-AL-1C1 constraint that review only runs after verification PASS is narrowly superseded by this additive extension. WP-AL-1C1 PASS-only semantics remain intact; the extension only adds a new trigger path for the verify-FAIL case.

**Status:** RESOLVED — PO approved 2026-08-07

### DEC-C6-02: Verification Remains Authoritative

**Decision:** A reviewer must NEVER override a failed verification. Final outcome depends on BOTH initial verification status and review status.

**Authoritative semantics:**

| Initial Verify | Review | Outcome |
|----------------|--------|---------|
| PASS | PASS | ACCEPTED |
| PASS | FAIL + repair | repair path |
| PASS | FAIL + human_review | HUMAN_REVIEW_REQUIRED |
| PASS | FAIL + none | REVIEW_REJECTED |
| FAIL | PASS | VERIFICATION_FAILED (reviewer did not recommend repair; verify FAIL stands) |
| FAIL | FAIL + repair | repair path |
| FAIL | FAIL + human_review | HUMAN_REVIEW_REQUIRED |
| FAIL | FAIL + none | VERIFICATION_FAILED |

**Explicit regression:** initial verify FAIL + review PASS MUST NOT produce ACCEPTED or VERIFIED_AFTER_REPAIR.

**Rationale:** Verification is deterministic and authoritative. Review is advisory. Reviewer cannot convert failed verification into success. Review PASS after verify FAIL means only that reviewer did not recommend repair or additional rejection.

**Status:** RESOLVED — PO approved 2026-08-07 (remediation)

### DEC-C6-03: Immutable Verification Evidence

**Decision:** Initial verify/review/repair evidence must remain byte-stable after reverify. Immutable per-phase snapshots required.

**Problem:** verify-story.sh writes to canonical working filenames. If reverify overwrites these, downstream request artifacts (review-request, repair-request) that contain SHA-256 hashes and path references become invalid.

**Solution:**

After initial verification:
- `verify-result.json` → `verify-result.initial.json` (immutable)
- `failure-context.json` → `failure-context.initial.json` (immutable, when present)

After reverify:
- `verify-result.json` → `verify-result.reverify.json` (immutable)
- `failure-context.json` → `failure-context.reverify.json` (immutable, when present)

**Implementation:**
- verify-story.sh MAY continue using canonical working filenames during execution
- run-story.sh owns snapshot publication (copies after verify-story.sh completes)
- All downstream review-request and repair-request references target immutable paths
- SHA-256 of immutable snapshots must remain unchanged throughout run

**Failure semantics:**
- Inability to preserve required immutable evidence → INFRASTRUCTURE_ERROR
- No repair/reverify success path if snapshot publication fails

**Status:** RESOLVED — PO approved 2026-08-07 (remediation)

### DEC-C6-04: Clean Committed Candidate Precondition

**Decision:** WP-AL-1C5 repair adapter requires a clean tracked baseline. WP-AL-1C6 MUST NOT solve this by automatically committing implementation changes.

**Precondition for repair-capable flow:**
- Candidate implementation must already exist as a committed revision
- Clean tracked worktree required before initial verification begins
- Source: external/supervised implementer, harness fixture, or manual commit

**Orchestrator pre-flight check:**
- `git status --porcelain` shows no untracked or modified tracked files
- `git diff --cached --name-status` is empty
- HEAD points to valid commit

**Dirty baseline handling:**
- If repair_budget > 0 and baseline dirty → DIRTY_BASELINE → human handoff
- Repair adapter NOT invoked
- If repair_budget == 0 → proceed (repair not needed)

**Harness repair scenarios** must create disposable repo, commit candidate, verify clean baseline, then run orchestration.

**Status:** RESOLVED — PO approved 2026-08-07 (remediation)

---

## 24. Product Owner Approval

**INITIAL APPROVAL** — 2026-08-07

Product Owner initially approved:
1. The planning document (title: "WP-AL-1C6 — Minimal Orchestration Wiring")
2. DEC-C6-01 as RESOLVED
3. The minimum review invocation bridge
4. Maximum one repair attempt
5. The proposed branch name
6. The expected file scope
7. The test matrix
8. The harness scenarios
9. The dogfooding milestone

**REMEDIATION APPROVAL** — 2026-08-07

Product Owner approved remediation addressing independent review findings:
- DEC-C6-02: Verification remains authoritative
- DEC-C6-03: Immutable verification evidence
- DEC-C6-04: Clean committed candidate precondition
- N1–N5: Non-blocking findings resolved

**Document status:** REMEDIATED — AWAITING PO APPROVAL (post-review)

**Next step:** Product Owner reviews remediated document, approves, then commit and update PR #57.

---

## Appendix A: Comparison with Previous WPs

| Aspect | WP-AL-1C2 (Review Adapter) | WP-AL-1C5 (Repair Adapter) | WP-AL-1C6 (Orchestration Wiring) |
|--------|----------------------------|----------------------------|----------------------------------|
| Scope | Adapter only | Adapter only | Orchestration glue |
| Modifies run-story.sh | No | No | Yes |
| Modifies report-story.sh | No | No | Yes |
| Modifies verify-story.sh | No | No | Yes (verify-context) |
| New harness scenarios | U, V | Y, Z, AA | AB through AN |
| New unit/integration tests | 72 | 66 + 29 | 70 + 8 = 78 |
| Integration | No | No | Yes |

---

## Appendix B: Failure Taxonomy (Review)

| Review Result | recommended_action | final_status (after verify PASS) | final_status (after verify FAIL) |
|---------------|-------------------|----------------------------------|----------------------------------|
| PASS | none | ACCEPTED | VERIFICATION_FAILED |
| FAIL | repair | → repair path | → pre-repair check |
| FAIL | human_review | HUMAN_REVIEW_REQUIRED | HUMAN_REVIEW_REQUIRED |
| FAIL | none | REVIEW_REJECTED | VERIFICATION_FAILED |
| ERROR | human_review | HUMAN_REVIEW_REQUIRED | HUMAN_REVIEW_REQUIRED |
| ERROR | other | INFRASTRUCTURE_ERROR | INFRASTRUCTURE_ERROR |
| INVALID | — | INFRASTRUCTURE_ERROR | INFRASTRUCTURE_ERROR |

Note: Review PASS after verify FAIL produces VERIFICATION_FAILED, not ACCEPTED (DEC-C6-02).

---

## Appendix C: Failure Taxonomy (Repair Adapter)

| adapter_status | Category | Reverify? |
|----------------|----------|-----------|
| ADAPTER_SUCCESS + REPAIRED | Success | Yes |
| ADAPTER_SUCCESS + NO_CHANGE | Success | No → REPAIR_NO_CHANGE |
| ADAPTER_SUCCESS + ERROR | Success | No → INFRASTRUCTURE_ERROR |
| ADAPTER_DIRTY_BASELINE | Baseline | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_TIMEOUT | Invocation | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_NON_ZERO_EXIT | Invocation | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_MISSING_RESULT | Invocation | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_MALFORMED_RESULT | Validation | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_CONTRACT_VIOLATION | Validation | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_IDENTITY_MISMATCH | Validation | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_SOURCE_REVISION_DRIFT | Workspace | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_FORBIDDEN_CHANGE | Enforcement | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_UNDECLARED_CHANGE | Enforcement | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_DECLARED_MISSING | Enforcement | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_OUTPUT_SIZE_EXCEEDED | Invocation | No → REPAIR_ADAPTER_FAILURE |
| ADAPTER_INTERNAL_ERROR | Adapter | No → REPAIR_ADAPTER_FAILURE |

---

## Appendix D: Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `REVIEWER_BIN` | Reviewer executable path | `""` (must be set for review) |
| `REVIEWER_MODE` | Mock reviewer mode | `"PASS"` |
| `REVIEWER_ID` | Reviewer identifier | `"mock-reviewer"` |
| `REVIEW_TIMEOUT` | Review timeout (seconds) | `30` |
| `REPAIR_ACTOR_BIN` | Repair actor executable path | `""` (must be set for repair) |
| `REPAIR_ACTOR_MODE` | Mock actor mode | `"REPAIRED"` |
| `REPAIR_TIMEOUT` | Repair timeout (seconds) | `120` |
| `MAX_REPAIR_ITERATIONS` | Max repair attempts | `1` (overridden from default 3) |

---

## Appendix E: Artifact Path Summary

```
$RUN_DIR/
├── reports/
│   ├── passport.json
│   ├── verify-context.json                  (written by run-story.sh per verify)
│   ├── verify-result.json                   (working copy)
│   ├── verify-result.initial.json           (IMMUTABLE snapshot)
│   ├── verify-result.reverify.json          (IMMUTABLE snapshot)
│   ├── failure-context.json                 (working copy)
│   ├── failure-context.initial.json         (IMMUTABLE snapshot)
│   ├── failure-context.reverify.json        (IMMUTABLE snapshot)
│   ├── review-result.json
│   └── final-report.json                    (references all artifacts)
├── review/
│   ├── review-request.json                  (references immutable failure-context)
│   └── .adapter.lock
├── repair/
│   ├── repair-request.json                  (references immutable verify-result)
│   ├── repair-result.json
│   └── repair-adapter-result.json
└── verify/
    └── (gate logs)
```

---

## Appendix F: Non-Blocking Findings Resolution

### N1 — Failure-Context Requirement

**Finding:** Plan said failure-context is both always present and potentially absent.

**Resolution:** Failure-context MUST exist for both PASS and FAIL paths. verify-story.sh collects it on both exits. Orchestrator creates immutable snapshot. Review/repair adapters reference immutable snapshot. Missing/malformed/invalid failure-context → INFRASTRUCTURE_ERROR. Reviewer never invoked with invalid context.

### N2 — Git Safety Test Wording

**Finding:** "No git commands invoked" was too broad; adapters legitimately use read-only Git inspection.

**Resolution:** §16.2 now explicitly prohibits Git mutating/publishing/history-rewriting commands (commit, push, merge, rebase, reset --hard, clean, stash, checkout/switch mutations, branch deletion, force ops). Read-only operations (rev-parse, status --porcelain, diff --cached, log, show) are permitted. Test OW-39 verifies no mutating commands.

### N3 — Harness Determinism

**Finding:** Scenario AD and AJ had alternative acceptable outcomes.

**Resolution:**
- Scenario AD: Now specifies exact expected outcome: repair actor returns valid repair-result with status=ERROR, adapter publishes adapter_status=ADAPTER_SUCCESS with repair_result_summary.status=ERROR, orchestrator fails closed with final_status=INFRASTRUCTURE_ERROR, exit 1, no reverify. No alternatives.
- Scenario AJ: Now specifies exact setup (first repair succeeds with REPAIRED, reverify fails, orchestrator configured to attempt second repair) and exact expected outcome (second repair blocked, repair actor/adapter invocation counts prove exactly one execution, final_status=REPAIR_FAILED_REVERIFY, exit 1).

### N4 — Missing Test Cases

**Finding:** Several test cases missing.

**Resolution:** Added 26 new test cases:
- OW-23: Clarified attempt-binding tests in both directions (initial with attempt≠0; reverify with attempt≠1)
- OW-24: Clarified identity-mismatch tests for both run_id and story_id
- OW-61: Clarified absent verify-context defaults to initial/0
- OW-41–OW-47: Immutable snapshot tests (7)
- OW-48: Snapshot publication failure (1)
- OW-49–OW-50: Pre-flight baseline tests (2)
- OW-51–OW-53: Failure-context validation tests (3)
- OW-54–OW-55: Infrastructure ERROR tests (2)
- OW-56–OW-62: Verify-context edge cases including absent, malformed, identity mismatch (7)
- OW-63: repair_budget=0 behavior (1)
- OW-64–OW-66: Adapter-success evidence validation tests (3)

### N5 — Passport/Guard Semantics

**Finding:** Guard behavior for reverify not explicitly tested/enforced.

**Resolution:** §13.1 now explicitly requires guard to accept ONLY correct phase/role/workspace combinations and reject all others. Added tests OW-32–OW-34 verifying guard rejects wrong role/workspace_type. AC-16 updated to require both acceptance and rejection.

---

**End of WP-AL-1C6 Planning Specification (Remediated)**
