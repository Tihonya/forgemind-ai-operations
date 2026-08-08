# SP-0 — Repository Separation Assessment

**Baseline Commit:** 2217e5882767379c1d34d6cc5ba3193caf7c01ad (origin/main)
**Assessment Date:** 2026-08-08
**Revision:** v2 (Manager Review Correction Pass applied)

---

## 1. Safety and Baseline Verification

| Check | Result |
|-------|--------|
| pwd | `/run/media/toha/Virtual Staff/AgentLab/worktrees/forgemind-agent-loop` |
| Git root | matches pwd |
| Current branch | `feature/agent-loop-wp-al-1c6-orchestration-wiring` |
| HEAD | `5001dbd98c5f1fa7882d1db57c166e657e221505` |
| origin/main | `2217e5882767379c1d34d6cc5ba3193caf7c01ad` ✓ matches expected |
| Working tree | `?? docs/reviews/` — protected, non-blocking |

**Baseline status: CONFIRMED.** Proceeding with audit against commit 2217e588.

---

## 2. Current Repository Ownership Map

### 2.1 Top-level structure

| Path | Owner | Classification |
|------|-------|----------------|
| `backend/` | Product | PRODUCT_OWNED |
| `frontend/` | Product | PRODUCT_OWNED |
| `infra/` | Product | PRODUCT_OWNED |
| `forgemind_project_source_of_truth/` | Product | PRODUCT_OWNED |
| `HERMES.md` | Product | PRODUCT_OWNED (Product governance contract) |
| `README.md` | Product (Supply Risk focused) | PRODUCT_OWNED |
| `docker-compose.yml`, `docker-compose.dev.yml` | Product | PRODUCT_OWNED |
| `Makefile` | Product (no agent-loop targets) | PRODUCT_OWNED |
| `.env.example` | Product | PRODUCT_OWNED |
| `.github/workflows/ci-*.yml` | Product (3 workflows, no agent-loop) | PRODUCT_OWNED |
| `.gitignore` | Shared | SHARED (trivial split; both repos need independent copies) |
| `docs/planning/wp_al_*` | Historical | HISTORICAL_ONLY |
| `docs/planning/phase_*`, `wp_3_*`, `wp4*` | Historical | HISTORICAL_ONLY |

### 2.2 `.agent-loop/` — split ownership (CORRECTED)

Not all of `.agent-loop/` is Runtime-owned. Individual artifacts are classified:

| Path | Classification | Rationale |
|------|----------------|-----------|
| `.agent-loop/failure-context/SCHEMA.md` | RUNTIME_OWNED | Generic contract schema |
| `.agent-loop/review/SCHEMA.md` | RUNTIME_OWNED | Generic contract schema |
| `.agent-loop/review-adapter/SCHEMA.md` | RUNTIME_OWNED | Generic adapter schema |
| `.agent-loop/repair/SCHEMA.md` | RUNTIME_OWNED | Generic contract schema |
| `.agent-loop/repair-adapter/SCHEMA.md` | RUNTIME_OWNED | Generic adapter schema |
| `.agent-loop/manifests/SCHEMA.md` | RUNTIME_OWNED (mostly) | Schema is generic; but line 10 hardcodes `project_id` must be `"forgemind"` — requires genericization for external use |
| `.agent-loop/project.json` | **PRODUCT_INTEGRATION_CONFIG** | Contains `project_id: "forgemind"`, ForgeMind-specific paths (`FORGEMIND_MAIN_ROOT`, `AGENTLAB_ROOT/worktrees/forgemind-agent-loop`), and `forgemind_project_source_of_truth/**` in forbidden paths. This is ForgeMind's project configuration consumed by the Runtime. |
| `.agent-loop/gates.json` | **PRODUCT_INTEGRATION_CONFIG** | Contains `project_id: "forgemind"` and encodes Product-specific verification assumptions (ruff/mypy on backend/ tree). This is ForgeMind's gate configuration consumed by the Runtime. |

### 2.3 `scripts/agent-loop/` — split ownership

| Path | Classification | Rationale |
|------|----------------|-----------|
| `scripts/agent-loop/lib/*.py` (contracts, adapters, harness, reporting) | RUNTIME_OWNED | Core runtime implementation logic |
| `scripts/agent-loop/lib/*.sh` (artifacts, env, guard, scope, tests) | RUNTIME_OWNED | Bash helpers |
| `scripts/agent-loop/*.sh` (run-story, verify-story, report-story) | RUNTIME_OWNED | Entry points |
| `scripts/agent-loop/config.sh` | RUNTIME_OWNED | Configuration loader (contains ForgeMind-specific paths — requires genericization) |
| `scripts/agent-loop/templates/story-prd.json` | **FORGEMIND_SPECIFIC** | Contains a ForgeMind Phase-4 story (AT-006). Not a generic template. |
| `scripts/agent-loop/tests/` (34 files) | RUNTIME_OWNED (tests) | Runtime test suite + harness scenarios + test fixtures |
| `scripts/agent-loop/tests/fixtures/manifest-scenario-*.json` | RUNTIME_OWNED (test) | Test fixtures; contain `forgemind_project_source_of_truth/**` in forbidden_paths but this is test data |
| `scripts/agent-loop/README.md` | RUNTIME_OWNED | Runtime documentation |

### 2.4 Key finding: Application-code coupling

```
git grep -l "agent-loop\|agent_loop" 2217e588 -- backend/ frontend/ infra/
→ (EMPTY)
```

**No direct Agent Loop references were found in the inspected Product application paths (`backend/`, `frontend/`, `infra/`) at baseline commit 2217e588.**

This establishes absence of identified application-code coupling from Product to Runtime. However, operational coupling (environment variables, repository-root scripts, CI workflows, documentation, and project configuration) must be assessed separately — see §3.

---

## 3. Cross-Boundary Dependency Matrix

### 3.1 Runtime → Product dependencies

| # | Dependency | Type | Evidence | Blocks Extraction |
|---|------------|------|----------|-------------------|
| D1 | `project_id: "forgemind"` hardcoded | Config | `.agent-loop/project.json:3`, `.agent-loop/gates.json:3`, `.agent-loop/manifests/SCHEMA.md:10,113`, `config_loader.py:34` | YES |
| D2 | `repository_name: "forgemind-agent-loop"` | Config | `.agent-loop/project.json:4` | YES |
| D3 | `FORGEMIND_MAIN_ROOT` env var name | Config | `config_loader.py:38,85,100,470`, `guard.sh:28,37` | YES |
| D4 | `FORGEMIND_AGENT_LOOP_ROOT` env var name | Config | `config_loader.py:39,86,101,471`, `config.sh` | YES |
| D5 | `forgemind_project_source_of_truth/**` in forbidden paths | Config | `.agent-loop/project.json:37`, test fixtures (6 manifests) | YES |
| D6 | Hardcoded worktree path `worktrees/forgemind-agent-loop` | Path assumption | `.agent-loop/project.json:8` | YES |
| D7 | Hardcoded worktree path `worktrees/forgemind-validation` | Path assumption | `.agent-loop/project.json:9` | YES |
| D8 | `AIAutomation` path check | Path assumption | `config.sh:32` | YES |
| D9 | Error message `"Expected path: .../worktrees/forgemind-agent-loop"` | Path assumption | `config.sh:34` | YES |
| D10 | `"Running pytest in backend/"` test output | Path assumption | `lib/tests.sh:47` | NO (cosmetic) |
| D11 | `"cd /path/to/forgemind-agent-loop"` in README | Documentation | `README.md:8,305` | NO (cosmetic) |
| D12 | `PROJECT_ID` defaults to `"forgemind"` | Config | `run-story.sh`, `guard.sh:128,246` | NO (overridable) |
| D13 | Story template references Product phases | Template | `story-prd.json` (Phase-4 story) | YES |
| D14 | Ruff/mypy lint assumptions | Config | `.agent-loop/gates.json` lint gate config, `lib/tests.sh` full-project lint semantics | YES (for external projects with different tooling) |

### 3.2 Product → Runtime dependencies

No direct code imports or function calls from Product application code to Runtime code were found in the inspected paths.

However, the following operational/documentation coupling exists and must be assessed separately:

- `HERMES.md` references Agent Loop execution rules
- Repository-root Makefile may invoke scripts
- CI workflows may reference agent-loop paths
- Documentation cross-references

**The extraction is primarily unidirectional (Runtime contains all coupling), but operational and documentation coupling requires explicit decoupling.**

### 3.3 Shared/ambiguous

| # | Item | Classification | Reason |
|---|------|----------------|--------|
| S1 | `HERMES.md` | PRODUCT_OWNED (primarily) | Currently a Product governance contract. Contains agent execution rules that apply to the Agent Loop, but the document as a whole governs the Product. The Runtime repository needs a new, derived governance document — the existing file cannot simply be split mechanically. |
| S2 | `.gitignore` | SHARED (trivial split) | Standard patterns; both repos need independent copies |
| S3 | CI workflows | PRODUCT_OWNED | No agent-loop references; Runtime needs its own CI |

---

## 4. Extraction Inventory

All pre-parity extraction phases use **COPY** (not MOVE). Files are copied to the Runtime repository while remaining in the ForgeMind repository. MOVE/removal from ForgeMind occurs only after the removal gate (SP-5).

| # | Current Path | Proposed Owner | Migration Action | Risk | Verification Needed |
|---|-------------|----------------|------------------|------|---------------------|
| 1 | `scripts/agent-loop/lib/*.py` (13 files) | Runtime | COPY_TO_RUNTIME | Low | Unit tests pass in new repo |
| 2 | `scripts/agent-loop/lib/*.sh` (5 files) | Runtime | COPY_TO_RUNTIME | Low | bash -n + harness scenarios |
| 3 | `scripts/agent-loop/*.sh` (3 files) | Runtime | COPY_TO_RUNTIME | Low | End-to-end harness |
| 4 | `scripts/agent-loop/templates/story-prd.json` | Product (stays) | **FORGEMIND_SPECIFIC — stays in Product** | N/A | Becomes a ForgeMind story manifest example |
| 5 | `scripts/agent-loop/tests/` (34 files) | Runtime | COPY_TO_RUNTIME (Runtime-owned tests only) | Medium | SP-0B must determine exact Runtime test inventory |
| 6 | `scripts/agent-loop/README.md` | Runtime | COPY_TO_RUNTIME | Low | Documentation accurate |
| 7 | `scripts/agent-loop/config.sh` | Runtime | **SP-1A:** COPY_UNCHANGED with provenance; **SP-2:** GENERICIZE_IN_RUNTIME (remove ForgeMind-specific paths) | Medium | SP-1A: blob equivalence verified; SP-2: works without ForgeMind paths |
| 8 | `.agent-loop/project.json` | Product (stays) | **PRODUCT_INTEGRATION_CONFIG — stays in Product** | N/A | ForgeMind's project configuration for external Runtime |
| 9 | `.agent-loop/gates.json` | Product (stays) | **PRODUCT_INTEGRATION_CONFIG — stays in Product** | N/A | ForgeMind's gate configuration for external Runtime |
| 10 | `.agent-loop/*/SCHEMA.md` (8 files) | Runtime | COPY_TO_RUNTIME | Low | Schemas preserved; genericization of `project_id` in manifests SCHEMA |
| 11 | `docs/planning/wp_al_1b3..1c6*.md` | Product (stays) | KEEP_IN_PRODUCT (historical) | Low | Historical record only |
| 12 | `forgemind_project_source_of_truth/` | Product | KEEP_IN_PRODUCT | None | Runtime references via config, not path |
| 13 | `backend/`, `frontend/`, `infra/` | Product | KEEP_IN_PRODUCT | None | No Runtime coupling identified |
| 14 | `Makefile` | Product | KEEP_IN_PRODUCT | None | No Runtime targets |
| 15 | `docker-compose*.yml` | Product | KEEP_IN_PRODUCT | None | No Runtime coupling identified |
| 16 | `.github/workflows/ci-*.yml` | Product | KEEP_IN_PRODUCT | None | No Runtime references |
| 17 | `HERMES.md` | Product (stays) | **PRODUCT_OWNED — stays in Product** | N/A | Runtime derives its own governance document |
| 18 | `README.md` | Product | KEEP_IN_PRODUCT | None | Runtime gets its own |
| 19 | `.env.example` | Product | KEEP_IN_PRODUCT | None | No Runtime env vars |

### Critical genericization items

Items D1-D9 and D14 require the Runtime to accept **external project configuration** rather than hardcoded "forgemind" values. This is the core architectural change. The Runtime must be genericized in SP-2 to accept project config from the target repository (e.g., `.agent-loop/project.json` in ForgeMind).

---

## 5. Proposed Target Architecture

### 5.1 Agent Runtime repository — layout evolution

The Runtime repository layout evolves across phases. The initial SP-1A bootstrap preserves the current ForgeMind structure. Post-SP-2 enhancements introduce genericization artifacts and documentation improvements.

#### 5.1A SP-1A Bootstrap Layout (provenance-preserving copy)

The SP-1A bootstrap copies only Runtime-owned implementation, schemas, and test inventory. Product-owned configuration (`.agent-loop/project.json`, `.agent-loop/gates.json`, `scripts/agent-loop/templates/story-prd.json`) remains in ForgeMind and is NOT copied to the Runtime repository.

```
<runtime-repo>/
├── scripts/agent-loop/           # Runtime-owned implementation (unchanged)
│   ├── lib/                      # Core runtime (contracts, adapters, harness, reporting)
│   ├── tests/                    # Runtime-owned test suite + harness scenarios
│   ├── run-story.sh
│   ├── verify-story.sh
│   ├── report-story.sh
│   ├── config.sh                 # Copied unchanged (ForgeMind-specific paths still present)
│   └── README.md
├── .agent-loop/                  # Runtime-owned schemas only (unchanged)
│   ├── failure-context/SCHEMA.md
│   ├── review/SCHEMA.md
│   ├── review-adapter/SCHEMA.md
│   ├── repair/SCHEMA.md
│   ├── repair-adapter/SCHEMA.md
│   └── manifests/SCHEMA.md
├── docs/
│   └── provenance.md             # NEW: source repo, baseline commit, copy metadata
├── .gitignore
└── README.md                     # Minimal: states this is a provenance-preserving copy
```

**SP-1A constraints:**
- Copy only Runtime-owned implementation (lib/, tests/, shell scripts, README)
- Copy only Runtime-owned schemas (.agent-loop/*/SCHEMA.md)
- Do NOT copy Product-owned configuration (project.json, gates.json, story-prd.json)
- Preserve all copied paths exactly
- No schema relocation
- No generic template creation
- No `examples/` directory
- No layout redesign
- Only minimal repository metadata (provenance.md, basic README.md)

**Handling Product configuration dependencies:**
If unchanged Runtime code temporarily requires Product configuration during SP-1B testing:
- Tests may reference an explicitly supplied ForgeMind checkout path
- Tests that cannot run without Product configuration are recorded as blocked
- Do NOT duplicate Product configuration into the Runtime repository merely to make the bootstrap self-contained

#### 5.1B Post-SP-2 Target Layout (after genericization, pre-parity)

After SP-2 genericization, the Runtime repository includes additional structure to support external project configuration and documentation. However, structural relocation of existing paths is NOT authorized until after parity (SP-3) is proven.

```
<runtime-repo>/
├── scripts/agent-loop/           # Genericized (ForgeMind-specific assumptions removed)
│   ├── lib/                      # Core runtime (genericized config_loader.py, etc.)
│   ├── templates/                # Generic story template (NEW)
│   ├── tests/                    # Runtime test suite + harness scenarios
│   ├── run-story.sh
│   ├── verify-story.sh
│   ├── report-story.sh
│   ├── config.sh                 # Genericized (no FORGEMIND_* env vars)
│   └── README.md                 # Updated to reflect generic Runtime
├── .agent-loop/                  # Preserved paths (schemas NOT relocated until post-parity)
│   ├── failure-context/SCHEMA.md
│   ├── review/SCHEMA.md
│   ├── review-adapter/SCHEMA.md
│   ├── repair/SCHEMA.md
│   ├── repair-adapter/SCHEMA.md
│   └── manifests/SCHEMA.md       # Genericized (project_id configurable)
├── examples/                     # NEW: example project configurations
│   └── forgemind/                # ForgeMind integration example
│       ├── project.json
│       └── gates.json
├── docs/
│   ├── provenance.md
│   ├── contracts.md              # Contract documentation
│   └── integration-guide.md      # How to configure a target project
├── HERMES.md                     # NEW: Runtime governance document (derived from Product HERMES.md)
├── .gitignore
├── Makefile                      # NEW: Runtime-specific build/test commands
├── pyproject.toml                # NEW: Python package metadata (if applicable)
└── README.md                     # Comprehensive Runtime documentation
```

**Post-SP-2, pre-parity constraints:**
- May contain generic templates, example configs, versioned contract documentation
- Existing Runtime paths (.agent-loop/*/SCHEMA.md, scripts/agent-loop/**) are preserved
- Schema relocation is NOT authorized until after SP-3 parity is proven
- `src/`/`cli/`/`lib/` restructuring is NOT authorized until after SP-3 parity is proven
- Layout refactor belongs to a separately approved post-parity phase

### 5.2 ForgeMind repository after extraction (what remains)

```
forgemind-ai-operations/
├── .agent-loop/                  # ForgeMind-specific project config (PRODUCT_INTEGRATION_CONFIG)
│   ├── project.json              # project_id, paths, policy
│   └── gates.json                # ForgeMind gate definitions
├── docs/agent-loop-integration.md  # How to invoke external Runtime against this repo
├── HERMES.md                     # PRODUCT_OWNED governance (unchanged)
├── scripts/agent-loop/           # RETAINED until SP-5 removal gate (dual-copy period)
├── backend/, frontend/, infra/   # Product code (unchanged)
└── ... (existing Product structure)
```

### 5.3 Integration contract (versioned, explicit)

The Runtime consumes a **project configuration bundle** from the target repository:

```json
{
  "runtime_version": ">=1.0.0,<2.0.0",
  "project_id": "forgemind",
  "project_config_path": ".agent-loop/project.json",
  "gates_config_path": ".agent-loop/gates.json",
  "manifest_path": ".agent-loop/story-manifests/<story>.json"
}
```

The Runtime does NOT need to know about Supply Risk, RAG, approvals, or any Product domain. It only needs:
- Path policies (allowed/forbidden)
- Verification commands (test_commands.targeted_args)
- Environment requirements
- Acceptance criteria
- Repair budget

---

## 6. External Project Contract

### 6.1 What the Runtime expects from a target project

| Requirement | Source | Format |
|-------------|--------|--------|
| Project identifier | `project.json:project_id` | string |
| Git repository root | auto-detected via `git rev-parse --show-toplevel` | path |
| Allowed paths | `story-manifest.json:allowed_paths` | gitwildmatch[] |
| Forbidden paths | `story-manifest.json:forbidden_paths` + `project.json:path_policy` | gitwildmatch[] |
| Test commands | `story-manifest.json:test_commands.targeted_args` | string[] |
| Environment requirements | `story-manifest.json:environment_requirements` | object |
| Repair budget | `story-manifest.json:repair_budget` | int 0-3 |
| Worktree roots | `project.json:structure` | path map |
| Run artifacts output | `project.json:structure:runs_root` | path |

### 6.2 What the Runtime produces for a target project

| Artifact | Location | Format |
|----------|----------|--------|
| Passport | `<runs_root>/<run_id>/reports/passport.json` | JSON |
| Verify results | `<runs_root>/<run_id>/reports/verify-result.{initial,reverify}.json` | JSON |
| Review result | `<runs_root>/<run_id>/reports/review-result.json` | JSON |
| Repair result | `<runs_root>/<run_id>/reports/repair-result.json` | JSON |
| Final report | `<runs_root>/<run_id>/reports/final-report.json` | JSON |
| Failure context | `<runs_root>/<run_id>/reports/failure-context.{initial,repair}.json` | JSON |
| Evidence snapshots | `<runs_root>/<run_id>/snapshots/` | SHA-256 verified |

### 6.3 Version compatibility

Runtime declares supported config schema versions:
```json
{
  "supported_config_schema_versions": ["1.0"],
  "runtime_version": "1.0.0"
}
```

Target project declares required runtime version:
```json
{
  "runtime_version": ">=1.0.0,<2.0.0",
  "config_schema_version": "1.0"
}
```

---

## 7. Contract Portability Matrix (CORRECTED)

| Contract | Current File | Portability | Rationale |
|----------|-------------|-------------|-----------|
| Failure Context | `lib/failure_context.py` | PORTABLE_AS_IS | No ForgeMind-specific logic; sanitization is generic |
| Review Contract | `lib/review_contract.py` | PORTABLE_AS_IS | Schema validation is project-agnostic |
| Review Adapter | `lib/review_adapter.py` | PORTABLE_AS_IS | Invokes external reviewer command; no Product coupling |
| Review-Result Reporting | `lib/review_result_reporting.py` | PORTABLE_AS_IS | Pure classification logic |
| Repair Contract | `lib/repair_contract.py` | PORTABLE_AS_IS | Identity validation is generic |
| Repair Adapter | `lib/repair_adapter.py` | PORTABLE_AFTER_RENAME | References `harness.gitwildmatch` (import path change only) |
| Harness utilities | `lib/harness.py` | PORTABLE_AS_IS | JSON parsing, JUnit, gitwildmatch — all generic |
| Passport | `lib/passport.py` | PORTABLE_AS_IS | Run identity tracking |
| Final Status | `lib/report_final_status.py` | PORTABLE_AS_IS | Pure state machine; no Product knowledge |
| Manifest Loader | `lib/manifest_loader.py` | PORTABLE_AFTER_RENAME | Schema validation requires genericization of `project_id` |
| Mock Reviewer | `lib/mock_reviewer.py` | **TEST_ONLY** | Deterministic test tool; not production integration |
| Mock Repair Actor | `lib/mock_repair_actor.py` | **TEST_ONLY** | Deterministic test tool; not production integration |
| Config Loader | `lib/config_loader.py` | REQUIRES_PROJECT_ADAPTER | Hardcoded `EXPECTED_PROJECT_ID = "forgemind"`, `FORGEMIND_*` env vars |
| Gates Config | `.agent-loop/gates.json` | **REQUIRES_PROJECT_ADAPTER** | Contains `project_id: "forgemind"` and encodes Product-specific Ruff/mypy assumptions |
| Project Config | `.agent-loop/project.json` | **PRODUCT_INTEGRATION_CONFIG** | Stays in Product; consumed by external Runtime |
| Schemas (8 files) | `.agent-loop/*/SCHEMA.md` | PORTABLE_AFTER_RENAME | `project_id` must become configurable in manifests SCHEMA |
| Config shell | `config.sh` | REQUIRES_PROJECT_ADAPTER | Hardcoded `AIAutomation` path, `forgemind-agent-loop` name |
| Guard shell | `lib/guard.sh` | PORTABLE_AFTER_RENAME | Comments say "ForgeMind" but logic uses env var |
| Tests shell | `lib/tests.sh` | PORTABLE_AFTER_RENAME | Line 47 `"Running pytest in backend/"` is cosmetic |
| Story Template | `templates/story-prd.json` | **FORGEMIND_SPECIFIC** | Contains ForgeMind Phase-4 story; not a generic template |

### Summary (recalculated)

| Portability | Count |
|-------------|-------|
| PORTABLE_AS_IS | 9 |
| PORTABLE_AFTER_RENAME | 5 |
| REQUIRES_PROJECT_ADAPTER | 3 |
| PRODUCT_INTEGRATION_CONFIG | 1 |
| FORGEMIND_SPECIFIC | 1 |
| TEST_ONLY | 2 |

**Key insight:** The core runtime logic (contracts, adapters, state machine) is already portable. Configuration loading, path assumptions, and ForgeMind-specific configuration need genericization. Test-only tools are clearly identified as such.

---

## 8. Repository Strategy Options

### OPTION A — Keep one repository with stronger internal boundaries

**Description:** Maintain current single-repo structure; add logical boundaries between Product and Runtime within the same codebase.

**Benefits:**
- Zero migration cost
- No tooling changes
- Single CI/CD pipeline
- Easy cross-track references

**Risks:**
- Agent Loop remains ForgeMind-specific forever
- Cannot reuse for other projects
- Runtime testing requires Product context
- Confusing for external contributors
- Violates proposed intent (B: "independent engineering runtime")

**Migration complexity:** None (status quo)
**Operational complexity:** Low
**Effect on Product development:** No change
**Effect on Runtime development:** Constrained — must maintain Product compatibility
**Rollback ability:** N/A (no migration)
**Evidence gained:** None
**Premature work:** None

**Verdict:** FAILS to achieve the stated goal of an independent runtime.

---

### OPTION B — Extract Runtime into a new repository; direct cutover after test baseline

**Description:** Create a new repository for the Agent Runtime. Copy runtime code. Cutover occurs after the external configuration is runnable (SP-2) and a direct-cutover integration check confirms the external Runtime can invoke ForgeMind. No formally required dual-copy cross-repository normalized parity period. The SP-4 current-capability integration exercise is not required before cutover. The internal copy may be removed or deactivated at cutover.

**Phases under Option B:**
- SP-1B establishes the independent unchanged-copy test baseline
- SP-2 establishes runnable external configuration
- Direct-cutover integration check confirms the external Runtime can invoke ForgeMind
- Cutover: the internal copy may be removed or deactivated
- No normalized comparison against the retained internal copy is required before cutover
- The SP-4 overlap exercise is not required before cutover

**Benefits:**
- Clean separation
- Runtime can evolve independently
- Runtime can target other repositories immediately
- ForgeMind deployment unaffected
- Clear ownership boundaries
- Faster path to external Runtime use

**Risks:**
- Migration must be behavior-preserving
- Cross-repo testing requires coordination
- Historical WP documents remain in Product repo (acceptable — they're historical)
- ForgeMind integration config must be designed correctly before first integration exercise
- No dual-copy parity safety net — if cross-repository integration fails, rollback requires restoring the internal copy from Git and repeating validation
- Higher migration risk due to absence of provenance-preserving overlap period

**Migration complexity:** Medium
**Operational complexity:** Medium (two repos, two CIs)
**Effect on Product development:** Expected to be limited to integration configuration and documentation after migration (no direct application-code references were found in inspected paths, but operational coupling must still be decoupled)
**Effect on Runtime development:** Liberated — can evolve without Product constraints
**Rollback ability:** Medium (can stop using the new repository; original repo intact; but requires re-validation)
**Evidence gained:** Independent runtime CI pass, cross-repo integration
**Premature work:** Risk of over-engineering the "project adapter" abstraction before second consumer exists

**Verdict:** Achieves the goal. Higher risk due to absence of dual-copy parity period.

---

### OPTION C — New Runtime repository + compatibility copy until parity proven (RECOMMENDED)

**Description:** Create new Runtime repository. **Copy** runtime code there (do not move). The compatibility copy in ForgeMind is **explicitly retained** through the normalized parity gate (SP-3) and the current-capability integration exercise (SP-4). The copy is removed only through the explicit removal gate (SP-5), which requires proven parity and successful integration exercise.

**Benefits:**
- All benefits of Option B
- Additional safety: ForgeMind can continue working even if Runtime repo migration has issues
- Dual-copy period provides provenance-preserving overlap; parity is proven before cleanup
- Rollback is straightforward (stop using the new repository; ForgeMind continues with internal copy)
- Integration exercise validates the actual extraction against current capabilities
- Lower migration risk due to explicit dual-copy parity period

**Risks:**
- Temporary duplication (bounded by SP-1A → SP-5 timeline)
- Slightly more complex migration (must maintain both copies in sync during dual-copy period)
- Must define clear parity criteria (see §7, SP-3)

**Migration complexity:** Medium-High
**Operational complexity:** Medium (two repos, temporary dual maintenance)
**Effect on Product development:** Expected to be limited to integration configuration and documentation (ForgeMind continues with internal copy if needed)
**Effect on Runtime development:** Liberated, but with safety net
**Rollback ability:** High (original copy remains until explicit SP-5 removal)
**Evidence gained:** Independent CI pass, cross-repo normalized parity, current-capability integration exercise
**Premature work:** None — the dual-copy phase is explicitly bounded and removal is gated

**Verdict:** ACHIEVES THE GOAL with maximum safety. Recommended.

---

## 9. Recommended Strategy

**Recommendation: OPTION C — New Runtime repository + compatibility copy until parity proven.**

**Rationale:**

1. **No direct Agent Loop references were found in the inspected Product application paths at baseline 2217e588.**
2. **Extraction changes are primarily Runtime-side, with bounded Product integration-configuration and documentation changes.**

3. **Genericization scope is bounded** — 3 files require structural changes (config_loader.py, config.sh, gates.json). 9 files are portable as-is. 2 files are test-only.

4. **Parity gate eliminates migration risk** — the copy in ForgeMind serves as fallback until the independent Runtime repo demonstrates normalized semantic equivalence through harness scenarios and a current-capability integration exercise.

5. **No premature abstraction** — the "project adapter" is the minimum viable interface: a JSON config file in the target repo. No plugin system, no shared library, no submodule.

6. **Evidence-driven** — we learn whether the extraction works by actually running it, not by theorizing.

7. **Rollback is straightforward** — if the Runtime repo has issues, stop using it; ForgeMind continues with its internal copy.

---

## 10. Phased Migration Plan (REVISED)

### SP-0A — Separation Decision Document (Revised)

**Objective:** Formal Product Owner decision to proceed with separation.

**Allowed scope:**
- Create separation architecture decision/planning document **outside** Source of Truth (e.g., `docs/planning/sp0a_separation_decision.md`)
- Obtain explicit Product Owner approval
- Choose provisional repository name

**Non-goals:**
- No implementation
- No file movement
- No new branches
- **Do NOT modify `forgemind_project_source_of_truth/08_DECISION_LOG.md`** — the Product Source of Truth remains protected. Only after PO approval, under a separate authorized task, may the accepted Product boundary decision be recorded in the Decision Log if required.

**Required evidence:**
- This assessment (SP-0 report, revised)
- Manager review and approval

**Verification gate:**
- PO approves the separation decision document
- Provisional name chosen

**Rollback point:** N/A (decision only)

**Completion criteria:**
- Separation decision document approved
- Repository name chosen (provisional: `forgemind-agent-runtime`)
- Phase SP-0B authorized

**Dependencies:** SP-0 report approved

---

### SP-0B — File and Dependency Migration Map

**Objective:** Produce exact file-by-file migration plan with source paths, target paths, required changes, and verification commands. Determine the exact Runtime test inventory and commands.

**Allowed scope:**
- Analysis only
- Create migration manifest document
- Identify Runtime-owned tests vs Product tests vs historical tests

**Non-goals:**
- No file movement
- No code changes
- No new repositories

**Required evidence:**
- Complete file inventory (this report §4)
- Dependency analysis (this report §3)
- Portability matrix (this report §7)
- **Exact Runtime test inventory** — which tests are Runtime-owned and will be copied

**Verification gate:**
- Migration manifest reviewed by manager
- Every file classified with migration action
- Genericization changes enumerated
- Runtime test inventory determined

**Rollback point:** N/A (planning only)

**Completion criteria:**
- Migration manifest document approved
- Runtime test inventory identified
- Phase SP-1A authorized

**Dependencies:** SP-0A approved

---

### SP-1A — Runtime Repository Bootstrap and Provenance-Preserving Copy (NEW)

**Objective:** Create new Runtime repository with a provenance-preserving copy of all Runtime-owned code. Preserve current paths and layout where practical. No genericization, no test skipping, no behavioral code changes.

**Allowed scope:**
- Create new repository `forgemind-agent-runtime`
- **Copy** (not move) Runtime-owned files per migration manifest
- Preserve current directory layout (no `src/`, `cli/`, `lib/` redesign yet)
- Preserve behavior and contracts exactly as they exist in baseline
- Record source repository and baseline commit (`2217e588`) in a provenance file
- Verify blob equivalence (SHA-256 or git hash) for all copied files
- Copy and discover the planned test inventory (as determined by SP-0B)
- Record tests blocked by Product-relative assumptions (e.g., tests that require `FORGEMIND_MAIN_ROOT` or reference Product-specific paths)
- **No behavioral code changes** — do not genericize, do not modify, do not skip tests to obtain a green baseline

**Non-goals:**
- No genericization of any kind (even if tests cannot run without ForgeMind environment)
- No test skipping to obtain green baseline
- No changes to ForgeMind Product repo
- No ForgeMind integration yet
- No cross-repo orchestration
- No multi-project support
- No directory-layout redesign
- No new CI pipeline yet

**Required evidence:**
- Provenance file records source commit and copy metadata
- All copied files have verified blob equivalence to baseline
- Copied tests are present and discoverable (even if some cannot run without Product environment)
- Blocked tests are explicitly listed (not silently skipped)
- No behavioral changes to original: ForgeMind repo unchanged

**Verification gate:**
- File copy is complete and provenance verified (blob hashes match)
- No changes to ForgeMind Product repo
- Runtime-owned tests are present in new repo (even if some require Product environment)
- Blocked tests are documented (not hidden or skipped)

**Rollback point:**
- Stop using the new repository
- Preserve it for evidence
- Revert unpublished local changes where safe
- Close or abandon the migration branch

**Completion criteria:**
- Runtime repo exists with copied files (provenance-preserving, unchanged)
- Provenance recorded and verified
- Runtime-owned tests present (including blocked tests)
- Blocked test list documented
- Phase SP-1B authorized

**Dependencies:** SP-0B approved

**Note:** SP-1A does not execute tests. It establishes the copy and discovers what tests exist. SP-1B executes the inventory and validates behavior. Genericization (if needed) belongs to SP-2.

---

### SP-1B — Independent Runtime Test/CI Baseline (NEW)

**Objective:** Execute the Runtime-owned test inventory (discovered in SP-1A), establish authoritative test commands, and prove the copied implementation behaves like the baseline. Establish independent CI.

**Allowed scope:**
- Execute Runtime-owned tests in the new repository (as discovered and listed in SP-1A)
- Establish `make test` and `make lint` equivalents for Runtime
- Set up CI pipeline for Runtime repo
- Prove the copied implementation behaves like the baseline (for tests that can run without Product environment)
- Document tests that require Product environment (cannot run in isolation)
- Add independent test/CI entry points (e.g., Makefile targets) if needed for Runtime-specific test execution

**Non-goals:**
- No external ForgeMind integration yet
- **No behavioral genericization** (genericization belongs to SP-2)
- No layout refactor
- No real LLM integration
- **No silent test skipping** — if a test cannot run, it must be explicitly documented as "requires Product environment" rather than skipped to obtain green baseline

**Required evidence:**
- Exact list of Runtime-owned tests with pass/fail/blocked status
- Test commands documented
- CI pipeline green (for tests that can run without Product environment)
- Blocked test list documented (tests requiring Product environment)
- Behavior comparison: copied tests produce same results as in ForgeMind (for tests that don't require ForgeMind-specific config)

**Verification gate:**
- `make test` (or equivalent) passes for Runtime-owned tests that can run independently
- `make lint` passes
- CI pipeline green (for independent tests)
- Test inventory matches SP-0B plan
- Blocked tests explicitly listed (not hidden)

**Rollback point:**
- Stop using the new repository
- Preserve for evidence
- Investigate failures

**Completion criteria:**
- Runtime repo is independently testable (for tests that don't require Product environment)
- Independent Runtime-owned tests pass
- CI pipeline established
- Blocked test list documented
- Phase SP-2 authorized

**Dependencies:** SP-1A complete

**Note on test counts:** The historical claim of "907 passed" in WP-AL-1C6 completion report includes all backend tests (Product + Runtime harness). SP-0B must determine the exact count of Runtime-owned tests. Not all 907 tests are Runtime-owned; many are Product tests that happen to run in the same suite. Some Runtime tests may require Product environment and will be blocked until SP-2 genericization or SP-3 integration.

**Note on genericization:** SP-1B does NOT perform genericization. If tests fail due to ForgeMind-specific assumptions (e.g., `FORGEMIND_MAIN_ROOT`), they are documented as blocked. Genericization (to enable those tests) belongs to SP-2.

---

### SP-2 — External Project Configuration and Genericization (REVISED)

**Objective:** Remove ForgeMind-specific env/path/project assumptions from the Runtime. Introduce versioned external configuration. Keep behavior changes isolated and tested.

**Allowed scope:**
- Genericize `config_loader.py` (remove `EXPECTED_PROJECT_ID = "forgemind"`, `FORGEMIND_*` env vars)
- Genericize `config.sh` (remove `AIAutomation` path check, hardcoded worktree names)
- Genericize `manifest SCHEMA.md` (make `project_id` configurable)
- Genericize `gates.json` handling (remove hardcoded `project_id: "forgemind"`)
- Create generic story template (separate from ForgeMind-specific `story-prd.json`)
- Create example ForgeMind project config in `examples/forgemind/`
- Implement external project config resolution (Runtime defaults + project overrides)
- Version compatibility checking

**Non-goals:**
- No actual ForgeMind integration yet
- No cross-repo execution
- No real LLM integration
- No layout refactor

**Required evidence:**
- Schema documents for external project config
- Validation tests for external project config
- Version compatibility tests
- Example ForgeMind config validates against all schemas
- Invalid configs are rejected with clear errors

**Verification gate:**
- External config schema tests pass
- ForgeMind example config validates
- Runtime tests still pass after genericization
- Config loader accepts external project config
- Config loader rejects invalid project config

**Rollback point:**
- If genericization breaks behavior: revert to pre-SP-2 branch
- If tests fail: fix before proceeding

**Completion criteria:**
- External project config contract documented and tested
- ForgeMind example config complete
- All Runtime tests still pass
- Phase SP-3 authorized

**Dependencies:** SP-1B complete

---

### SP-3 — Cross-Repository Compatibility/Parity Gate (REVISED)

**Objective:** Prove the independent Runtime repo can operate against the ForgeMind Product repo with **normalized semantic equivalence** (not byte-identical artifacts).

**Parity definition (CORRECTED):**

Parity is defined as **normalized semantic equivalence** covering at minimum:
- Terminal status (final_status value)
- Exit code
- Invocation counts (repair_attempt, repair_adapter_invocations, etc.)
- Configured repair-budget behavior produces equivalent invocation counts and terminal results
- Contract validation (same pass/fail outcomes)
- Gate outcomes (same gate pass/fail for same inputs)
- Failure classification (same error codes)
- Required artifact presence (same files created)

**Evidence classes:**

1. **Raw immutable input evidence:**
   - Raw hashes match only for inputs expected to be byte-identical
   - Examples: story manifest, base_commit SHA, allowed_paths/forbidden_paths patterns
   - These do not contain volatile fields

2. **Generated result artifacts:**
   - Remove explicitly approved volatile fields
   - Canonicalize JSON deterministically (sorted keys, consistent formatting)
   - Compare semantic content
   - Optionally hash the canonicalized representation
   - Do NOT require raw result-file hashes to match when volatile fields legitimately differ

**Volatile fields (excluded from raw hash comparison):**
- `run_id` (generated per-run)
- `slot_id` (environment-dependent)
- Timestamps (`created_at`, `updated_at`, `timestamp`)
- Absolute paths (e.g., `/path/to/repo-A/...` vs `/path/to/repo-B/...`)
- Environment metadata (e.g., different `FORGEMIND_MAIN_ROOT` values, `AGENTLAB_ROOT` values)
- `workspace_root` paths

**Repair budget semantics:**

Parity cases must explicitly include `repair_budget=0` semantics:
- repair adapter calls = 0
- repair actor calls = 0
- reverify calls = 0 after initial verification failure
- final_status = `VERIFICATION_FAILED`
- exit code = 1

This verifies that the configured repair budget is respected, not that a universal maximum of 1 is enforced (the 1-attempt limit is an orchestration-level constraint in WP-AL-1C6, not a universal Runtime invariant).

**External invocation direction (CORRECTED):**

The `.agent-loop/project.json` already exists in the Product baseline (2217e588). SP-3 must NOT create this file unless SP-0B proves that replacement or version update is required by the external config contract.

- Preserve `.agent-loop/project.json` Product ownership and identity
- Version or update it only where required by the approved external config contract (e.g., adding `runtime_version` field)
- Product configuration must NOT contain a machine-specific path to the Runtime repository
- The external Runtime is invoked with: `target project root` + `project config path` + `story manifest path`
- Runtime compatibility version may be declared in Product config
- Runtime installation/path discovery belongs to the invocation environment (e.g., PATH, explicit CLI argument)

**Allowed scope:**
- Configure ForgeMind repo to be consumed by external Runtime (using existing `.agent-loop/project.json`)
- Update `.agent-loop/project.json` only if required by external config contract (e.g., add `runtime_version`)
- Run harness scenarios from Runtime repo against ForgeMind worktree
- Compare results with internal-copy runs using normalized parity definition

**Non-goals:**
- No real LLM agents
- No production deployment changes
- No Product application-code changes (documentation additions such as `docs/agent-loop-integration.md` are authorized)
- No removal of internal Runtime copy from ForgeMind

**Required evidence:**
- Harness scenarios A-AN pass from Runtime repo against ForgeMind
- Normalized parity proven (terminal status, exit codes, invocation counts, gate outcomes match)
- ForgeMind `.agent-loop/project.json` validates
- No Product application-code changes; existing Product integration configuration was versioned or updated only as authorized by the approved external configuration contract.

**Verification gate:**
- Cross-repo harness run succeeds
- Normalized parity comparison shows equivalence (excluding allowed differences)
- ForgeMind deployment unaffected

**Rollback point:**
- Stop using the external Runtime
- Continue using internal copy
- Investigate divergence

**Completion criteria:**
- Cross-repo parity proven (normalized semantic equivalence)
- Phase SP-4 authorized

**Dependencies:** SP-2 complete, Runtime repo stable

---

### SP-4 — Supervised ForgeMind Current-Capability Integration Exercise

**Objective:** Demonstrate that the external Runtime repository can process a controlled, task-shaped fixture using current capabilities (mock actors), producing a complete evidence set and passing normalized semantic comparison.

**Current capability boundary:** The Runtime contains only test-only mock actors (mock_reviewer.py, mock_repair_actor.py). It does not yet contain real implementer, reviewer, or repair actor adapters. This phase exercises current capability, not production readiness.

**Allowed scope:**
- Define a controlled task-shaped fixture (deterministic pre-staged change in a ForgeMind test branch)
- Execute Runtime against the fixture using mock actors
- Capture full evidence set (artifacts, logs, hashes)
- Human observation and supervision
- Compare results against internal-copy baseline using normalized semantic equivalence

**Non-goals:**
- No autonomous implementation
- No real reviewer or repair actor behavior
- No production-readiness claims
- No claims of completing a real engineering task

**Required evidence:**
- Controlled fixture definition
- Full evidence set from external Runtime execution
- Normalized semantic comparison against internal-copy baseline
- Human observation record

**Verification gate:**
- External Runtime produces expected terminal status
- Normalized semantic equivalence achieved
- No behavioral divergence detected

**Rollback point:**
- Stop using the external Runtime
- Continue using internal copy
- Investigate divergence

**Completion criteria:**
- Successful current-capability integration exercise
- Evidence pack created
- Normalized semantic equivalence proven
- Phase SP-5 authorized

**Dependencies:** SP-3 complete, controlled integration exercise defined

---

### SP-5 — Removal of Duplicated Runtime from ForgeMind

**Objective:** After proven parity and successful integration exercise, remove the internal Runtime copy from the ForgeMind repository.

**Allowed scope:**
- Remove `scripts/agent-loop/` from ForgeMind
- Remove `.agent-loop/*/SCHEMA.md` from ForgeMind (keep `.agent-loop/project.json` and `.agent-loop/gates.json`)
- Update ForgeMind documentation
- Keep `.agent-loop/project.json` and `.agent-loop/gates.json` in ForgeMind (PRODUCT_INTEGRATION_CONFIG)

**Non-goals:**
- No changes to Runtime repo
- No changes to Product code
- No deployment changes

**Required evidence:**
- SP-3 parity proven
- SP-4 integration exercise successful
- ForgeMind CI still passes after removal
- ForgeMind deployment unaffected
- Documentation updated

**Verification gate:**
- ForgeMind CI passes
- No references to removed paths
- ForgeMind can still be consumed by external Runtime
- Git history preserved

**Rollback point:**
- If removal breaks something: restore from Git history
- This is the ONLY destructive step; everything else is additive

**Completion criteria:**
- Internal Runtime copy removed
- ForgeMind repo contains only Product code + integration config
- External Runtime is the single source of truth for orchestration

**Dependencies:** SP-3 and SP-4 complete, manager approval

**Reversibility and removal gate:**

SP-5 is the first removal phase. It is destructive in the working tree but recoverable through Git.

- Requires an isolated branch/PR and explicit manager/PO approval
- The pre-removal commit must be recorded
- Rollback restores the removed paths and compatible integration configuration from Git
- Removal is merged only after Product CI and external Runtime invocation pass from clean checkouts

Git restoration is not automatic or cost-free — it requires:
- Identifying the pre-removal commit
- Restoring the removed directories
- Re-verifying that Product CI passes
- Re-verifying that external Runtime invocation still works
- Potentially resolving any integration-config drift that occurred during the removal period

Therefore SP-5 should only proceed after SP-3 and SP-4 have proven that the external Runtime works correctly, minimizing the probability that restoration will be needed.

---

### 10.1 Runtime Production Integration Track (SEPARATE)

**Note (CORRECTED):** Repository separation and production integration are two separate roadmaps.

**Track A — Repository Separation Track** (this document):
- SP-0A through SP-5
- Extraction, independent tests, external config, cross-repo parity, removal of duplicate

**Track B — Runtime Production Integration Track** (separate, future work):
- Real implementer adapter (not mock)
- Real reviewer adapter (not mock)
- Real repair actor (not mock)
- Supervised production-like integration exercise with real agents
- Human handoff mechanism

**These tracks are independent.** Repository separation can proceed with mock actors (SP-4). Real-actor integration is a separate effort that may proceed in parallel or later.

**Avoid indefinite dual-copy maintenance:** The dual-copy period (SP-1A through SP-5) is bounded by parity and integration exercise evidence. If real-actor integration takes longer, the dual-copy period should still end after SP-4 proves the extraction works. The Runtime repo becomes the authoritative source after SP-5, regardless of whether real actors exist.

---

### Phase splitting assessment (REVISED)

- **SP-1A and SP-1B are separate** — copy first (provenance-preserving), then establish test baseline. This ensures behavior preservation before any changes.
- **SP-2 is genericization** — only after tests are proven in the new repo.
- **SP-3 and SP-4 are separate** because parity proof (harness scenarios with mocks) and integration exercise (controlled fixture) are different goals.
- **SP-5 should NOT be split** — partial removal would create ambiguity.
- **SP-0A and SP-0B could be merged** but are separated for governance clarity.
- **No layout refactor** during initial extraction — preserve current structure until parity is proven.

---

## 11. Naming Recommendation (CORRECTED)

| Candidate | Clarity | Independence | Reuse | Collision Risk |
|-----------|---------|--------------|-------|----------------|
| `forgemind-agent-runtime` | High — "runtime" implies execution environment | Medium — "forgemind" prefix preserves lineage | Medium — prefix limits perceived scope but aids discoverability | Low |
| `forgemind-agent-loop` | High — matches existing terminology | Medium — prefix preserves lineage | Low | Low |
| `agent-runtime` | High | High — no Product tie | High — clearly reusable | Medium — too generic, potential collision; availability not verified |

**Provisional recommendation:** `forgemind-agent-runtime`

**Rationale:**
1. The `forgemind-` prefix preserves lineage and discoverability during the migration period.
2. The prefix does **not** create a technical dependency on the Product — it is a naming choice, not a coupling.
3. "Runtime" accurately describes its role (execution environment for autonomous agent loops).
4. Collision/availability was not verified for generic names like `agent-runtime`.
5. A later independent brand may be selected after a second target repository proves general reuse.

**Note:** This is a provisional name. Final naming should be confirmed in SP-0A decision document. The name does not create technical coupling.

---

## 12. Risks and Rollback Strategy (CORRECTED)

### 12.1 Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Genericization breaks behavior | Low | High | SP-2 verification gate: all Runtime-owned tests must pass |
| Cross-repo config resolution fails | Medium | Medium | SP-2 validation tests; example config |
| Parity cannot be proven | Low | High | SP-3 gate; internal copy remains as fallback |
| Current-capability integration exercise fails | Medium | High | Supervised execution; lessons learned feed back |
| Historical documents create confusion | Medium | Low | Clear HISTORICAL classification in migration |
| Dual-copy maintenance burden | Low | Low | Bounded by SP-1A→SP-5 timeline |
| CI/CD duplication | Low | Low | Independent pipelines; no shared infrastructure |
| Real-actor integration delays separation | Low | Medium | Separation proceeds with mocks; real actors are separate track |

### 12.2 Rollback Points (CORRECTED)

| Phase | Rollback Action | Cost |
|-------|----------------|------|
| SP-0A | Do not proceed | Zero |
| SP-0B | Do not proceed | Zero |
| SP-1A | Stop using the new repository; preserve for evidence; revert unpublished local changes where safe; close or abandon the migration branch | Low |
| SP-1B | Same as SP-1A; additionally investigate test failures | Low |
| SP-2 | Revert to pre-SP-2 branch; no Product impact | Low |
| SP-3 | Stop using the external Runtime; continue using internal copy; investigate divergence | Low |
| SP-4 | Stop using the external Runtime; investigate failure | Medium |
| SP-5 | Restore from Git history (if removal causes issues) | Medium (one-time) |

**Note (CORRECTED):** Rollback is not "cost-free" — it requires investigation and potential rework. However, the cost is Low for pre-SP-5 phases because the ForgeMind repository is unchanged and the internal copy remains available.

### 12.3 Critical invariant

**At no point does the Product deployment become dependent on the Runtime repo.** The Runtime is a development-time engineering tool, not a Product deployment dependency. ForgeMind can always be deployed without the Runtime.

---

## 13. Documentation Changes Needed Later (CORRECTED)

| Document | Change | Phase |
|----------|--------|-------|
| `docs/planning/sp0a_separation_decision.md` | NEW — separation decision document (outside Source of Truth) | SP-0A |
| `forgemind_project_source_of_truth/08_DECISION_LOG.md` | Add DEC-013 (separation decision) — **ONLY after PO approval and under separate authorized task** | After SP-0A approved |
| Runtime `HERMES.md` | NEW — derived governance document for Runtime (does not weaken Product HERMES.md) | SP-1A |
| Runtime `README.md` | NEW — Runtime purpose, usage, integration | SP-1A |
| ForgeMind `README.md` | Add section on Agent Loop integration via external Runtime | SP-3 |
| ForgeMind `docs/agent-loop-integration.md` | NEW — how to invoke external Runtime | SP-3 |
| Runtime `docs/` | Migration guide for new target projects | SP-2 |
| ForgeMind Source of Truth | No changes (Runtime is not part of Product SoT) | Never |
| ForgeMind `HERMES.md` | **No changes** — remains PRODUCT_OWNED governance | Never |

---

## 14. Uncertainties Requiring Evidence

| Uncertainty | Required Evidence | Impact | Resolution Phase |
|-------------|-------------------|--------|------------------|
| Whether genericization preserves all harness scenario outcomes | Run A-AN in Runtime repo | Blocks SP-2 completion | SP-2 |
| Exact Runtime test inventory (how many of the 907 are Runtime-owned) | SP-0B analysis | Blocks SP-1B test execution | SP-0B |
| Whether cross-repo config resolution works end-to-end | Cross-repo harness run | Blocks SP-3 | SP-3 |
| Whether current-capability integration exercise proves extraction | Supervised exercise with mock actors | Blocks SP-4 | SP-4 |
| Whether ForgeMind CI is affected by Runtime removal | ForgeMind CI after SP-5 | Blocks SP-5 | SP-5 |
| Whether historical WP documents cause confusion | Manager review | Informational | SP-0A |
| Whether real-actor integration is needed before separation | Manager decision | Affects timeline | SP-0A |

---

## 15. STOP / READY FOR SP-0 DOCUMENT PLANNING

**Status: READY FOR SP-0 MANAGER RE-REVIEW**

**Current state (after corrections):**
- No direct Agent Loop references were found in the inspected Product application paths at baseline 2217e588
- All Runtime→Product dependencies are configuration/path assumptions (genericization, not restructuring)
- Extraction changes are primarily Runtime-side, with bounded Product integration-configuration and documentation changes
- Option C (new repo + compatibility copy until parity) provides maximum safety
- Phased plan (SP-0A → SP-0B → SP-1A → SP-1B → SP-2 → SP-3 → SP-4 → SP-5) allows incremental verification
- Rollback is straightforward at every phase
- Repository separation and production integration are separate tracks
- Parity is defined as normalized semantic equivalence (not byte-identical)
- Provisional name: `forgemind-agent-runtime`
- No calendar estimates (relative complexity only)
- SP-0A does not modify Source of Truth directly

**Decision required:**
1. Approve Option C and proceed to SP-0A (separation decision document)
2. Approve different option (A or B)
3. Request additional evidence before decision
4. Reject separation (maintain status quo)
5. Defer decision (focus on integration exercise first, separation later)

**After approval:** Proceed to SP-0A — formal separation decision document with repository naming (provisional: `forgemind-agent-runtime`).

---

## Final Audit Trailer (CORRECTED)

| Item | Value |
|------|-------|
| **Authoritative baseline commit** | `2217e5882767379c1d34d6cc5ba3193caf7c01ad` |
| **Current branch** | `feature/agent-loop-wp-al-1c6-orchestration-wiring` |
| **Current HEAD** | `5001dbd98c5f1fa7882d1db57c166e657e221505` |
| **Files inspected (from baseline)** | 80+ (full tree listing, specific file contents via `git show 2217e588:<path>`) |
| **Git commands executed** | `git ls-tree`, `git show`, `git grep`, `git rev-parse`, `git branch`, `git status`, `git merge-base` |
| **Tests executed** | NONE (read-only assessment; no tests independently executed) |
| **Repository baseline files modified** | **NONE** |
| **Working-tree assessment artifacts created/edited** | `docs/reviews/sp0_repository_separation_assessment.md` (this file) |
| **Protected files modified** | **NONE** (`docs/reviews/wp_al_1c2_*.md` untouched) |
| **Baseline repository evidence** | Read through `git show`/`git grep` against commit 2217e588 |
| **Assessment file** | Read and edited directly from the working tree (not part of baseline commit) |

### Assumptions

1. The proposed direction (A-E) is the intended architecture, not yet approved.
2. `forgemind-agent-runtime` is the provisional name for the extracted system.
3. ForgeMind remains the first consumer/integration target.
4. Product deployment must remain independent of Runtime.
5. Historical planning documents are evidence of past decisions, not current state.
6. Mock adapters are TEST_ONLY and do not constitute production integration.
7. The Runtime is a development-time engineering tool, not a production runtime dependency.
8. Repository separation and production integration are separate tracks that can proceed independently.

### Blockers

1. No PO decision on separation yet (SP-0A required).
2. Repository name not yet chosen (provisional: `forgemind-agent-runtime`).
3. No real LLM integration exists yet (blocks real-actor integration exercise, but does not block repository separation with mock actors).
4. Exact Runtime test inventory not yet determined (SP-0B must resolve this).

### Recommended Next Action

**Manager re-review required:** Confirm the corrections are satisfactory and authorize SP-0A (formal separation decision document with provisional name `forgemind-agent-runtime`), or request further revisions.
