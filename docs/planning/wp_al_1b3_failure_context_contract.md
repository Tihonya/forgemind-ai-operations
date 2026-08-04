# WP-AL-1B3 — Structured Failure Context Contract

## 1. Status and ownership

- Status: **MERGED — PR #45, merge commit d1561ac1f2e74b98a4a9d4bc25381cd417be3ad9, 2026-08-04**
- Owner: ForgeMind AI Operations
- Branch: `chore/agent-loop-failure-context`
- Base: `origin/main` @ `10b0e1bf8a0ba4ced62cec585cb291f3b4c9697b`
- Pull Request: #45
- Model: qwen3.7-plus (deterministic Python; no LLM invocation)
- Depends on: WP-AL-1B2 (verify-story.sh canonical gate wiring)
- Precedes: WP-AL-1C (review/repair agent integration)
- Pull Request: #45

## 2. Background

WP-AL-1A delivered the cycle passport and workspace identity guard.
WP-AL-1B1 delivered the project configuration loader.
WP-AL-1B2 delivered the canonical manifest schema v1.0, isolated harness
execution (temp_repo_fixture, scenarios A-O), and canonical gate wiring
(scope/json/yaml/targeted_tests/lint/secrets/git_diff_check).

Merged as PR #44, commit `10b0e1bf8a0ba4ced62cec585cb291f3b4c9697b`.

The verification phase now produces per-gate logs and structured verdicts,
but no single structured object is emitted to downstream agents describing
what failed, why, and where. Reviewer and repair agents (future WP-AL-1C)
need a stable, schema-valid contract as input.

## 3. Problem statement

Downstream consumers (reviewer, repair, reporter) currently have no
machine-readable, schema-versioned failure summary. Without one:

- repair agents must re-parse pytest XML, scope logs, lint output ad-hoc;
- reviewer cannot deterministically enumerate failing gates;
- reporter cannot correlate gate verdicts with candidate identity;
- partial collector failure is silently masked as "empty context".

A structured failure-context contract closes this gap deterministically.

## 4. Objective

Define and implement a versioned failure-context schema v1.0 with a
deterministic collector that reads verify-story.sh artifacts and emits
`$RUN_DIR/reports/failure-context.json` for every run (pass, fail, or
partial infrastructure failure when source artifacts are sufficient).

## 5. Architecture and data flow

```
verify-story.sh
  └─ produces: $RUN_DIR/verify/{scope,tests,lint,secrets,
                                json_*,yaml_*,diff_check}.log
               $RUN_DIR/verify/pytest-report.xml
               $RUN_DIR/reports/verify-result.json
                      │
                      ▼
failure_context.py (collector)
                      │
                      ▼
$RUN_DIR/reports/failure-context.json  ──► reviewer / repair / reporter
```

The collector is a pure function over the artifact directory. It has no
network access, no LLM invocation, no shell interpolation. It reads only
the artifacts verify-story.sh already wrote.

## 6. Failure-context schema summary

Schema document: `.agent-loop/failure-context/SCHEMA.md` (separate from
the story-manifest schema at `.agent-loop/manifests/SCHEMA.md`).

Top-level fields (v1.0):

- `schema_version`: `"1.0"`
- `project_id`: `"forgemind"`
- `run_id`: string (matches passport/run metadata)
- `story_id`: string
- `generated_at`: ISO-8601 timestamp
- `collection_status`: `"complete"` | `"partial"` | `"failed"`
- `collection_errors`: array of structured entries (see §9)
- `candidate_identity`: object (see §8)
- `gate_verdicts`: object keyed by canonical gate id
  (scope | json_syntax | yaml_syntax | targeted_tests | lint |
  secrets | git_diff_check); each entry:
    - `status`: `PASS` | `FAIL` | `SKIP` | `ERROR` | `DISABLED`
    - `summary`: bounded, sanitized string
    - `source_artifacts`: array of artifact file refs (relative to $RUN_DIR)
    - `diagnostics`: array of structured diagnostic objects (see §7)
- `failing_gates`: array of canonical gate ids (deterministic order)
- `repair_guidance`: array of strings (pass-through from manifest)
- `redaction_applied`: boolean
- `redaction_count`: integer

The canonical manifest schema (`SCHEMA.md` v1.0) is NOT modified. At most
a short cross-reference is added pointing to the separate failure-context
schema document.

## 7. Sanitization / redaction policy

Structured diagnostics first; bounded excerpts only after sanitization.

Mandatory redaction rules (applied before any field is written to the
output):

1. No raw secret values, ever. Secrets-gate evidence is limited to
   `rule_id`, `relative_file_path`, `line_number`, `classification/status`.
2. No environment dumps.
3. No command-line arguments containing credentials.
4. No raw `Authorization` headers or cookie values.
5. No full URLs with query parameters (strip query string).
6. No arbitrary binary or base64 content.
7. All text is UTF-8 normalized; invalid bytes are replaced with U+FFFD.
8. Excerpts are bounded by configurable line and byte limits
   (defaults: 50 lines, 4096 bytes per excerpt).
9. Truncation marker: `"... [truncated: N bytes omitted, source: <path>]"`.
10. Each diagnostic carries `source_artifact` reference and a
    `redaction_applied` boolean plus `redaction_count` integer.

Sanitization is implemented as a single Python module
(`failure_context.py`) with dedicated unit tests covering each rule.

## 8. Candidate identity semantics

The `candidate_identity` object:

- `base_commit`: required, concrete 40-character lowercase hex SHA.
  Symbolic refs (`HEAD`, `main`, `origin/main`, `refs/...`) are rejected.
- `candidate_commit`: concrete 40-character lowercase hex SHA when the
  candidate is committed; `null` when verification targets working-tree
  changes only.
- `candidate_state`: `"committed"` | `"working_tree"`.
- `candidate_diff_digest`: deterministic digest of the normalized candidate
  diff inventory.

Algorithm for `candidate_diff_digest`:

1. Enumerate the candidate-diff file list via the existing harness
   primitive (`list_candidate_diff_files` against `base_commit`),
   producing a sorted list of repo-relative paths.
2. For each path, record `(path, size_bytes, sha256_of_content)` for
   tracked-and-committed files; for untracked files, the same tuple is
   recorded from the working-tree content.
3. Sort the tuples lexicographically by `path`.
4. Serialize as newline-delimited lines `path\tsize\tsha256`
   (UTF-8, LF only).
5. Compute `sha256` over the serialized buffer.
6. The resulting 64-character lowercase hex digest is the value.

The algorithm is documented verbatim in the schema and tested for
determinism (same input → same digest) and sensitivity (any content or
path change → different digest).

## 9. Collector failure semantics

Fail-closed infrastructure semantics:

- If verification gates complete but the collector cannot produce a
  schema-valid `failure-context.json`, the overall run becomes
  `INFRASTRUCTURE_ERROR` with exit code `2`.
- Existing gate verdicts in `$RUN_DIR/reports/verify-result.json` and
  the per-gate logs remain preserved and unmodified.
- Collector failure must not be reported as `VERIFICATION_FAILED` or
  `REVIEW_REJECTED`.
- `collection_status` is `"failed"`; `collection_errors` contains at
  least one structured entry with `artifact_id`, `error_code`,
  `safe_summary`.

Recursive-failure guard: if the collector itself fails mid-write, the
existing small safe infrastructure-error artifact (written by the
established `atomic_write` mechanism) is emitted. The collector is never
invoked recursively from its own error path.

Pass runs: `failure-context.json` is emitted with
`collection_status: "complete"` and `failing_gates: []`.

Partial infrastructure failure (when enough source artifacts exist to
produce a schema-valid partial context): `collection_status: "partial"`,
`collection_errors` enumerates the missing/malformed artifacts, and
`failing_gates` reflects whatever verdicts could be read.

## 10. Functional scope

In scope:

- `.agent-loop/failure-context/SCHEMA.md` (v1.0 contract document).
- `scripts/agent-loop/lib/failure_context.py` (collector module).
- Wire the collector into `verify-story.sh` at the end of the gate loop,
  after all gate logs and `verify-result.json` are written.
- Collector fail-closed exit-code 2 handling is in `verify-story.sh` (collector
  failure naturally propagates through existing orchestrator exit semantics).
- Unit tests: `scripts/agent-loop/tests/test_failure_context.py`.
- Harness scenario T: extend `run_harness_scenarios.sh` to validate a
  failed verification run emits a safe, schema-valid failure-context
  artifact.
- README status update.

**Collector integration point:**

The collector is invoked by `verify-story.sh` after all gate artifacts and
`verify-result.json` exist. It runs in the post-gate phase, not in
`run-story.sh`. This ensures:

- Gate evidence is available before collection;
- Fail-closed exit 2 from collector failure is produced by verify-story.sh
  and naturally propagated by the existing orchestrator;
- `run-story.sh` remains outside approved implementation scope (unchanged).

## 11. Allowed paths

- `docs/planning/wp_al_1b3_failure_context_contract.md` (this file)
- `.agent-loop/failure-context/SCHEMA.md` (NEW, created during impl)
- `.agent-loop/manifests/SCHEMA.md` (cross-reference append only)
- `scripts/agent-loop/lib/failure_context.py` (NEW)
- `scripts/agent-loop/verify-story.sh` (emit call at end of gate loop)
- `scripts/agent-loop/tests/test_failure_context.py` (NEW)
- `scripts/agent-loop/tests/run_harness_scenarios.sh` (scenario T)
- `scripts/agent-loop/tests/lib/temp_repo_fixture.py` (find-run subcommand for
  Scenario T run-directory discovery)
- `scripts/agent-loop/tests/lib/scenario_helpers.sh` (helper if needed)
- `scripts/agent-loop/README.md` (status update)

**temp_repo_fixture.py find-run subcommand justification:**

Scenario T must locate the most recent run directory inside the isolated
repository's artifacts folder to validate the emitted `failure-context.json`.
The `find-run` subcommand provides deterministic, narrow run-directory
discovery without mutating the repository or introducing external dependencies.
It is restricted to Scenario T's isolated temp repository and does not operate
on the real infrastructure worktree.

## 12. Forbidden paths

- Canonical manifest schema v1.0 core field table (no changes to
  `required_gates`, `allowed_paths`, etc. semantics).
- `.agent-loop/gates.json` (no policy changes).
- Gate implementations in `lib/{scope.sh,tests.sh,harness.py,
  manifest_loader.py,config_loader.py,guard.sh,passport.py}`.
- `backend/`, `frontend/`, `docker*`, `forgemind_project_source_of_truth/`.
- Any reviewer/repair/LLM invocation code.
- `.env`, `.env.*`, `*.pem`, `*.key`.

## 13. Explicit non-goals

- No LLM invocation.
- No reviewer agent integration (WP-AL-1C).
- No repair agent integration (WP-AL-1C).
- No implementer (Ralph/OpenCode) invocation.
- No diff-based targeted-test selection (separate future WP).
- No run lifecycle / state machine / resumability.
- No concurrency support.
- No prompt design.
- No change to manifest schema v1.0 field table.
- No change to gates.json policy.
- No change to backend or product code.

## 14. Acceptance criteria

AC-1  A separate failure-context schema v1.0 is documented at
      `.agent-loop/failure-context/SCHEMA.md` during implementation.
      `.agent-loop/manifests/SCHEMA.md` carries at most a short
      cross-reference; its canonical manifest field table and schema v1.0
      contract remain unchanged.

AC-2  A schema-valid `failure-context.json` is produced after successful
      and failed verification runs.

AC-3  All seven canonical gate verdicts are represented with stable IDs
      (`scope`, `json_syntax`, `yaml_syntax`, `targeted_tests`, `lint`,
      `secrets`, `git_diff_check`) and structured statuses
      (`PASS`/`FAIL`/`SKIP`/`ERROR`/`DISABLED`).

AC-4  `base_commit`, `candidate_commit`, `candidate_state`,
      `candidate_diff_digest` semantics are deterministic and tested for
      stability and sensitivity.

AC-5  No raw secret value or unsafe diagnostic payload is embedded in the
      output (rule-based redaction tests cover each rule in §7).

AC-6  All excerpts are sanitized, UTF-8 normalized, and bounded by
      configurable line and byte limits (defaults: 50 lines / 4096 bytes
      per excerpt). Truncation marker and source artifact reference are
      present.

AC-7  Missing or malformed source artifacts produce explicit
      `partial` / `failed` collection metadata; no silent empty success.

AC-8  Collector failure produces `INFRASTRUCTURE_ERROR` exit code 2 while
      preserving already-produced gate evidence in
      `$RUN_DIR/reports/verify-result.json` and per-gate logs. Collector
      failure is never reported as `VERIFICATION_FAILED` or
      `REVIEW_REJECTED`.

AC-9  Existing verification verdict and exit-code semantics remain
      unchanged when the collector succeeds (regression parity with
      WP-AL-1B2 behavior).

AC-10 Unit tests cover:
      - successful run
      - one failed gate
      - multiple failed gates
      - working-tree candidate
      - committed candidate
      - missing artifact
      - malformed artifact
      - truncation
      - redaction (each §7 rule)
      - Unicode handling
      - path with spaces
      - deterministic digest (same input → same digest)
      - digest sensitivity (any change → different digest)
      - collector infrastructure failure

AC-11 Harness Scenario T validates a failed verification run emits a safe,
      schema-valid failure-context artifact.

AC-12 Harness scenarios A through T pass 20/20 and all WP-AL-1B2
      regression suites remain green.

AC-13 No change to:
      - manifest schema v1.0;
      - gates.json policy;
      - gate implementations;
      - reviewer/repair/LLM invocation;
      - backend or product code.

## 15. Test matrix

Unit tests (`scripts/agent-loop/tests/test_failure_context.py`):

| ID  | Case                                 | Expected                       |
|-----|--------------------------------------|--------------------------------|
| U01 | Successful run                       | collection_status=complete     |
| U02 | One failed gate                      | failing_gates has one entry    |
| U03 | Multiple failed gates                | failing_gates has N entries    |
| U04 | Working-tree candidate               | candidate_commit=null,         |
|     |                                      | state=working_tree             |
| U05 | Committed candidate                  | candidate_commit=SHA,          |
|     |                                      | state=committed                |
| U06 | Missing source artifact              | collection_status=partial      |
| U07 | Malformed source artifact            | collection_errors populated    |
| U08 | Excerpt truncation                   | marker + source ref present    |
| U09 | Redaction — secret value             | never embedded                 |
| U10 | Redaction — Authorization header     | stripped                       |
| U11 | Redaction — URL with query params    | query stripped                 |
| U12 | Unicode — invalid UTF-8 bytes        | U+FFFD replacement             |
| U13 | Path with spaces                     | handled without shell split    |
| U14 | Digest determinism                   | same input → same digest       |
| U15 | Digest sensitivity                   | content change → different     |
| U16 | Collector infrastructure failure     | collection_status=failed,      |
|     |                                      | exit 2                         |

Harness scenario T:
- Uses `temp_repo_fixture.py` to build an isolated repo.
- Induces a pytest failure.
- Invokes `verify-story.sh`.
- Asserts `failure-context.json` exists, is schema-valid, contains
  `failing_gates: ["targeted_tests"]`, `collection_status: "complete"`.

Regression (A-O): unchanged; all 15 existing scenarios continue to pass.

Total expected: A through T = 20 scenarios, 20/20 PASS.

## 16. Expected artifacts

- `.agent-loop/failure-context/SCHEMA.md` (v1.0 contract).
- `scripts/agent-loop/lib/failure_context.py` (collector).
- `scripts/agent-loop/tests/test_failure_context.py` (unit tests).
- Scenario T integration in `run_harness_scenarios.sh`.
- Cross-reference in `.agent-loop/manifests/SCHEMA.md` (short).
- `scripts/agent-loop/verify-story.sh` (emit wiring).
- README status update.

## 17. Stop conditions

Stop and report without further action if:

- Any regression in verify-story.sh exit code or overall_status for
  existing scenarios A-O.
- Any secret value appearing in a test fixture output or emitted artifact.
- Any scope violation on a forbidden path.
- Any change to the canonical manifest schema v1.0 field table.
- Any change to gates.json policy.
- Collector failure cannot be contained without recursively invoking the
  collector.
- Digest algorithm cannot be made deterministic and sensitive.

## 18. Branch strategy

- Base: `origin/main` @ `10b0e1b`.
- Branch name: `chore/agent-loop-failure-context` (created in the agent-loop
  worktree via `git checkout -b chore/agent-loop-failure-context origin/main`).
- One PR against `main`.
- Merge commit strategy (not squash) to preserve the WP structure.

## 19. Commit / PR strategy

Conventional commits, one logical change per commit:

1. `docs(agent-loop): add failure-context schema v1.0 contract`
   (SCHEMA.md, cross-reference in manifest SCHEMA.md)
2. `feat(agent-loop): add failure-context collector`
   (lib/failure_context.py, unit tests)
3. `feat(agent-loop): wire failure-context emit into verify-story.sh`
   (verify-story.sh, run-story.sh fail-closed)
4. `test(agent-loop): add harness scenario T for failure context`
   (run_harness_scenarios.sh, scenario_helpers.sh)
5. `docs(agent-loop): record WP-AL-1B3 completion in README`

PR description references this planning document and lists AC-1…AC-13.

## 20. Dependencies and follow-on WPs

Depends on:
- WP-AL-1B2 (canonical gate wiring, artifact layout).

Precedes / unblocks:
- WP-AL-1C — review-agent and repair-agent integration
  (failure-context is their structured input contract).

Orthogonal future WPs (not sequenced by this WP):
- Diff-based targeted-test selection.
- Run lifecycle / state machine / resumability (required before
  concurrency=2).

## 21. Open decisions

None. All architectural decisions referenced in this document are resolved:

- Schema document location: `.agent-loop/failure-context/SCHEMA.md`
  (separate from story-manifest schema).
- Candidate identity semantics: §8.
- Sanitization/redaction policy: §7.
- Collector failure policy: fail-closed `INFRASTRUCTURE_ERROR` exit 2
  (§9), PO-approved.
- Pass/fail emission rules: §9.
- Harness scenario identifier: `T` (P–S are reserved for identity-guard
  scenarios).
- Expected harness total after implementation: 20/20 (A through T).
