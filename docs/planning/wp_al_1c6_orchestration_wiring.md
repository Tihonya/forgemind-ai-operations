# WP-AL-1C6 — Minimal Orchestration Wiring

**Status:** APPROVED — READY FOR PLANNING COMMIT

**Branch (proposed):** `feature/agent-loop-orchestration-wiring`
**Base:** `origin/main` @ `764ca3e5b1b38e7a97370c478113e28588d152f8`
**Depends on:** WP-AL-1B3, WP-AL-1C1, WP-AL-1C2, WP-AL-1C3, WP-AL-1C4, WP-AL-1C5
**Precedes:** production review/repair hardening (later WP)

---

## 1. Status

**Status:** APPROVED — READY FOR PLANNING COMMIT

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

**Product Owner Approval:** APPROVED on 2026-08-07

**Supersedes:** The previous `docs/next_steps.md` statement that "review invocation/configuration bridge" would remain a separate future WP. For the minimum wiring required by WP-AL-1C5 §29, WP-AL-1C6 includes the minimum review invocation bridge. No general production reviewer configuration is introduced.

---

## 2. Objective

Wire the existing review adapter and repair adapter into `run-story.sh` to enable the minimal supervised end-to-end cycle:

```
implement → verify → review → optional one repair → reverify → human handoff
```

The WP delivers the orchestration glue that connects the six completed adapter
contracts (WP-AL-1B3 through WP-AL-1C5) into one bounded supervised flow.

This WP does NOT deliver:
- Autonomous retry loops
- Real LLM/provider integration
- Production hardening
- Automatic commit/push/merge

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
  ├─ implement (dry-run placeholder; workspace prepared by harness or manual)
  │
  ├─ verify [INITIAL]
  │   └─ failure-context collected (always, PASS or FAIL)
  │
  ├─ [verify result?]
  │   ├─ PASS ──► review (triggered_by=initial_verify_pass, repair_iteration=0)
  │   │            │
  │   │            ├─ [review PASS?]
  │   │            │   ├─ YES ──► report (ACCEPTED) ──► END_SUCCESS
  │   │            │   │
  │   │            │   └─ NO ──► [recommended_action == "repair"?]
  │   │            │               ├─ YES ──► repair (attempt=1)
  │   │            │               │            │
  │   │            │               │            ├─ [adapter_status == ADAPTER_SUCCESS
  │   │            │               │            │   AND status == REPAIRED]
  │   │            │               │            │   ├─ YES ──► verify [REVERIFY]
  │   │            │               │            │   │            │
  │   │            │               │            │   │            ├─ PASS ──► report (VERIFIED_AFTER_REPAIR) ──► END_SUCCESS
  │   │            │               │            │   │            │
  │   │            │               │            │   │            └─ FAIL ──► report (REPAIR_FAILED_REVERIFY) ──► END_FAIL
  │   │            │               │            │   │
  │   │            │               │            │   └─ NO ──► report (REPAIR_ADAPTER_FAILURE) ──► END_FAIL
  │   │            │               │            │
  │   │            │               │            └─ (other) ──► report (REPAIR_FAILED) ──► END_FAIL
  │   │            │               │
  │   │            │               └─ NO ──► [recommended_action == "human_review"?]
  │   │            │                           ├─ YES ──► report (HUMAN_REVIEW_REQUIRED) ──► END_HUMAN
  │   │            │                           └─ NO  ──► report (REVIEW_REJECTED) ──► END_FAIL
  │   │            │
  │   │            └─ [review adapter ERROR / INVALID?]
  │   │                ├─ ERROR + human_review ──► report (HUMAN_REVIEW_REQUIRED) ──► END_HUMAN
  │   │                ├─ ERROR (other) ──► report (INFRASTRUCTURE_ERROR) ──► END_FAIL
  │   │                └─ INVALID ──► report (INFRASTRUCTURE_ERROR) ──► END_FAIL
  │   │
  │   └─ FAIL ──► review (triggered_by=initial_verify_fail, repair_iteration=0)
  │                │
  │                ├─ [review recommends "repair"?]
  │                │   ├─ YES ──► repair (attempt=1)
  │                │   │            (same reverify path as above)
  │                │   │
  │                │   └─ NO ──► report (VERIFICATION_FAILED) ──► END_FAIL
  │                │
  │                └─ [review adapter ERROR / INVALID?]
  │                    ├─ ERROR + human_review ──► report (HUMAN_REVIEW_REQUIRED) ──► END_HUMAN
  │                    ├─ ERROR (other) ──► report (INFRASTRUCTURE_ERROR) ──► END_FAIL
  │                    └─ INVALID ──► report (INFRASTRUCTURE_ERROR) ──► END_FAIL
```

### 5.2 triggered_by value mapping

The review-request schema defines exactly three values for `triggered_by`:
- `"initial_verify_pass"` — review after verification PASS on iteration 0
- `"initial_verify_fail"` — review after verification FAIL on iteration 0
- `"post_repair_verify_pass"` — review after re-verification PASS following repair

The review-request builder uses:

- Verify PASS path: `triggered_by = "initial_verify_pass"`, `repair_iteration = 0`
- Verify FAIL path: `triggered_by = "initial_verify_fail"`, `repair_iteration = 0`
- Post-repair reverify PASS path: `triggered_by = "post_repair_verify_pass"`, `repair_iteration = 1`

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

Before each verify-story.sh invocation, the orchestrator writes this file.
`verify-story.sh` reads it and includes `verify_type` in the verify-result.json
output under a new optional field `verify_context`.

Existing verify-result schema is extended with one optional field:
- `verify_context` (optional object): `verify_type`, `attempt`

This does NOT break existing scenarios because the field is optional and absent
in existing harness tests.

---

## 6. Transition Table

| Current State | Event | Next State | Action |
|---------------|-------|------------|--------|
| START | begin | implement | placeholder / dry-run |
| implement | done | verify_initial | invoke verify-story.sh |
| verify_initial | exit 0 (PASS) | review | build review-request, invoke review_adapter.py |
| verify_initial | exit 1 (FAIL) | review_fail_path | build review-request, invoke review_adapter.py |
| verify_initial | exit 2 (ERROR) | infrastructure_error | report INFRASTRUCTURE_ERROR |
| review | status=PASS | report_accepted | report ACCEPTED |
| review | status=FAIL, action=repair | repair | build repair-request, invoke repair_adapter.py |
| review | status=FAIL, action=human_review | report_human | report HUMAN_REVIEW_REQUIRED |
| review | status=FAIL, action=none | report_rejected | report REVIEW_REJECTED |
| review | status=ERROR, action=human_review | report_human | report HUMAN_REVIEW_REQUIRED |
| review | status=ERROR, other | report_infra | report INFRASTRUCTURE_ERROR |
| review | adapter ERROR / INVALID | report_infra | report INFRASTRUCTURE_ERROR |
| repair | adapter_status=ADAPTER_SUCCESS, status=REPAIRED | reverify | invoke verify-story.sh |
| repair | adapter_status=ADAPTER_SUCCESS, status=NO_CHANGE | report_no_change | report REPAIR_NO_CHANGE |
| repair | adapter_status=ADAPTER_SUCCESS, status=ERROR | report_infra | report INFRASTRUCTURE_ERROR |
| repair | adapter_status=non-success | report_adapter_fail | report REPAIR_ADAPTER_FAILURE |
| reverify | exit 0 (PASS) | report_verified | report VERIFIED_AFTER_REPAIR |
| reverify | exit 1 (FAIL) | report_repair_fail | report REPAIR_FAILED_REVERIFY |
| reverify | exit 2 (ERROR) | report_infra | report INFRASTRUCTURE_ERROR |

---

## 7. Artifact Ownership

| Artifact | Written by | Path |
|----------|-----------|------|
| verify-result.json | verify-story.sh | `$RUN_DIR/reports/verify-result.json` |
| verify-context.json | run-story.sh | `$RUN_DIR/reports/verify-context.json` |
| failure-context.json | verify-story.sh (via failure_context.py) | `$RUN_DIR/reports/failure-context.json` |
| review-request.json | review_adapter.py | `$RUN_DIR/review/review-request.json` |
| review-result.json | review_adapter.py | `$RUN_DIR/reports/review-result.json` |
| repair-request.json | repair_adapter.py | `$RUN_DIR/repair/repair-request.json` |
| repair-result.json | repair actor | `$RUN_DIR/repair/repair-result.json` |
| repair-adapter-result.json | repair_adapter.py | `$RUN_DIR/repair/repair-adapter-result.json` |
| final-report.json | report-story.sh | `$RUN_DIR/reports/final-report.json` |

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

### 8.3 report-story.sh distinction

`report-story.sh` reads `verify_context` from verify-result.json and uses it
to determine the correct `final_status`:

- `verify_type = "initial"`, PASS → use review classification for final_status
- `verify_type = "reverify"`, PASS → `VERIFIED_AFTER_REPAIR`
- `verify_type = "reverify"`, FAIL → `REPAIR_FAILED_REVERIFY`
- `verify_type = "initial"`, FAIL, no repair → `VERIFICATION_FAILED`
- `verify_type = "initial"`, FAIL, repair attempted, reverify not done → depends on repair outcome

---

## 9. Review Invocation Protocol

### 9.1 When to invoke review

Review is invoked in two paths:
1. **After initial verify PASS** — standard review
2. **After initial verify FAIL** — review to determine if repair is possible

In both cases, failure-context is already present (verify-story.sh collects it
on both PASS and FAIL; on PASS the failure-context may have `overall_status = "PASS"`
or may not exist — see §9.3).

### 9.2 Failure-context requirement

The review-request schema REQUIRES `failure_context_ref` (path, schema_version,
sha256).

**DEC-C6-01 (REVISED):** The `failure_context_ref.overall_verification_status` field is conditionally validated based on `triggered_by`:
- `triggered_by = "initial_verify_pass"` requires `overall_verification_status = "PASS"`
- `triggered_by = "initial_verify_fail"` requires `overall_verification_status = "FAIL"`
- `triggered_by = "post_repair_verify_pass"` requires `overall_verification_status = "PASS"`

This enables the supervised self-development cycle where verification failures are reviewed before repair, while maintaining backward compatibility with existing PASS-review semantics.

**Contract extension scope:** The review contract (`review_contract.py`) validator is extended to enforce these conditional bindings. No schema changes are required — the conditional logic is added to the referential validation layer only.

### 9.3 Review adapter CLI invocation (verify PASS path)

```bash
"$PYTHON_BIN" "$SCRIPT_DIR/lib/review_adapter.py" \
  --repo-root "$REPO_ROOT" \
  --run-dir "$RUN_DIR" \
  --manifest "$STORY_MANIFEST" \
  --failure-context "$RUN_DIR/reports/failure-context.json" \
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
   - PASS → ACCEPTED (proceed to report)
   - FAIL + recommended_action=repair → proceed to repair
   - FAIL + recommended_action=human_review → HUMAN_REVIEW_REQUIRED
   - FAIL + recommended_action=none → REVIEW_REJECTED
   - ERROR + recommended_action=human_review → HUMAN_REVIEW_REQUIRED
   - ERROR (other) → INFRASTRUCTURE_ERROR
   - INVALID → INFRASTRUCTURE_ERROR

---

## 10. Repair Invocation Protocol

### 10.1 When to invoke repair

Repair is invoked when:
- Review status = FAIL AND recommended_action = "repair"
- OR (future) verify FAIL AND repair_budget > 0

For WP-AL-1C6, the only repair trigger is: review FAIL + action=repair.

### 10.2 Repair adapter CLI invocation

```bash
"$PYTHON_BIN" "$SCRIPT_DIR/lib/repair_adapter.py" \
  --repo-root "$REPO_ROOT" \
  --run-dir "$RUN_DIR" \
  --manifest "$STORY_MANIFEST" \
  --failure-context "$RUN_DIR/reports/failure-context.json" \
  --verify-result "$RUN_DIR/reports/verify-result.json" \
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

Where:
- `REPAIR_ACTOR_BIN`: repair actor executable (e.g., `"$PYTHON_BIN"` for mock_repair_actor.py)
- `REPAIR_ACTOR_MODE`: e.g., `"REPAIRED"` or `"NO_CHANGE"` or `"ERROR"`
- `REPAIR_TIMEOUT`: seconds (default 120, max 600)

### 10.3 Repair actor executable configuration

For WP-AL-1C6, the repair actor executable is supplied through environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `REPAIR_ACTOR_BIN` | Repair actor executable path | `""` (must be set) |
| `REPAIR_ACTOR_MODE` | Mock actor mode (REPAIRED/NO_CHANGE/ERROR) | `"REPAIRED"` |
| `REPAIR_TIMEOUT` | Repair timeout in seconds | `120` |

### 10.4 Repair result interpretation

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

### 10.5 Which adapter statuses allow reverify

Only `ADAPTER_SUCCESS` with `repair_result_summary.status == "REPAIRED"`
allows reverify. All other adapter statuses result in fail-closed reporting.

---

## 11. Human-Handoff Semantics

Human handoff occurs when the orchestrator cannot proceed autonomously:

| Condition | final_status | Meaning |
|-----------|-------------|---------|
| Review ERROR + action=human_review | `HUMAN_REVIEW_REQUIRED` | Reviewer infrastructure failed, human must decide |
| Review FAIL + action=human_review | `HUMAN_REVIEW_REQUIRED` | Reviewer rejected but asked for human |
| Review adapter ERROR (infrastructure) | `INFRASTRUCTURE_ERROR` | Review infrastructure failed |
| Repair adapter failure | `REPAIR_ADAPTER_FAILURE` | Repair infrastructure failed |
| Repair NO_CHANGE | `REPAIR_NO_CHANGE` | Actor chose not to repair |
| Repair REPAIRED + reverify FAIL | `REPAIR_FAILED_REVERIFY` | Repair did not fix the issue |

In all handoff cases:
- No automatic retry
- No automatic commit/push/merge
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
- Review PASS → ACCEPTED
- Repair REPAIRED + reverify PASS → VERIFIED_AFTER_REPAIR

All other states return exit 1.

---

## 13. Passport Phase Transitions

The passport tracks phase progression. WP-AL-1C6 introduces new phases:

| Phase | Role | Workspace Type | When |
|-------|------|----------------|------|
| `allocate` | `implementer` | `control-plane` | Bootstrap |
| `implement` | `implementer` | `source` | Before verify (existing) |
| `verify` | `verifier` | `validation` | Initial verify (existing) |
| `review` | `reviewer` | `validation` | After verify PASS (new) |
| `repair` | `repair` | `source` | After review FAIL+repair (new) |
| `reverify` | `verifier` | `validation` | After repair REPAIRED (new) |
| `report` | `reporter` | `control-plane` | Final reporting (existing) |

### 13.1 Guard policy extensions

The existing guard policy (`lib/guard.sh`) must be extended to accept the new
phases:
- `review` phase: role=`reviewer`, workspace=`validation`
- `repair` phase: role=`repair`, workspace=`source`
- `reverify` phase: role=`verifier`, workspace=`validation`

These are already defined in `.agent-loop/project.json`:
- `roles.allowed`: `["manager", "implementer", "verifier", "reviewer", "repair", "reporter"]`
- `workspaces.allowed_types`: `["source", "validation", "control-plane"]`

The guard policy must accept these phase/role/workspace combinations.

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
| `scripts/agent-loop/run-story.sh` | Wire review/repair/reverify invocation |
| `scripts/agent-loop/report-story.sh` | Extend final report with repair adapter result, reverify result, verify_context |
| `scripts/agent-loop/verify-story.sh` | Read verify-context.json, include verify_context in verify-result.json |
| `scripts/agent-loop/lib/guard.sh` | Accept new phases (review, repair, reverify) |
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
- No automatic commit
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

---

## 16. Acceptance Criteria

### 16.1 Orchestration flow

| AC | Criterion |
|----|-----------|
| AC-01 | After initial verify PASS, reviewer adapter is invoked with correct parameters |
| AC-02 | After review PASS, final_status = ACCEPTED, exit 0 |
| AC-03 | After review FAIL + action=repair, repair adapter is invoked |
| AC-04 | After repair REPAIRED + adapter ADAPTER_SUCCESS, reverify is invoked |
| AC-05 | After reverify PASS, final_status = VERIFIED_AFTER_REPAIR, exit 0 |
| AC-06 | After reverify FAIL, final_status = REPAIR_FAILED_REVERIFY, exit 1 |
| AC-07 | After repair adapter failure (non-ADAPTER_SUCCESS), fail closed |
| AC-08 | After review adapter ERROR + action=human_review, final_status = HUMAN_REVIEW_REQUIRED |
| AC-09 | After review adapter ERROR (other), final_status = INFRASTRUCTURE_ERROR |
| AC-10 | Maximum one repair attempt enforced (second repair never invoked) |
| AC-11 | No automatic commit/push/merge in any path |
| AC-12 | verify-context.json written before each verify-story.sh invocation |
| AC-13 | verify-result.json includes verify_context when present |
| AC-14 | report-story.sh distinguishes initial verify from reverify |
| AC-15 | Passport transitions through review, repair, reverify phases correctly |
| AC-16 | Guard policy accepts new phase/role/workspace combinations |
| AC-17 | After initial verify FAIL, reviewer adapter is invoked with triggered_by="initial_verify_fail" |
| AC-18 | Review contract extension: triggered_by="initial_verify_fail" requires overall_verification_status="FAIL" |
| AC-19 | Review contract extension: mismatched trigger/status combinations are rejected |
| AC-20 | Review adapter successfully invokes mock reviewer for verify-FAIL-triggered request |

### 16.2 Fail-closed behavior

| AC | Criterion |
|----|-----------|
| AC-21 | Malformed review-result → INFRASTRUCTURE_ERROR, exit 1 |
| AC-22 | Malformed repair-result → INFRASTRUCTURE_ERROR, exit 1 |
| AC-23 | Review adapter invocation failure → fail closed, exit 1 |
| AC-24 | Repair adapter invocation failure → fail closed, exit 1 |
| AC-25 | Repair REPAIRED but adapter reconciliation failure → fail closed, exit 1 |
| AC-26 | Repair NO_CHANGE → REPAIR_NO_CHANGE, exit 1 |

### 16.3 Regression

| AC | Criterion |
|----|-----------|
| AC-27 | Existing harness scenarios A-AA (27 scenarios) all pass |
| AC-28 | Existing unit tests all pass |
| AC-29 | Dry-run mode unchanged |
| AC-30 | Bootstrap guard unchanged |
| AC-31 | Existing report-story.sh behavior preserved for absent review/repair |

### 16.4 Testing

| AC | Criterion |
|----|-----------|
| AC-32 | New unit tests cover orchestration transitions |
| AC-33 | New harness scenarios AB+ cover end-to-end paths |
| AC-34 | All new tests pass with evidence |
| AC-35 | Ruff clean for new/modified Python files |
| AC-36 | mypy --strict clean for new/modified Python files |

### 16.5 Documentation

| AC | Criterion |
|----|-----------|
| AC-37 | Planning document committed on planning branch |
| AC-38 | Completion report produced |
| AC-39 | README updated |
| AC-40 | next_steps.md updated |

**Total: 40 acceptance criteria (AC-01 through AC-40)**

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
| OW-12 | Repair REPAIRED + reverify PASS → VERIFIED_AFTER_REPAIR, exit 0 | Correct final_status |
| OW-13 | Repair REPAIRED + reverify FAIL → REPAIR_FAILED_REVERIFY, exit 1 | Correct final_status |
| OW-14 | Repair adapter failure (non-ADAPTER_SUCCESS) → fail closed | REPAIR_ADAPTER_FAILURE |
| OW-15 | Repair NO_CHANGE → REPAIR_NO_CHANGE, exit 1 | Correct final_status |
| OW-16 | Review adapter ERROR + action=human_review → HUMAN_REVIEW_REQUIRED | Correct final_status |
| OW-17 | Review adapter ERROR (other) → INFRASTRUCTURE_ERROR | Correct final_status |
| OW-18 | Malformed review-result → INFRASTRUCTURE_ERROR | Correct final_status |
| OW-19 | Malformed repair-result → INFRASTRUCTURE_ERROR | Correct final_status |
| OW-20 | verify-context.json written with verify_type=initial before initial verify | File exists, correct content |
| OW-21 | verify-context.json written with verify_type=reverify after repair | File exists, correct content |
| OW-22 | verify-story.sh includes verify_context in verify-result when file present | Field present |
| OW-23 | report-story.sh distinguishes initial verify from reverify | Correct final_status |
| OW-24 | report-story.sh handles repair adapter result | repair field present |
| OW-25 | report-story.sh handles reverify result | reverify field present |
| OW-26 | Passport phase transition: verify→review | Phase updated |
| OW-27 | Passport phase transition: review→repair | Phase updated |
| OW-28 | Passport phase transition: repair→reverify | Phase updated |
| OW-29 | Guard accepts review phase | Guard passes |
| OW-30 | Guard accepts repair phase | Guard passes |
| OW-31 | Guard accepts reverify phase | Guard passes |
| OW-32 | End-to-end: verify FAIL → review(initial_verify_fail) → repair REPAIRED → reverify PASS → VERIFIED_AFTER_REPAIR | All adapters invoked in sequence, correct final_status |
| OW-33 | End-to-end: verify FAIL → review FAIL with action≠repair → VERIFICATION_FAILED (no repair) | Orchestrator does not invoke repair |
| OW-34 | Dry-run mode skips review/repair | No adapter invocation |
| OW-35 | No automatic commit/push/merge in any path | No git commands invoked |
| OW-36 | Existing scenarios A-AA unaffected | All pass |

**Total: 36 new orchestration test cases**

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

**Combined planned unit/integration test total: 36 + 8 = 44**

---

## 18. New Harness Scenarios

### 18.1 Scenario AB — Review PASS (happy path)

**Purpose:** Verify PASS + review PASS → ACCEPTED

**Setup:**
- Workspace with passing implementation
- Mock reviewer in PASS mode

**Expected:**
- verify-story.sh exits 0
- Review adapter invoked
- review-result.json status=PASS
- final_status=ACCEPTED, exit 0

### 18.2 Scenario AC — Review FAIL + repair REPAIRED + reverify PASS

**Purpose:** Full cycle with successful repair

**Setup:**
- Workspace with failing implementation
- Mock reviewer in FAIL mode with action=repair
- Mock repair actor in REPAIRED mode

**Expected:**
- verify-story.sh exits 1
- Review adapter invoked
- review-result.json status=FAIL, action=repair
- Repair adapter invoked
- repair-adapter-result.json status=REPAIRED
- verify-story.sh exits 0 (reverify)
- final_status=VERIFIED_AFTER_REPAIR, exit 0

### 18.3 Scenario AD — Review FAIL + repair failure

**Purpose:** Repair adapter failure

**Setup:**
- Workspace with failing implementation
- Mock reviewer in FAIL mode with action=repair
- Mock repair actor in ERROR mode

**Expected:**
- verify-story.sh exits 1
- Review adapter invoked
- Repair adapter invoked
- repair-adapter-result.json status=ERROR or adapter failure
- final_status=REPAIR_ADAPTER_FAILURE or INFRASTRUCTURE_ERROR, exit 1

### 18.4 Scenario AE — Review ERROR + human_review

**Purpose:** Review infrastructure error with human handoff

**Setup:**
- Workspace with passing implementation
- Mock reviewer in ERROR mode

**Expected:**
- verify-story.sh exits 0
- Review adapter invoked
- review-result.json status=ERROR, action=human_review
- final_status=HUMAN_REVIEW_REQUIRED, exit 1

### 18.5 Scenario AF — Review FAIL + repair NO_CHANGE

**Purpose:** Repair actor chooses not to repair

**Setup:**
- Workspace with failing implementation
- Mock reviewer in FAIL mode with action=repair
- Mock repair actor in NO_CHANGE mode

**Expected:**
- verify-story.sh exits 1
- Review adapter invoked
- Repair adapter invoked
- repair-adapter-result.json status=NO_CHANGE
- final_status=REPAIR_NO_CHANGE, exit 1

### 18.6 Scenario AG — Review FAIL + repair REPAIRED + reverify FAIL

**Purpose:** Repair succeeds but reverify still fails

**Setup:**
- Workspace with failing implementation
- Mock reviewer in FAIL mode with action=repair
- Mock repair actor in REPAIRED mode (but changes don't fix the issue)

**Expected:**
- verify-story.sh exits 1 (initial)
- Review adapter invoked
- Repair adapter invoked
- verify-story.sh exits 1 (reverify)
- final_status=REPAIR_FAILED_REVERIFY, exit 1

### 18.7 Scenario AH — Malformed review artifact

**Purpose:** Malformed review-result.json

**Setup:**
- Manually write malformed review-result.json

**Expected:**
- report-story.sh classifies as INVALID
- final_status=INFRASTRUCTURE_ERROR, exit 1

### 18.8 Scenario AI — Repair adapter rejection

**Purpose:** Repair adapter enforcement failure

**Setup:**
- Mock repair actor makes undeclared changes

**Expected:**
- repair-adapter-result.json status=ADAPTER_UNDECLARED_CHANGE
- final_status=REPAIR_ADAPTER_FAILURE, exit 1

### 18.9 Scenario AJ — Max one repair enforced

**Purpose:** Second repair attempt blocked

**Setup:**
- Force a second repair invocation attempt

**Expected:**
- Orchestrator refuses second repair
- final_status reflects first repair outcome

**Total new harness scenarios: 9 (AB through AJ)**
**Total harness scenarios after WP-AL-1C6: 36 (A through AJ)**

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
- Automatic commit/push/merge
- Branch lifecycle automation
- Ignored-file inspection
- Full filesystem snapshot

### 20.2 Rollback strategy

If WP-AL-1C6 implementation fails:
- Revert the feature branch
- All existing scenarios A-AA remain green
- No data loss (all artifacts under $RUN_DIR)
- No infrastructure changes

---

## 21. Dogfooding Exit Criterion

WP-AL-1C6 achieves the dogfooding milestone when:

1. The orchestrator can invoke review adapter after verification
2. The orchestrator can invoke repair adapter after review FAIL
3. The orchestrator can re-invoke verify-story.sh after repair
4. The final report incorporates all artifacts
5. Maximum one repair attempt is enforced
6. All fail-closed paths work correctly
7. All harness scenarios (A through AJ) pass
8. ForgeMind can be developed through one supervised Ralph-style agent cycle

The dogfooding cycle is **supervised**, not autonomous. A human observes the
cycle and approves the final result. No automatic commit/push/merge.

---

## 22. Definition of Done

- Branch created from `origin/main` @ `764ca3e5b1b38e7a97370c478113e28588d152f8`
- Implementation confined to the expected file scope in §14 (3 new + 10 modified files)
- All AC-01 through AC-40 pass with evidence
- All 44 new unit/integration tests pass (36 orchestration + 8 review-contract extension)
- All 9 new harness scenarios (AB-AJ) pass
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

**Source-of-truth note:** WP-AL-1B3 failure-context was explicitly designed as structured downstream input for reviewer, repair, and reporter. The WP-AL-1C1 PASS-only review restriction was based on the first review use case. WP-AL-1C6 extends this to enable the supervised self-development cycle per the PO's intended flow.

**Status:** RESOLVED — PO approved 2026-08-07

---

## 24. Product Owner Approval

**APPROVED** — 2026-08-07

Product Owner has approved:

1. The planning document (title: "WP-AL-1C6 — Minimal Orchestration Wiring")
2. All architectural decisions (DEC-C6-01) as RESOLVED
3. The minimum review invocation bridge (supersedes older wording)
4. Maximum one repair attempt (overrides max_repair_iterations=3)
5. The proposed branch name (`feature/agent-loop-orchestration-wiring`)
6. The expected file scope (3 new files, 10 modified files = 13 total file changes)
7. The test matrix (44 unit/integration tests: 36 orchestration + 8 review-contract extension; 9 harness scenarios AB-AJ)
8. The harness scenarios (AB through AJ — exactly 9)
9. The dogfooding milestone (one supervised end-to-end cycle)
10. The review contract extension (DEC-C6-01): `triggered_by` enum extended to include `"initial_verify_fail"` with conditional `overall_verification_status` binding

**Document status:** APPROVED — READY FOR PLANNING COMMIT

**Next step:** Create planning branch from origin/main, commit this planning document, then create implementation branch for development.

---

## Appendix A: Comparison with Previous WPs

| Aspect | WP-AL-1C2 (Review Adapter) | WP-AL-1C5 (Repair Adapter) | WP-AL-1C6 (Orchestration Wiring) |
|--------|----------------------------|----------------------------|----------------------------------|
| Scope | Adapter only | Adapter only | Orchestration glue |
| Modifies run-story.sh | No | No | Yes |
| Modifies report-story.sh | No | No | Yes |
| Modifies verify-story.sh | No | No | Yes (verify-context) |
| New harness scenarios | U, V | Y, Z, AA | AB through AJ |
| New unit/integration tests | 72 | 66 + 29 | 36 + 8 = 44 |
| Integration | No | No | Yes |

---

## Appendix B: Failure Taxonomy (Review)

| Review Result | recommended_action | final_status |
|---------------|-------------------|--------------|
| PASS | none | ACCEPTED |
| FAIL | repair | → repair path |
| FAIL | human_review | HUMAN_REVIEW_REQUIRED |
| FAIL | none | REVIEW_REJECTED |
| ERROR | human_review | HUMAN_REVIEW_REQUIRED |
| ERROR | other | INFRASTRUCTURE_ERROR |
| INVALID | — | INFRASTRUCTURE_ERROR |
| ABSENT | — | VERIFIED |

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
│   ├── verify-context.json          (NEW: written by run-story.sh)
│   ├── verify-result.json           (MODIFIED: includes verify_context)
│   ├── failure-context.json
│   ├── review-result.json
│   └── final-report.json            (MODIFIED: includes repair adapter result)
├── review/
│   ├── review-request.json
│   └── .adapter.lock
├── repair/
│   ├── repair-request.json
│   ├── repair-result.json
│   └── repair-adapter-result.json
└── verify/
    └── (gate logs)
```

---

**End of WP-AL-1C6 Planning Specification**
