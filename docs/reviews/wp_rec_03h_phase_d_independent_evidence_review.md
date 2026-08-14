# WP-REC-03H Phase D — Independent Read-Only Evidence Review

**Reviewer:** Hermes Agent (independent, read-only)
**Date:** 2026-08-14
**Authoritative candidate run:** `wp-rec-03h-phase-c-20260813-02`
**Previously failed run:** `wp-rec-03h-phase-c-20260813-01` (permanently preserved, non-acceptable, non-reusable)
**Expected corrected main commit:** `686739fd1e56ec4072b52029e01e3a6d8f9963cb`
**Corrective PR:** #85 (`fix(acceptance): repair WP-REC-03H formal finalization`)

---

## 1. Preflight Identities

| Item | Expected | Observed | Status |
|------|----------|----------|--------|
| Repository remote | github.com/Tihonya/forgemind-ai-operations | `https://github.com/Tihonya/forgemind-ai-operations.git` | MATCH |
| Current branch | main | `main` | MATCH |
| Local HEAD | `686739fd…` | `686739fd1e56ec4072b52029e01e3a6d8f9963cb` | MATCH |
| Local main | `686739fd…` | `686739fd1e56ec4072b52029e01e3a6d8f9963cb` | MATCH |
| origin/main | `686739fd…` | `686739fd1e56ec4072b52029e01e3a6d8f9963cb` | MATCH |
| GitHub main head | `686739fd…` | `686739fd…` (`git ls-remote origin refs/heads/main`) | MATCH (no advancement) |
| Staging | empty | empty | MATCH |
| Stash | none | none | MATCH |
| Tracked changes | none | none | MATCH |
| Untracked | only protected audit | `?? docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md` | MATCH (sole entry) |
| PR #85 | MERGED, merge commit `686739fd…` | state=MERGED, mergeCommit.oid=`686739fd…`, mergedAt=`2026-08-13T19:57:30Z`, headRefOid=`0b2edeb…` | MATCH |
| Protected audit SHA-256 | `639a2529…e89657` | `639a2529351bdacc606c6c5bbede44b82c73a7aefa26ae249bb592dec8e89657` | MATCH |
| Protected audit lines/bytes | 437 / 29036 | 437 / 29036 | MATCH |
| Failed run `-01` | 71 files / 300481 B / hash `e04c7f9d…a981` / no manifest | 71 / 300481 / `e04c7f9d967e33cc466f73f38f66431a5d37bc42785af94ef7d9d7a7c80aa981` / manifest absent | MATCH |
| Candidate run `-02` | 41 files / 272956 B / hash `0efe3acb…88dd` / manifest present | 41 / 272956 / `0efe3acb7533fc0cce1afd8f2957b9ee27afc18b40acf9d2b1f110b6019b88dd` / manifest present | MATCH |
| Third Phase C run | absent | only `-01` and `-02` exist | MATCH |
| Acceptance infra running | none | no ports 5433/6380/8001/5174 listening; no Docker containers; no uvicorn/worker/playwright processes | MATCH |

**Stop conditions:** none triggered. No staged/tracked changes; protected audit and both evidence fingerprints exact; no unexpected formal-run directory; baseline commit and evidence files all present.

---

## 2. Authoritative Phase D and Evidence-Contract Sources

Primary authoritative sources (blob SHAs verified at commit `686739fd…`):

| # | File | Section / symbol | Requirement | Explicit / Inferred |
|---|------|------------------|-------------|---------------------|
| 1 | `docs/planning/wp_rec_03h_acceptance_harness.md` | §0 "Lifecycle Phases", Phase C | Phase C = Formal Acceptance Execution (run harness in formal-evidence mode, collect evidence); must NOT itself declare PASS | Explicit |
| 2 | same | §0 "Lifecycle Phases", Phase D | Phase D = Product Owner Evidence Review and Acceptance Declaration: PO reviews evidence, explicitly declares AT-008/AT-013 PASS and Phase 5 acceptance; MUST NOT be automated | Explicit |
| 3 | same | §0 "Lifecycle Phases", Phase E | Phase E = Documentation Lifecycle Reconciliation (separate authorization after Phase D) | Explicit |
| 4 | same | §4.7.1 category 2 | `environment/versions.json` = "System" tool versions via `python --version` / `node --version` / `docker --version` | Explicit |
| 5 | same | §4.7.2 step 4 | SHA-256 checksums for all **redacted** artifacts, excluding checksum file itself | Explicit |
| 6 | same | §13 Authorization Boundary | Evidence review (Phase D) and acceptance declaration separated from execution (Phase C) | Explicit |
| 7 | `scripts/acceptance_harness.py` | `class BrowserResult` (line 222) | BrowserResult schema: schema_version, scenario, harness_execution_id, product_workflow_run_id, correlation_id, plan_id, browser_test_start/end, final_state, dispatch_generation, screenshots[], pre/post_retry_snapshot | Explicit (code) |
| 8 | `scripts/acceptance_harness.py` | `_write_manifest()` (line 1868) | `artifact_count = len(artifacts_list)` — count equals list-entry count | Explicit (code) |
| 9 | `scripts/tests/test_acceptance_harness_formal.py` | `test_manifest_artifact_count_matches_list` (line 2381) | `assert manifest["artifact_count"] == len(manifest["artifacts"])` — the formal contract ties artifact_count to **list entries**, NOT unique paths | Explicit (test = contract) |
| 10 | `scripts/acceptance_harness.py` | `collect_scenario_identity()` (line 1589) | scenario identity recorded per scenario | Explicit (code) |
| 11 | `scripts/acceptance_harness.py` | `capture_tool_versions()` (line 475) | versions captured via `python3 --version` (system `python3`) | Explicit (code) |
| 12 | `forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md` | AT-008 | invalid structure → `FAILED_VALIDATION`, no write actions, error visible in trace | Explicit |
| 13 | same | AT-013 | endpoint unavailable → risk result remains available, failed AI step shown, UI does not hang, user can retry | Explicit |
| 14 | `backend/app/api/workflow.py` | retry path (lines 456–501) | atomic conditional `FAILED_* → PENDING` with dispatch-generation increment | Explicit (code) |
| 15 | `backend/app/ai/provider/acceptance_scenarios.py` | `InvalidOutputProvider`, `OutageUntilRetryProvider` | deterministic scenario semantics | Explicit (code) |

No conflict among authoritative documents was found. The only place the term "formal-evidence contract" is materially encoded beyond the planning doc is the harness code itself and its formal test suite (`scripts/tests/test_acceptance_harness_formal.py`), which is the executable definition of correctness. Both are at commit `686739fd…`.

---

## 3. Source and Execution Provenance

| Claim | Evidence | Verdict |
|-------|----------|---------|
| Run ID is exactly `wp-rec-03h-phase-c-20260813-02` | `redacted/manifest.json` `run_id`; both `redacted/scenarios/*/identity.json` `harness_run_id`; both BrowserResult `harness_execution_id` | EVIDENCED |
| Execution used commit `686739fd…` | `redacted/repository/baseline.json` and `final.json` both record `head = 686739fd1e56ec4072b52029e01e3a6d8f9963cb`; identical before/after | EVIDENCED |
| Command was formal mode | Exact formal command recorded in the Phase C execution report §8: `/home/toha/Projects/forgemind-ai-operations/.venv/bin/python3.12 scripts/acceptance_harness.py --mode=formal --run-id wp-rec-03h-phase-c-20260813-02`; corroborated in-package by manifest `complete:true` + finalized redacted package (only `--mode=formal` writes it) | EVIDENCED (report + structural) |
| Invocation count = one | single `-02` directory; `validate_evidence_dir_not_exists` guard rejects a pre-existing dir; no `-03` directory | EVIDENCED (structural) |
| No retry of the run | coherent single timestamp sequence (20:15:07 → 20:15:55); no second manifest or re-generated artifacts | EVIDENCED |
| Both scenarios same execution | identical `harness_run_id` in both identity.json and both BrowserResults; single `baseline.json`/`final.json` | EVIDENCED |
| Coherent timestamp sequence | backend AT008 start 20:15:07 → AT008 playwright end 20:15:17 → AT013 backend 20:15:27 → AT013 playwright end 20:15:53 → manifest `generated_at` 20:15:55.712477Z | EVIDENCED (monotonic) |
| Teardown after collection | no acceptance infra currently running (ports free, no containers/processes) | EVIDENCED |
| No artifact copied from `-01` | distinct workflow run IDs (`e4a0bf34…`/`593f0711…` vs `801f5e32…`/`7bd6bca7…`), distinct correlation IDs, distinct timestamps (20:15 vs 17:14); `-02` has no `raw/` (successful cleanup) whereas `-01` retained `raw/` | EVIDENCED |
| Candidate not modified after finalization | manifest `generated_at` precedes review; aggregate hash stable before/after review (see §15) | EVIDENCED |

**Exit-code note:** the literal exit code (0) and the exact formal command are recorded in the Phase C execution report (`/tmp/wp-rec-03h-phase-c-second-formal-execution-report.md` §8–§9) and its console transcript (`/tmp/wp-rec-03h-phase-c-formal-02-console.log`, `HARNESS_EXIT_CODE=0`), not directly inside the finalized evidence package. In-package, the exit code is strongly corroborated structurally: `run_formal_mode()` returns `0` only after `redact_and_verify()` succeeds, and `redact_and_verify()` deletes `raw/` only as its final step. Run `-02` has no `raw/` directory and a finalized `manifest.json` with `complete:true` — a state only reachable on the success path. This is corroborating structural evidence, not a primary exit-code record.

---

## 4. Manifest Structure and Duplicate-Path Analysis

Parsed `redacted/manifest.json` (read-only, not modified):

| Property | Value |
|----------|-------|
| Declared schema/version field | **absent** (manifest has no `schema_version`; BrowserResult artifacts do carry `schema_version: "1.0"`) |
| `run_id` | `wp-rec-03h-phase-c-20260813-02` |
| `complete` | `true` |
| `artifact_count` (declared) | `31` |
| Actual list-entry count | `31` |
| Unique normalized paths | `29` |
| Duplicate paths | `scenarios/AT008_INVALID_OUTPUT/identity.json` (×2), `scenarios/AT013_OUTAGE_UNTIL_RETRY/identity.json` (×2) |
| Duplicate hashes identical? | Yes — each pair carries identical SHA-256, identical `source:"harness"`, identical `type:"json"` |

Path safety: all 31 manifest paths are relative, normalized, and inside the run directory (`redacted/`). No absolute paths, no `..` traversal, no symlinks anywhere in either run directory.

**Why each duplicate was emitted (code-traced):** In `run_formal_mode()`, `collect_scenario_identity(scenario)` is called **twice** per scenario — once as a placeholder before services start (line 2581) and once with the real `correlation_id`/`workflow_run_id` after the BrowserResult is loaded (line 2625). Each call appends the same artifact name (`scenarios/{scenario}/identity.json`) to `collector.artifacts`. `_write_manifest()` iterates `self.artifacts` **without deduplication**, so each `identity.json` name appears twice in the artifacts list. The second `collect_json` write overwrites the placeholder on disk, so the single physical file carries the enriched content.

**Determinism:** Yes. The formal flow always makes exactly two `collect_scenario_identity` calls per scenario; the duplicate is a deterministic harness emission, not a race or data corruption.

**artifact_count semantics:** `artifact_count = len(artifacts_list)` — **list entries**, not unique identities. This is explicitly the contract: the formal test asserts `artifact_count == len(artifacts)` (`test_acceptance_harness_formal.py:2381`). No contract rule requires unique manifest paths.

**Consumer impact:** Both duplicate entries reference the identical path with the identical SHA-256, so a verifier cannot ambiguously address or inconsistently verify the artifact — both entries resolve to the same file and the same digest. The authoritative per-file integrity map is `checksums.sha256` (32 unique entries, correct). A naive entry-counter would read 31 vs 29 unique paths, but that affects only presentation/accounting, not integrity, completeness, or reproducibility (re-running the same harness would reproduce the same 31-entry manifest).

**Classification: NON-BLOCKING CONTRACT-COMPLIANT DUPLICATE.**

Supporting evidence: `test_acceptance_harness_formal.py:2381` defines `artifact_count` as list length; no uniqueness requirement exists in the planning contract or the formal test suite; checksums are unique and correct.

**Independent accounting correction:** the Phase C report stated "artifact_count=31 for 30 unique artifact paths." Independent count is **29** unique paths (31 entries − 2 duplicated `identity.json` entries). The report's "30" is a minor arithmetic error; the evidence itself is unambiguous.

---

## 5. Complete Checksum Verification

`redacted/checksums.sha256` — 32 entries, all verified programmatically:

| Check | Result |
|-------|--------|
| Total entries | 32 |
| Unique paths | 32 (no duplicate checksum lines) |
| Missing files | 0 |
| Mismatched hashes | 0 |
| Files outside evidence scope | 0 (all 32 resolve inside `redacted/`) |
| Manifest entries missing from checksums | 0 |
| In checksums but not in manifest | 3: `manifest.json` (itself), `scenarios/*/playwright-results/.last-run.json` (×2) |
| Manifest itself covered | Yes (`ec9dfb20…`) |
| Determinism | Yes (sorted by path) |

Cross-reference: every one of the 31 manifest list entries (29 unique paths) has a matching, correct checksum entry. The 3 checksum entries not listed in the manifest are the manifest itself (expected — it is written after the initial checksum pass) and the two Playwright `.last-run.json` files (collected via `collect_file`, present and checksummed but not enumerated in the manifest list).

**Structural observation (non-blocking):** the 8 files under `browser-results/` (2 BrowserResult JSON, 3 PNG, 3 DOM) are **not** in `checksums.sha256` and **not** in the manifest. This is consistent with the literal contract (`§4.7.2` scopes checksums to *redacted* artifacts; BrowserResults are written directly by the Playwright spec to the run directory, outside the redaction pipeline). They are nonetheless covered at the package level by the aggregate directory hash (`0efe3acb…`, §15). Note that the authoritative identity artifacts (BrowserResult JSON) therefore lack per-file checksum coverage; their integrity is enforced only by the aggregate hash and cross-artifact ID matching. This is a coverage gap worth recording but does not constitute a contract violation.

---

## 6. Python-Version Discrepancy Analysis

`redacted/environment/versions.json` records exactly:

```json
{ "python": "Python 3.14.5", "node": "v22.23.1", "docker": "Docker version 28.3.0, build 38b7060" }
```

**Which command produced the value:** `capture_tool_versions()` (harness line 475) runs `["python3", "--version"]`.

**Which executable that resolved to:** `/usr/bin/python3` → `Python 3.14.5` (system interpreter, confirmed on this host).

**Which interpreter actually invoked `scripts/acceptance_harness.py`:** the repository venv Python 3.12.13. The exact formal command recorded in the Phase C execution report (`/tmp/wp-rec-03h-phase-c-second-formal-execution-report.md` §8) is:

```
/home/toha/Projects/forgemind-ai-operations/.venv/bin/python3.12 scripts/acceptance_harness.py --mode=formal --run-id wp-rec-03h-phase-c-20260813-02
```

The orchestrator therefore ran under **Python 3.12.13** (venv `python3.12`), not system Python 3.14.5. The harness shebang (`#!/usr/bin/env python3`) is **irrelevant** when the script is invoked through an explicit absolute interpreter path; the Phase C report additionally records `sys.executable = /home/toha/Projects/forgemind-ai-operations/.venv/bin/python3.12` (its §6). The interpreter is established from the recorded invocation, not inferred from what the script could run under.

**Which interpreter ran the application subprocesses:** repository venv Python 3.12.13 — the harness explicitly invokes `[VENV_BIN/"python3.12", "-m", "app.seed.generator.main"]` (line 2102) and `[VENV_BIN/"python3.12", "-m", "arq", "app.worker.WorkerSettings"]` (line 2149), plus `VENV_BIN/alembic`, `VENV_BIN/uvicorn`, `VENV_BIN/pytest`. The pytest stdout headers in both `scenarios/*/tests/backend.json` read: `platform linux -- Python 3.12.13 … -- /home/toha/Projects/forgemind-ai-operations/.venv/bin/python3.12`.

**Do logs/shebangs independently prove 3.12.13?** Yes — the `backend.json`/`playwright.json` artifacts embed the pytest runner header naming `Python 3.12.13` and the venv path; the subprocess command arrays name `python3.12` explicitly. The worker log confirms ARQ startup under that venv.

**Did any component run under 3.14.5?** No. The harness orchestrator and every application subprocess (backend tests, Alembic, Uvicorn, ARQ worker, seed) all ran under venv Python 3.12.13. The only 3.14.5 value anywhere in the package is the `versions.json` system-tool probe string itself.

**What does `versions.json` claim?** Per `§4.7.1` category 2, it is a **system tool-version probe** (`python --version`), not a claim about the interpreter that invoked the harness. The recorded value (`Python 3.14.5`) is the system `python3` version, produced by the separate `python3 --version` subprocess — a true statement about the system tool, but it is **not** the harness/application runtime interpreter (which was 3.12.13).

**Materially false?** No. The value is a true statement about the system tool version, correctly scoped by the explicit version-capture contract. It is not mislabeled within the contract: the contract asks for the system tool version, not the run interpreter.

**Reproducibility without external narrative:** Partially. The application runtime interpreter (3.12.13) is independently evidenced *inside* the package by the pytest headers and subprocess command arrays. The literal formal command and its exit code are **not** recorded directly inside the finalized evidence package — they are recorded in the Phase C execution report (`/tmp/wp-rec-03h-phase-c-second-formal-execution-report.md` §8–§9) and its console transcript (`/tmp/wp-rec-03h-phase-c-formal-02-console.log`, `HARNESS_EXIT_CODE=0`). This is an evidence-package limitation, not an inconsistency: the in-package artifacts (pytest headers naming `Python 3.12.13`) independently prove the runtime interpreter without relying on external narrative.

**Classification: ACCURATE ACCORDING TO THE EXPLICIT VERSION-CAPTURE CONTRACT.** `versions.json` accurately records the system-tool probe (`Python 3.14.5`), not the interpreter that invoked the harness (venv `Python 3.12.13`). The discrepancy is not a provenance defect, not a mislabel, and not materially false — it is two different facts (system-tool version vs. application-runtime version), each correctly captured in its designated location.

---

## 7. BrowserResult Schema and Identity Review

**Schema:** both BrowserResult JSON files parse and contain exactly the fields of `class BrowserResult` (harness line 222), plus the AT-013-specific `pre_retry_snapshot`/`post_retry_snapshot`. No missing or extra required fields; no silently defaulted values.

**AT-008 (`browser-results/AT008_INVALID_OUTPUT.json`):**
- run ID `wp-rec-03h-phase-c-20260813-02` ✓; scenario `AT008_INVALID_OUTPUT` ✓
- `product_workflow_run_id = e4a0bf34-772f-41fb-b95a-3ca9a1c34314` — matches `workflow_run_state.json`, `workflow_steps.json`, identity.json ✓
- `correlation_id = 6cc5ac11-3ea5-4bd9-ae57-c16495a5ad26` — matches DB `correlation_id` and worker-log transition lines ✓
- `final_state = FAILED_VALIDATION` ✓; `dispatch_generation = 0` ✓
- screenshot + DOM paths exist and resolve inside `browser-results/` ✓
- atomic write (temp+fsync+rename) ✓; deterministic naming ✓; no overwrite of AT-013 files ✓

**AT-013 (`browser-results/AT013_OUTAGE_UNTIL_RETRY.json`):**
- `product_workflow_run_id = 593f0711-68e9-4cf8-8bee-a06860b1bb1b` — same in pre- and post-retry snapshots, DB state, steps, recommendations ✓
- `correlation_id = 89b0fa69-39e2-4486-902f-0c559062f6df` — same across snapshots and DB ✓
- pre-retry snapshot: generation 0, state `FAILED_PROVIDER`; post-retry snapshot: generation 1, state `COMPLETED`; **same run ID** in both ✓
- dispatch generation 0 → 1 (explicit retry, asserted in spec as `post == pre + 1`) ✓
- final recommendation belongs to post-retry generation: `recommendations.json` shows recommendation `bd7200e5…` with `run_id = 593f0711…` and `created_at = 20:15:49` (during generation-1 execution window) ✓
- identities coherent across API data, BrowserResult, logs, screenshots, and DOM ✓

**Referenced artifact hashes:** screenshots/DOM are not in `checksums.sha256` (see §5). They were independently verified present and structurally valid (§8).

---

## 8. Independent Screenshot and DOM Findings

Independent structural verification (PNG signature + IHDR dimension parse; pixel-channel statistics) plus visual inspection (vision model):

| Artifact | Dimensions | Validity | Visual interpretation | DOM corroboration |
|----------|-----------|----------|----------------------|-------------------|
| `AT008_INVALID_OUTPUT-final-state.png` | 1280×720 | Valid PNG, non-blank (256 distinct R-values, high variance) | Workflow run detail page; `FAILED_VALIDATION` badge; Error card `VALIDATION_FAILED` / `StructuredOutputValidationError`; Steps card shows `provider_call #0 completed` (validation step and "No recommendation" are below the viewport cut) | DOM fully corroborates: `provider_call completed`, `validation #1 failed VALIDATION_FAILED`, and "No recommendation" present |
| `AT013_OUTAGE_UNTIL_RETRY-pre-retry.png` | 1280×720 | Valid PNG, non-blank | Supply risk detail RISK-001 CRITICAL shortage 8; `Workflow state: FAILED_PROVIDER`; visible `Retry` button; Evidence & Calculation (Required 20, Available 12, Confirmed early/late 0) | DOM corroborates (RISK-001, FAILED_PROVIDER, Retry, evidence grid) |
| `AT013_OUTAGE_UNTIL_RETRY-post-retry.png` | 1280×720 | Valid PNG, non-blank | Same RISK-001 CRITICAL shortage 8; `Workflow state: COMPLETED` (no longer FAILED_PROVIDER); Evidence & Calculation present | DOM corroborates (COMPLETED) |

No loading spinners, no error overlays, no auth/redirect/blank/stale states, no unrelated content, no sensitive or prohibited information in any screenshot or DOM snapshot. Screenshot and DOM are captured at the same point in each scenario (DOM `innerText` read immediately after the screenshot in the same page state).

**Binary-review comparison:** the manifest's `binary_reviews` carries exactly three entries (`final-state`, `pre-retry`, `post-retry`), each with `reviewed:true`, `method:"signature_and_dom_scan"`, `safe:true`, and `findings:[]` (a present list). This matches the independent findings. Fail-closed behavior is implemented: `review_binary_artifact` sets `safe = (len(findings) == 0)` and the harness raises if `safe` is false (line 2731–2736); `review_screenshot` raises on any secret pattern in the paired DOM. Structurally valid review entries are corroborated by the screenshots themselves proving the required states.

---

## 9. AT-008 Criterion-by-Criterion Assessment

Authoritative criteria (`04_ACCEPTANCE_TESTS.md` AT-008 + task-specific checks):

| # | Criterion | Evidence | Classification |
|---|-----------|----------|----------------|
| 1 | Model returns invalid structure | `InvalidOutputProvider` returns `{"invalid":"data"}` (acceptance_scenarios.py:126); worker log `acceptance_scenario.at008.invalid_output` + `structured_output.validation.failed reason=INVALID_SCHEMA error_count=6` | EVIDENCED |
| 2 | Run reaches `FAILED_VALIDATION` | `workflow_run_state.json` state `FAILED_VALIDATION`; worker log transition `AWAITING_VALIDATION → FAILED_VALIDATION`; BrowserResult `final_state`; DOM badge | EVIDENCED |
| 3 | Error code `VALIDATION_FAILED` | `workflow_run_state.error_code = VALIDATION_FAILED`; `workflow_steps` validation step `error_code VALIDATION_FAILED`; DOM Error card | EVIDENCED |
| 4 | Generation remains 0 | `workflow_run_state.dispatch_generation = 0`; BrowserResult `dispatch_generation = 0` | EVIDENCED |
| 5 | No recommendation produced | `recommendations.json` `count = 0`; DOM "No recommendation" | EVIDENCED |
| 6 | Write actions not created | `recommendations.json` count 0 (no recommendation ⇒ no write path); `controlled_write_check.json` `procurement_tasks_exist: false` | EVIDENCED |
| 7 | Error visible in trace | `workflow_steps` validation step `failed`; DOM Error card + step trace; screenshot Error card | EVIDENCED |
| 8 | UI evidence corresponds to same run/backend state | DOM run ID `e4a0bf34…` matches DB/API/BrowserResult | EVIDENCED |

No criterion CONTRADICTED, NOT EVIDENCED, or NOT APPLICABLE. This is a semantic assessment only — it does not declare AT-008 formally PASS.

---

## 10. AT-013 Criterion-by-Criterion Assessment

| # | Criterion | Evidence | Classification |
|---|-----------|----------|----------------|
| 1 | AI endpoint unavailable (initial) | `OutageUntilRetryProvider` raises `TransientChatProviderError` on generation 0; worker log `acceptance_scenario.at013.dispatch dispatch_generation=0` ×4 + `retry.attempt` attempts 1–4 `outcome=exhausted` | EVIDENCED |
| 2 | Risk engine result remains available | backend test `test_at013_risk_available_during_outage PASSED`; worker log `workflow.vertical.risk_calculated risk_count=3`; UI DOM/screenshot show RISK-001 CRITICAL shortage 8 | EVIDENCED (see Finding F3) |
| 3 | Workflow shows failed AI step | `workflow_steps` seq 0 `provider_call` `failed` `PROVIDER_TRANSIENT`; UI `Workflow state: FAILED_PROVIDER` | EVIDENCED |
| 4 | UI does not hang | Playwright test passed within timeouts (pre-retry FAILED_PROVIDER then retry then COMPLETED); responsive screenshots | EVIDENCED |
| 5 | User can retry | Retry button visible (screenshot); `retryButton.click()`; worker log `workflow_retry` job `…:1:workflow_retry` | EVIDENCED |
| 6 | Same run ID preserved across retry | pre/post snapshots and DB all `593f0711-68e9-4cf8-8bee-a06860b1bb1b` | EVIDENCED |
| 7 | Generation 0 → 1 | pre snapshot gen 0, post snapshot gen 1, DB `dispatch_generation = 1` | EVIDENCED |
| 8 | Worker-side generation guard | worker log `workflow.run.transition_generation_guarded … dispatch_generation=1`; `workflow.py` atomic retry transition; `vertical.py:245` injects `dispatch_generation` into provider context | EVIDENCED |
| 9 | Completed post-retry state | DB `state = COMPLETED`; BrowserResult `final_state = COMPLETED`; UI `Workflow state: COMPLETED` | EVIDENCED |
| 10 | Resulting recommendation | `recommendations.json` `count = 1` (`bd7200e5…`, `run_id = 593f0711…`) | EVIDENCED |

No criterion CONTRADICTED, NOT EVIDENCED, or NOT APPLICABLE. This is a semantic assessment only — it does not declare AT-013 formally PASS.

---

## 11. Cross-Artifact Identity Table

| Field | AT-008 value | AT-013 value (pre → post) | Consistency |
|-------|--------------|---------------------------|-------------|
| Run ID | `wp-rec-03h-phase-c-20260813-02` | `wp-rec-03h-phase-c-20260813-02` | ✓ (manifest, identity, BrowserResult) |
| Scenario | `AT008_INVALID_OUTPUT` | `AT013_OUTAGE_UNTIL_RETRY` | ✓ |
| Workflow run ID | `e4a0bf34-772f-41fb-b95a-3ca9a1c34314` | `593f0711-68e9-4cf8-8bee-a06860b1bb1b` (same pre/post) | ✓ across DB/steps/recommendation/BrowserResult/UI |
| Correlation ID | `6cc5ac11-3ea5-4bd9-ae57-c16495a5ad26` | `89b0fa69-39e2-4486-902f-0c559062f6df` (same pre/post) | ✓ across DB/BrowserResult/worker log |
| Final state | `FAILED_VALIDATION` | `FAILED_PROVIDER` → `COMPLETED` | ✓ |
| Error code | `VALIDATION_FAILED` | `PROVIDER_TRANSIENT` (gen 0) → none (gen 1) | ✓ |
| Dispatch generation | 0 | 0 → 1 | ✓ (DB + BrowserResult) |
| Recommendation | 0 rows | 0 → 1 row (`bd7200e5…`) | ✓ |
| Screenshot path | `…-final-state.png` | `…-pre-retry.png`, `…-post-retry.png` | ✓ exist |
| DOM path | `…-final-state.dom.txt` | `…-pre-retry.dom.txt`, `…-post-retry.dom.txt` | ✓ exist |
| BrowserResult path | `browser-results/AT008_INVALID_OUTPUT.json` | `browser-results/AT013_OUTAGE_UNTIL_RETRY.json` | ✓ |
| Checksum coverage | redacted artifacts ✓ (screenshots/DOM outside redacted scope) | same | See §5 |

**Distinctions:**
- **Directly recorded facts:** all DB/API/log values above are verbatim in the evidence files.
- **Corroborated by multiple artifacts:** workflow run IDs and correlation IDs appear in ≥3 independent artifacts each (DB snapshot, workflow steps, worker log, BrowserResult, identity).
- **Inferred from code:** exit code 0 (structural inference from finalized package + absent `raw/`); formal-mode invocation (structural inference from package shape); the harness-probe defects (F3/F4) are inferred from code vs. recorded `unavailable` values.
- **Present only in Phase C report (not independently re-verified):** the literal "exit code 0" statement and the "invoked exactly once" narrative — both corroborated but not independently captured in-package.

Two minor identity-field notes (non-blocking):
- `identity.json.dispatch_generation` is `null` for AT-008 (harness only populates it for AT-013) even though the true value is 0 — the authoritative 0 lives in `workflow_run_state.json` and BrowserResult.
- For AT-013, `identity.json.dispatch_generation = 0` records the **initial** (pre-retry) generation; the final generation 1 is in `workflow_run_state.json` and BrowserResult. Not a contradiction; a labeling nuance.

---

## 12. Binary-Review Assessment

Three binary-review entries, all structurally valid: `artifact` name, `reviewed:true`, `method:"signature_and_dom_scan"`, `safe:true`, `findings:[]` (list present). Fail-closed handling confirmed in code (raise on `safe:false`, raise on DOM secret patterns). Independent visual inspection confirms the screenshots prove the required states and contain no prohibited content. **The `safe:true` values are corroborated, not merely trusted.**

---

## 13. Failed-Run Isolation and Preservation

- `-02` contains **no reference** to `-01` (no shared paths, run IDs, correlation IDs, or timestamps).
- `-01` remains unchanged: 71 files, 300481 bytes, aggregate hash `e04c7f9d…a981`, manifest-less, retains both `raw/` (31) and `redacted/` (32) plus 8 `browser-results/` files.
- No symlinks, no absolute/traversal paths, no shared files between the two runs.
- No third formal-run directory (`-03` or otherwise) exists.
- `-01` remains non-acceptable and permanently non-reusable (confirmed non-final, no manifest).

---

## 14. Overall Evidence Disposition

The candidate run `-02` is **complete, internally consistent, traceable to `686739fd…`, and semantically sufficient** for AT-008 and AT-013. Neither of the two known observations is blocking:

- **Duplicate `identity.json` manifest entries** → NON-BLOCKING CONTRACT-COMPLIANT DUPLICATE (§4): deterministic harness emission; the formal contract explicitly ties `artifact_count` to list length; checksums are unique and correct; no ambiguous addressing.
- **Python 3.14.5 in `versions.json`** → ACCURATE ACCORDING TO THE EXPLICIT VERSION-CAPTURE CONTRACT (§6): `versions.json` records the system-tool probe (`python3 --version`), not the run interpreter. The harness orchestrator and all application subprocesses ran under venv Python 3.12.13 (proven by the recorded formal command and in-package pytest headers).

Additional non-blocking findings recorded for transparency (do not change the disposition):
- **F3:** `api/risk_api.json` records `unavailable 404` for both scenarios because `query_risk_api()` targets `/api/v1/risks` instead of the actual `/api/v1/production-plans/{plan_code}/risks` (backend router). Risk availability is independently proven (backend test pass + worker log `risk_count=3` + UI). Harness-probe defect; semantic criterion still evidenced.
- **F4:** `api/dispatch_generation.json` records `unavailable 401` for both scenarios because `query_workflow_run_api()` issues an unauthenticated `urllib` call to an auth-required endpoint. The authoritative `dispatch_generation` is captured via the DB and the authenticated Playwright API context. Harness-probe defect; value still evidenced.
- **F5:** `browser-results/` (8 files including the authoritative BrowserResult JSON) lack per-file checksum coverage (outside the redacted scope per `§4.7.2`); integrity enforced only by the aggregate directory hash and cross-artifact ID matching.
- **F6:** `identity.json.dispatch_generation = null` for AT-008 (true value 0 captured elsewhere).
- **F7:** Phase C report "30 unique paths" is arithmetically 29 unique.
- **F8:** `manifest.json` has no explicit `schema_version` field (BrowserResult does).

None of F3–F8 compromises completeness, integrity, provenance, semantic sufficiency, or contract compliance. F3/F4 are the most material (two evidence artifacts whose recorded content — "unavailable" — does not reflect the true system state), but the authoritative values are captured by independent artifacts, so the acceptance criteria remain fully evidenced. They should be logged as future harness corrections, not Phase D blockers.

**Primary verdict: run `-02` is ACCEPTABLE FOR A SEPARATE PRODUCT OWNER PHASE D ACCEPTANCE DECLARATION.**

This verdict does not declare AT-008, AT-013, or Phase 5 accepted.

---

## 15. Protected-Audit and Evidence Fingerprints Before and After

| Item | Before | After | Unchanged |
|------|--------|-------|-----------|
| Protected audit SHA-256 | `639a2529…e89657` | `639a2529…e89657` | ✓ |
| Protected audit lines / bytes | 437 / 29036 | 437 / 29036 | ✓ |
| Run `-01` files / bytes / hash | 71 / 300481 / `e04c7f9d…a981` | 71 / 300481 / `e04c7f9d…a981` | ✓ |
| Run `-02` files / bytes / hash | 41 / 272956 / `0efe3acb…88dd` | 41 / 272956 / `0efe3acb…88dd` | ✓ |

Aggregate method (identical before and after): `cd <run-dir> && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum`.

---

## 16. Confirmation of No Evidence or Project Mutation

- Branch `main` and HEAD unchanged (`686739fd…`); `origin/main` and `local main` not updated.
- Staging empty; no tracked changes; only untracked entry is the protected audit.
- No evidence file touched, rewritten, reformatted, or re-hashed.
- No new formal-run directory created.
- No repository source, commit, branch, tag, or remote-tracking state modified (only read-only `git ls-remote` and `gh pr view` metadata reads).
- No GitHub metadata changed; no review or comment posted; no workflow managed.
- No infrastructure started; no container/process launched.
- Formal mode NOT invoked; no acceptance declared.

---

## 17. Lifecycle-Boundary Confirmation

Consistent with the authoritative lifecycle (`docs/planning/wp_rec_03h_acceptance_harness.md` §0, blob `3bd7c9a962caa476061d36080b7f5c325fa8c007` at commit `686739fd…`): PR #84 merged; PR #85 merged at `686739fd…`; first Phase C run `-01` failed and is permanently preserved non-final/non-acceptable/non-reusable; second Phase C run `-02` executed once, finalized, exited cleanly — **Phase C execution is complete**; the independent substantive evidence review supporting Phase D is now complete (this report); the Product Owner Phase D acceptance declaration **has not yet occurred**; AT-008 formal PASS **not yet declared**; AT-013 formal PASS **not yet declared**; Phase 5 acceptance **not yet declared**; **Phase D is therefore not fully complete** (its acceptance-declaration component is outstanding); Phase E documentation lifecycle reconciliation **has not begun and remains unauthorized**.

---

## PRIMARY VERDICT

WP-REC-03H PHASE D EVIDENCE REVIEW PASSED — RUN WP-REC-03H-PHASE-C-20260813-02 IS ACCEPTABLE FOR A SEPARATE PRODUCT OWNER PHASE D ACCEPTANCE DECLARATION

**Recommended next action (only):**

Issue one explicit Product Owner Phase D acceptance declaration for AT-008, AT-013, and Phase 5 using unchanged run `wp-rec-03h-phase-c-20260813-02`; preserve failed run `wp-rec-03h-phase-c-20260813-01` unchanged, and do not rerun formal mode, modify evidence, remediate findings F3–F8, update project documentation, or begin Phase E documentation lifecycle reconciliation in the same decision task.
