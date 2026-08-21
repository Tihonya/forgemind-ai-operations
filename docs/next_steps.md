# ForgeMind — Next Steps

**Last Updated:** 2026-08-20
**Current Status:** Development in progress — Release 1 NOT READY
**Reconciliation base snapshot:** main @ `ad6a4786bf8a1de90cb23f4adc8dee22a2c5ef57` (PR #119 merge commit; snapshot semantics per DEC-051)

The `Reconciliation base snapshot` field records the immutable base snapshot used to prepare this document's lifecycle state — it is not a current-`main` assertion; current `main` is determined from Git/GitHub (see DEC-051).

---

## What is ForgeMind?

ForgeMind is a web platform for AI-assisted supply chain risk assessment in engineering and manufacturing environments. **Release 1 is a public portfolio MVP** demonstrating one complete vertical scenario: **Production Plan Supply Risk Review**.

**Release 1 framing:** "Controlled AI-assisted Supply Risk Intelligence portfolio MVP demonstrating one complete, auditable, human-approved vertical workflow." (SD-5)

**Release 1 deliverables:**
- **Live Demo:** Public HTTPS deployment on Product Owner's VPS
- **Source Code:** Public GitHub repository (this repo)
- **Data policy:** Synthetic data only — no real corporate or military systems

**Target reviewer journey:**
CV → Live Demo → complete working scenario (3–5 minutes) → inspect results and state transitions → open GitHub → understand architecture, implementation, tests, deployment, and limitations.

**Canonical Source of Truth:** `forgemind_project_source_of_truth/` (9 documents, 00–08)

**Product strategy:** `docs/planning/wp_strat_01_product_strategy.md` (WP-STRAT-01, completed)

**Assessment evidence:** `docs/reviews/sp1_recovery_mvp_separation_assessment.md` (SP-1 assessment, 2026-08-08). This assessment is a time-scoped historical snapshot. Earlier status classifications in the assessment reflect the state at assessment time and are not canonical current-state authorization. Current acceptance-test status is reported in the table below.

---

## Current Implementation Status

### ✅ IMPLEMENTED

| Capability | Status | Evidence |
|-----------|--------|----------|
| Phase 1: Running Skeleton | COMPLETE | FastAPI + PostgreSQL + Redis + ARQ (Phase 1 baseline: 239 backend tests; additional tests added in later phases) |
| Phase 2: Synthetic ERP Core | COMPLETE | 14 business tables, seed generator, deterministic risk engine |
| Phase 3: Core UI | COMPLETE | Dashboard, supply risk list, supply risk detail |
| Phase 4: Knowledge and RAG | COMPLETE / ACCEPTED | Document ingestion, pgvector index, retrieval with citations, role-filtered retrieval, and DocumentPermission model (WP-REC-05, PR #89); AT-006 PASS and AT-007 PASS via composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02` (Product Owner acceptance 2026-08-15, DEC-049) |
| Authentication + RBAC | COMPLETE | JWT auth, 5 demo accounts (manager/procurement/engineer/admin/auditor) |
| AI provider adapter (chat/reasoning) | COMPLETE | OpenAI-compatible ChatProvider adapter (PR #63); external chat-provider chain — Groq free primary → OpenRouter paid fallback — implemented and incorporated via PR #91 (merge commit `7d425c1d3f1e92e08d62360c28ced22481136fe7`). Runtime architecture present; external live interoperability was subsequently demonstrated for OpenRouter `qwen/qwen3.7-flash` via the WP-REC-05-VFY formal rerun (DEC-049); the repository still has no provider key/budget configured for general use |
| WP-REC-03B: Workflow/state-machine foundation | COMPLETE | Explicit state machine (7 states, immutable transition table), WorkflowEngine with conditional UPDATE concurrency safety, WorkflowRun/WorkflowStep/Recommendation ORM models, Alembic migration, Pydantic run/step schemas, unit and integration tests — merged via PR #65 |
| WP-REC-03C: Structured-output validation | COMPLETE | Structured-output validator, recommendation Pydantic wire schema, versioned prompt template, and unit tests — merged via PR #72 |
| WP-REC-03D: Automatic provider retry/outage | COMPLETE | Automatic provider retry/outage handler, retry policy, unit and integration tests — merged via PR #73 |
| WP-REC-03E: Workflow-run detail + recommendation UI | COMPLETE | Read-only workflow-run detail API, recommendation UI, TanStack Query hook, and tests — merged via PR #74 |
| WP-REC-03F: Backend workflow start/retry API + ARQ worker | COMPLETE | Backend start/retry API (POST /api/v1/workflow-runs, POST /api/v1/workflow-runs/{run_id}/retry), ARQ worker functions (workflow_start, workflow_retry), D6 reconciler cron job, dispatch generation, conditional UPDATE state transitions, all D1–D6 contracts — merged via PR #78 |
| WP-REC-03G: Frontend start/retry UI interaction | COMPLETE | Frontend workflow start and retry controls, stale-mutation protection, role-based authorization (production_manager or run creator), plan-change guard, deterministic polling lifecycle, safe error display — merged via PR #80 |
| WP-REC-05: RAG integration into the AI workflow | COMPLETE | Retrieval integrated into the controlled workflow — server-derived deterministic queries, role-filtered retrieval, bounded/deduplicated context, citation allow-list validation, `FAILED_RETRIEVAL` fail-closed handling, generation-specific WorkflowAuthorizationRecord — merged via PR #89 (merge commit `86e2d0cd3d6d3eaf889ca6d674829f7ac541778c`) |
| WP-REC-05-PROVIDER-IMP: external chat-provider chain + grounded-output hardening | COMPLETE | Groq free primary → OpenRouter paid fallback; capability-aware structured output; per-risk citation allow-list validation; merged via PR #91 (merge commit `7d425c1d3f1e92e08d62360c28ced22481136fe7`); strict post-merge verification passed; DEC-048; external live interoperability subsequently demonstrated for OpenRouter `qwen/qwen3.7-flash` via the WP-REC-05-VFY formal rerun (DEC-049); the repository still has no provider key/budget configured for general use |
| AT-003 (Golden Dataset) | PASS | Seed produces deterministic RISK-001/002/003 |
| AT-004 (Deterministic risk) | PASS | Risk engine returns exact expected values |
| AT-005 (No hidden mocks) | PASS | UI displays real backend data |

**Phase 4 is COMPLETE / ACCEPTED.** RAG and role-filtering implementation exists (retriever, citations, DocumentPermission model, role-filtered SQL query, server-side role derivation, unauthorized-role test, WP-REC-05 PR #89). AT-006 and AT-007 are PASS via the composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02` (Product Owner acceptance 2026-08-15, DEC-049). Phase 5 builds on real, implemented infrastructure.

**WP-REC-03B is a foundation package.** It delivers the workflow state machine, engine, models, and migration — but does NOT deliver end-to-end AI workflow execution. WP-REC-03C (structured-output validation), 03D (automatic provider retry/outage), 03E (workflow-run detail API + recommendation UI), 03F (backend start/retry API + ARQ worker), and 03G (frontend start/retry UI interaction) are now COMPLETE (merged via PRs #72, #73, #74, #78, #80). All Phase 5 implementation packages are delivered. AT-008 and AT-013 are now PASS and Phase 5 is ACCEPTED (Product Owner acceptance 2026-08-14, DEC-043; accepted evidence run `wp-rec-03h-phase-c-20260813-02`). No acceptance test newly passed as a result of 03B alone.

### NOT YET DEPLOYED (Release 1 — implementation complete, deployment pending)

| Capability | Implementation | Deployment Status |
|-----------|----------------|-------------------|
| Demo reset (operator-level, disposable) | WP-P7-03 COMPLETE — `make demo-reset` / `scripts/demo-reset.sh` | Implemented; AT-015 not yet evaluated from deployment evidence |
| Distributed rate limiting | WP-P7-02 COMPLETE — Redis-backed, fail-closed | Implemented; requires deployment verification |
| Backup/restore | WP-P7-02 COMPLETE — `scripts/backup*.sh`, compose `backup` profile | Implemented; restore rehearsal required before production |
| Public HTTPS deployment | WP-P7-02 configuration COMPLETE | NOT STARTED — WP-P7-06 |
| Operational runbooks | `docs/infra-production.md` + `docs/operations/release_1_runbook.md` | COMPLETE |

### What remains before Release 1

- WP-P7-CORR-01 review / merge / post-merge lifecycle (pre-staging architecture / resource correction package — ACTIVE, Draft PR)
- VPS security hardening (separate bounded action; begins only after WP-P7-CORR-01 completes its lifecycle)
- Staging deployment (WP-P7-06)
- Staging verification (WP-P7-07)
- Production deployment (WP-P7-08)
- Post-deployment verification and evidence (WP-P7-09)
- Independent evidence review (WP-P7-09A)
- Product Owner acceptance (WP-P7-10)
- GitHub Release/tag publication (WP-P7-11)
- Final lifecycle reconciliation (WP-P7-12)

### Current MVP completion

Four of five condensed MVP milestones now have verified evidence (step 1 verified by passing integration tests; step 2 now has formal AT-006/AT-007 PASS evidence (composite accepted packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02`, Product Owner acceptance 2026-08-15); step 3 — structured AI recommendation with validation and user retry — is implemented and formally accepted via Phase 5: AT-008 PASS, AT-013 PASS, Phase 5 ACCEPTED; step 4 — approval → procurement → audit — is implemented and formally accepted via Phase 6: AT-009 PASS, AT-010 PASS, AT-011 PASS, AT-012 PASS, Phase 6 CLOSED / ACCEPTED, accepted evidence run `wp-rec-04-vfy-20260816-03`, Product Owner acceptance 2026-08-16). The canonical 13-step Golden Scenario (defined in `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md` §2) remains incomplete. Step 5 of the condensed milestones (deployment) — repository-owned deployment configuration and runbook work is now implemented (WP-P7-02 configuration, `docs/operations/release_1_runbook.md`); actual staging/production deployment execution and deployment evidence are still pending. Phase 5 delivers the structured AI recommendation workflow and workflow retry; Phase 6 delivers human approval, controlled procurement writes, and the complete correlated audit trace.

---

## Product / Runtime Boundary

This repository contains two conceptually separate projects:

### A. ForgeMind Product (this repository)

**Objective:** Public portfolio MVP for CV.

**Success criteria:** Live Demo on VPS, public GitHub, synthetic data, real end-to-end workflows, persisted state, recruiter-friendly README, verified technology stack.

**Release 1 must work independently.** The agent-loop Runtime is not an end-user feature and must not block the portfolio MVP.

### B. Agent Runtime (separate future repository: forgemind-agent-runtime)

**Objective:** Reliable reusable agent-loop tool for the Product Owner's practical use across different repositories.

**Success criteria:** Reliable completion of long-running tasks, controlled retry/repair/reverify, recovery from failures, measurable completion rate, understandable logs, portability across models and repositories.

**Runtime is currently embedded in this repository** under `scripts/agent-loop/` and `.agent-loop/`. It is a development-time tool only — no Product code imports or depends on it at runtime.

**Separation decision:** SP-0A approved (Option C). SP-0B (migration manifest) is READY but NOT YET AUTHORIZED. See `docs/planning/sp0a_separation_decision.md`.

**Runtime separation does NOT block Release 1.** Zero coupling verified.

---

## Delivery Sequence

The accepted planning sequence is:

1. **WP-STRAT-01** (Product Strategy and Release 1 Alignment) — COMPLETED. This package defined the Release 1 product direction, reclassified Phase 4 as PARTIALLY COMPLETE, corrected AT status, and recorded accepted PO decisions.
2. **WP-ARCH-01** (Architecture Hygiene and Agent Onboarding) — COMPLETED and CLOSED (planning accepted, no execution required, 2026-08-09, PR #69 merge commit `3a2bc26`). Zero REQUIRED findings. Sole RECOMMENDED item (agent-onboarding document) deferred.
3. **WP-REC-03A through 03G** (Phase 5 AI Workflow, packages A-G) — COMPLETE. Merged via PRs #63, #65, #72, #73, #74, #78, #80. WP-REC-03G (frontend start/retry UI) merged via PR #80 on 2026-08-12. Phase 5 implementation packages are all delivered.
4. **WP-REC-05-DEC** (RAG integration decomposition and planning) — COMPLETE and CLOSED — planning artifact `docs/planning/wp_rec_05_rag_integration.md` delivered via PR #87, regular merge commit `e3a9a4572075840e8f1aa71b671ef0dd50dc2eb1`, post-merge verification passed. Planning only; does not authorize implementation or verification.
5. **WP-REC-05** (RAG integration into the AI workflow) — COMPLETE — merged via PR #89 (regular merge commit `86e2d0cd3d6d3eaf889ca6d674829f7ac541778c`, 2026-08-14); strict post-merge verification passed.
6. **WP-REC-05-PROVIDER-IMP** (external chat-provider chain and grounded-output hardening) — COMPLETE — merged via PR #91 (regular merge commit `7d425c1d3f1e92e08d62360c28ced22481136fe7`, 2026-08-14); strict post-merge verification passed. External live interoperability was subsequently demonstrated for OpenRouter `qwen/qwen3.7-flash` via the WP-REC-05-VFY formal rerun (DEC-049); the repository still has no Groq/OpenRouter key or ~USD 5 OpenRouter budget configured for general use.
7. **WP-REC-05-VFY** (bounded AT-006/AT-007 verification) — ACCEPTED — composite of sealed packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02` accepted by the Product Owner 2026-08-15 (DEC-049); AT-006 PASS; AT-007 PASS. Separate from WP-REC-05 (DEC-035); follows WP-REC-05 implementation.
8. **WP-REC-04-DEC** (Phase 6 contract and decomposition) — decision and planning package (DEC-052, Product Owner 2026-08-15); Phase 6 reconnaissance COMPLETE; decomposition `docs/planning/wp_rec_04_decomposition.md`. Documentation-only; completed and incorporated into main through PR #97 (regular merge commit `19d41f75cbaedfb652054fc11e5e46562f9581dc`); post-merge verification passed. WP-REC-04B (audit-event backend foundation) is COMPLETE and incorporated into main through PR #99 (regular merge commit `60574b65aec99bd7b33e24d8ff50cfc9299aad4f`); strict post-merge verification passed. WP-REC-04A (approval-request backend) is COMPLETE and incorporated into main through PR #102 (regular merge commit `6a8ab4447571c9a624a516e72f4a6930f1af3fa5`); strict post-merge verification passed. WP-REC-04C (procurement-task backend) is COMPLETE and incorporated into main through PR #104 (regular merge commit `d92a85a387b387ea0f1262c7f12f5dafb40941d8`); strict post-merge verification passed. WP-REC-04D (Approval Center frontend) is COMPLETE and incorporated into main through PR #106 (regular merge commit `03bea8d96fa48a2d51a1342dc93602a3a6f6ec83`); strict post-merge verification passed. WP-REC-04E (Audit Log frontend) is COMPLETE and incorporated into main through PR #108 (regular merge commit `b4c6fbc8beb96be8807d32e12b5236ce98e4ed38`); strict post-merge verification passed. Phase 6 implementation is now COMPLETE (all five implementation packages incorporated via PRs #99, #102, #104, #106, #108); WP-REC-04-VFY is ACCEPTED (accepted evidence run `wp-rec-04-vfy-20260816-03`, Product Owner acceptance 2026-08-16, DEC-053); AT-009 PASS; AT-010 PASS; AT-011 PASS; AT-012 PASS; Phase 6 CLOSED / ACCEPTED.
9. **Phase 6** (Approval and Audit) — CLOSED / ACCEPTED. Decomposed via WP-REC-04-DEC; WP-REC-04B (audit-event backend foundation) is COMPLETE and incorporated into main through PR #99 (regular merge commit `60574b65aec99bd7b33e24d8ff50cfc9299aad4f`); strict post-merge verification passed. WP-REC-04A (approval-request backend) is COMPLETE and incorporated into main through PR #102 (regular merge commit `6a8ab4447571c9a624a516e72f4a6930f1af3fa5`); strict post-merge verification passed. WP-REC-04C (procurement-task backend) is COMPLETE and incorporated into main through PR #104 (regular merge commit `d92a85a387b387ea0f1262c7f12f5dafb40941d8`); strict post-merge verification passed. WP-REC-04D (Approval Center frontend) is COMPLETE and incorporated into main through PR #106 (regular merge commit `03bea8d96fa48a2d51a1342dc93602a3a6f6ec83`); strict post-merge verification passed. WP-REC-04E (Audit Log frontend) is COMPLETE and incorporated into main through PR #108 (regular merge commit `b4c6fbc8beb96be8807d32e12b5236ce98e4ed38`); strict post-merge verification passed. WP-REC-04-VFY is ACCEPTED (accepted evidence run `wp-rec-04-vfy-20260816-03`, Product Owner acceptance 2026-08-16, DEC-053); AT-009 PASS; AT-010 PASS; AT-011 PASS; AT-012 PASS; Phase 6 is CLOSED / ACCEPTED.
10. **Phase 7** (Public Deployment) — OPEN / IN PROGRESS (DEC-054, 2026-08-17). The authoritative Release 1 / Phase 7 deployment contract and controlled decomposition are defined in `docs/planning/phase_7_deployment_contract.md` (WP-P7-01). The contract records Product Owner deployment decisions PD-1 through PD-12 (with corrected PD-3, PD-3a, and PD-6; PD-12 = Model C single-VPS disposable-staging model, DEC-058; PD-1 host sizing superseded by DEC-057: 2 vCPU / 8 GB RAM / 100 GB SSD), a dependency-ordered work-package decomposition (WP-P7-01 through WP-P7-12 plus WP-P7-CORR-01), staging/production/release gates, a VPS security-hardening contract, and a Hostinger and domain input contract. WP-P7-01 is COMPLETE (contract incorporated via PR #111, merge commit `8e018b2080917c50b5641abbdbd7be0407493677`). WP-P7-02 (deployment/security configuration + Golden RAG / production seed remediation + live embedding gate) is COMPLETE / ACCEPTED — PR #113 (merge commit `728bb107be88e48974ac401e50c26405570a81c3`) and PR #114 (merge commit `c30a06194beda6dc7f36b441e27afd7534b8a947`) merged and post-merge verified; live embedding smoke -03 PASSED (sealed aggregate `a755d37077fa77bd6f688c3551c3dec03c76b00ede3fec46fb7de63acbc5f0ba`); independent evidence review PASSED; Product Owner acceptance 2026-08-18 (DEC-055). WP-P7-03 (Isolated Demo Environment and deterministic reset — reframed by DEC-056, 2026-08-19: the Release 1 Demo is an isolated disposable environment, and "reset" is operator-level destruction/recreation, not an in-app row-deletion API) is COMPLETE / INCORPORATED / POST-MERGE VERIFIED — merged via PR #116 (regular merge commit `e90967f0428230b590cc648273219ffe0925f97f`, 2026-08-19); strict post-merge verification passed. WP-P7-04 (demo account login UX) is COMPLETE / INCORPORATED / POST-MERGE VERIFIED — merged via PR #117 (regular merge commit `a74e6b39bc761446125532cf2fc4f9dfbf58d441`, 2026-08-20); strict post-merge verification passed. WP-P7-05 (release documentation / portfolio / licensing) is COMPLETE / INCORPORATED / POST-MERGE VERIFIED — merged via PR #119 (regular merge commit `ad6a4786bf8a1de90cb23f4adc8dee22a2c5ef57`, 2026-08-20); strict post-merge verification passed. WP-P7-02 through WP-P7-05 have satisfied the package-completion portion of the staging entry gate. The next bounded action before VPS hardening is the WP-P7-CORR-01 correction-package lifecycle (independent review → merge → post-merge verification); PRE-STAGING VPS SECURITY HARDENING (separate operational action required by the authoritative Phase 7 deployment contract; not authorized or performed in this reconciliation) remains blocked until that lifecycle passes. WP-P7-06 — Staging deployment: NOT STARTED. Deployment execution, staging, and production remain NOT STARTED. Release 1 remains NOT READY / NOT DEPLOYED.
11. **Phase 8** (Portfolio Release) — NOT STARTED.

**Accepted sequencing (DEC-044):**

```
WP-REC-05 implementation → separate WP-REC-05-VFY bounded verification
→ separate Product Owner Phase 4 acceptance/closure
```

- **WP-REC-05-VFY** (bounded AT-006/AT-007 verification) — formal execution and accepted PASS evidence for AT-006 and AT-007. Separate from WP-REC-05 (DEC-035). The composite of sealed packages `wp-rec-05-vfy-20260814-01` (aggregate `f37f0ac8…`, exact canonical AT-007 restricted-only Given) and `wp-rec-05-vfy-20260815-02` (aggregate `2ce0ba6f…`, live OpenRouter AT-006 grounded citation + equal-similarity AT-007 discrimination + empty-role fail-closed) was accepted by the Product Owner 2026-08-15 (DEC-049); AT-006 PASS; AT-007 PASS. Phase 4 is CLOSED / ACCEPTED.
- **Formal VFY provider pinning (DEC-048):** DEC-048 specified that the formal WP-REC-05-VFY would run AT-006 and AT-007 against one exact pinned commercial provider/model with automatic provider fallback disabled inside those scenarios; the failover smoke is a separate scenario. The later execution used OpenRouter `qwen/qwen3.7-flash` with automatic fallback disabled.

This is a planning sequence, not an execution authorization. Every future package remains separately authorized. Authorization of one package must not authorize any other.

**WP-REC-03 lifecycle (2026-08-14 reconciliation):** WP-REC-03A through WP-REC-03G are COMPLETE (merged via PRs #63, #65, #72, #73, #74, #78, #80). All Phase 5 implementation packages are delivered. **AT-008 PASS; AT-013 PASS; Phase 5 ACCEPTED** (Product Owner acceptance 2026-08-14, DEC-043; accepted evidence run `wp-rec-03h-phase-c-20260813-02`; durable review `docs/reviews/wp_rec_03h_phase_d_independent_evidence_review.md`, durable acceptance declaration `docs/reviews/wp_rec_03h_phase_d_product_owner_acceptance_declaration.md`). WP-REC-03H Phase C and Phase D are complete; Phase E documentation lifecycle reconciliation is complete through PR #86.

**SP-0B (Runtime migration manifest):** READY but NOT AUTHORIZED. Creation of `forgemind-agent-runtime` is NOT AUTHORIZED. Activation of agent automation is deferred until available on general terms; neither the second repository nor agent automation is a runtime dependency or blocker for Release 1.

---

## What Must NOT Be Started Automatically

Without explicit Product Owner authorization, do not:
- Implement any MVP phase without explicit Product Owner authorization (Phase 7 implementation packages WP-P7-02 through WP-P7-05 are COMPLETE; deployment execution remains NOT STARTED)
- Start SP-0B or create forgemind-agent-runtime
- Copy or move Runtime files
- Access or modify the VPS
- Install dependencies or run migrations
- Create branches, commits, tags, releases, or PRs
- Change Source of Truth or Decision Log
- Perform strategic replanning or architectural redesign

---

## Acceptance Test Status

| AT | Description | Status |
|----|-------------|--------|
| AT-001 | Clean deployment | REQUIRES DEPLOYMENT/ENVIRONMENT VERIFICATION |
| AT-002 | Demo authentication | IMPLEMENTED — requires deployment verification |
| AT-003 | Golden Dataset integrity | ✅ PASS |
| AT-004 | Deterministic risk calculation | ✅ PASS |
| AT-005 | No hidden UI mocks | ✅ PASS |
| AT-006 | RAG retrieval | ✅ PASS — composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02` (Product Owner acceptance 2026-08-15) |
| AT-007 | Document access control | ✅ PASS — composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02` (Product Owner acceptance 2026-08-15) |
| AT-008 | Structured output validation | ✅ PASS — accepted evidence run `wp-rec-03h-phase-c-20260813-02` (Product Owner acceptance 2026-08-14; WP-REC-03C + 03E + 03F) |
| AT-009 | Human approval blocks write | ✅ PASS — accepted evidence run `wp-rec-04-vfy-20260816-03` (Product Owner acceptance 2026-08-16) |
| AT-010 | Approval executes action | ✅ PASS — accepted evidence run `wp-rec-04-vfy-20260816-03` (Product Owner acceptance 2026-08-16) |
| AT-011 | Reject path | ✅ PASS — accepted evidence run `wp-rec-04-vfy-20260816-03` (Product Owner acceptance 2026-08-16) |
| AT-012 | Audit trace completeness | ✅ PASS — accepted evidence run `wp-rec-04-vfy-20260816-03` (Product Owner acceptance 2026-08-16) |
| AT-013 | Model outage | ✅ PASS — accepted evidence run `wp-rec-03h-phase-c-20260813-02` (Product Owner acceptance 2026-08-14; WP-REC-03D + 03E + 03F + 03G) |
| AT-014 | Public HTTPS smoke | REQUIRES DEPLOYMENT/ENVIRONMENT VERIFICATION |
| AT-015 | Demo reset | IMPLEMENTED (WP-P7-03) — requires deployment/environment verification |

**Summary:**
- 11 ATs are PASS: AT-003, AT-004, AT-005, AT-006, AT-007, AT-008, AT-009, AT-010, AT-011, AT-012, AT-013.
- AT-006 is PASS (composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02`, Product Owner acceptance 2026-08-15).
- AT-007 is PASS (composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02`, Product Owner acceptance 2026-08-15).
- AT-008 is PASS (accepted evidence run `wp-rec-03h-phase-c-20260813-02`, Product Owner acceptance 2026-08-14).
- AT-013 is PASS (accepted evidence run `wp-rec-03h-phase-c-20260813-02`, Product Owner acceptance 2026-08-14).
- AT-009, AT-010, AT-011, and AT-012 are PASS (accepted evidence run `wp-rec-04-vfy-20260816-03`, Product Owner acceptance 2026-08-16, DEC-053).
- 3 ATs require deployment/environment verification: AT-001, AT-002, AT-014.
- 1 AT is implemented and requires deployment/environment verification: AT-015.

**AT-006 and AT-007 are PASS** via the accepted composite of sealed packages `wp-rec-05-vfy-20260814-01` and `wp-rec-05-vfy-20260815-02` (Product Owner acceptance 2026-08-15, DEC-049). These are Product Owner decisions based on accepted composite evidence, not inferences from inspection alone.

**WP-REC-03B does not cause any AT to newly pass.** The state machine and engine are foundational; AT coverage accrues in later packages (03C–03G and Phase 6).

---

## Decision Log Status

See `forgemind_project_source_of_truth/08_DECISION_LOG.md` for full history.

**Accepted:**
- DEC-001 through DEC-014, DEC-017, DEC-024, DEC-028, DEC-029, DEC-033
- DEC-034 through DEC-040 (WP-STRAT-01 strategic and technical decisions)
- DEC-041 (WP-ARCH-01 closure)
- DEC-042 (WP-REC-03F D6 reconciler mechanism resolved)
- DEC-043 (WP-REC-03H Phase D acceptance and Phase 5 closure)
- DEC-044 through DEC-046 (WP-REC-05 planning/authorization contracts)
- DEC-047 (WP-REC-05 implementation authorization and incorporation)
- DEC-048 (WP-REC-05 external provider architecture and formal VFY pinning)
- DEC-049 (WP-REC-05-VFY composite-evidence acceptance and AT-006/AT-007 PASS)
- DEC-050 (bounded documentation-only Phase 4 closure package authorization)
- DEC-051 (durable reconciliation-base snapshot convention)
- DEC-052 (Phase 6 approval/audit/procurement contract and WP-REC-04-DEC decomposition)
- DEC-053 (WP-REC-04-VFY evidence acceptance and Phase 6 closure)
- DEC-054 (Phase 7 deployment contract and Release 1 controlled decomposition)
- DEC-055 (WP-P7-02 live embedding evidence acceptance and work-package completion)
- DEC-056 (Isolated disposable Demo Environment and reset boundary)
- SP-0A: Option C approved, repository name `forgemind-agent-runtime` approved

**Proposed (pending PO decision):**
- DEC-015: State management

---

## Agent-Loop Infrastructure (Historical)

Agent-loop infrastructure is a development-time tool for autonomous agent-driven development cycles. It is NOT a ForgeMind end-user feature.

**Status: IMPLEMENTED (WP-AL-1A through WP-AL-1C6)**

All agent-loop work packages are merged to main. The implementation is tested (883 pytest tests, 40 harness scenarios A-AN all PASS). See individual WP docs under `docs/planning/wp_al_*`.

Agent-loop code lives under:
- `scripts/agent-loop/` — implementation, tests, templates
- `.agent-loop/` — schemas, project configuration

Agent-loop is a Runtime candidate for future extraction to `forgemind-agent-runtime` per SP-0A Option C.

---

## Documentation Index

**Current state:**
- This document: `docs/next_steps.md` (you are here)
- Product strategy: `docs/planning/wp_strat_01_product_strategy.md` (WP-STRAT-01)
- Reconnaissance report: `docs/planning/wp_strat_01_reconnaissance.md`
- SP-1 Assessment (historical snapshot): `docs/reviews/sp1_recovery_mvp_separation_assessment.md`
- SP-0A Decision: `docs/planning/sp0a_separation_decision.md`

**Source of Truth:**
- [Product and MVP Scope](../forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md)
- [System Behavior and Data](../forgemind_project_source_of_truth/02_SYSTEM_BEHAVIOR_AND_DATA.md)
- [Definition of Done](../forgemind_project_source_of_truth/03_DEFINITION_OF_DONE.md)
- [Acceptance Tests](../forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md)
- [Deployment and Demo](../forgemind_project_source_of_truth/05_DEPLOYMENT_AND_DEMO.md)
- [Decision Log](../forgemind_project_source_of_truth/08_DECISION_LOG.md)
- [Delivery Roadmap](../forgemind_project_source_of_truth/07_ROADMAP.md)

**Completed phase reports:**
- [Phase 1 Completion Report](phase_1/phase_1_completion_report.md)
- [Phase 3 Completion](planning/phase_3_completion.md)

---

## Next Milestone

**Last Updated:** 2026-08-20
**Reconciliation base snapshot:** main @ `ad6a4786bf8a1de90cb23f4adc8dee22a2c5ef57` (PR #119 merge commit; snapshot semantics per DEC-051)

**Completed work:**
1. WP-STRAT-01 is completed and merged via PR #67 (merge commit `77d359c`).
2. WP-ARCH-01 is completed and closed — planning artifact accepted via PO decision 2026-08-09 (DEC-041, PR #69 merge commit `3a2bc26`). No execution required. The optional agent-onboarding document is deferred.
3. WP-REC-03A through WP-REC-03G are COMPLETE and MERGED via PRs #63, #65, #72, #73, #74, #78, #80 (2026-08-09 through 2026-08-12). Phase 5 implementation packages are all delivered. **AT-008 PASS; AT-013 PASS; Phase 5 ACCEPTED** (Product Owner acceptance 2026-08-14, DEC-043; accepted evidence run `wp-rec-03h-phase-c-20260813-02`).

**Current implementation status:**
- **Phase 4 (Knowledge and RAG):** COMPLETE / ACCEPTED — AT-006 PASS; AT-007 PASS (composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02`, Product Owner acceptance 2026-08-15, DEC-049); WP-REC-05 CLOSED; WP-REC-05-PROVIDER-IMP CLOSED; WP-REC-05-VFY ACCEPTED
- **Phase 5 (WP-REC-03A–03G):** COMPLETE / ACCEPTED — all implementation packages merged; AT-008 and AT-013 formally accepted (Product Owner acceptance 2026-08-14)
- **AT-006:** PASS — composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02`
- **AT-007:** PASS — composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02`
- **AT-008:** PASS — accepted evidence run `wp-rec-03h-phase-c-20260813-02`
- **AT-013:** PASS — accepted evidence run `wp-rec-03h-phase-c-20260813-02`
- **WP-REC-05 (RAG integration into the AI workflow):** COMPLETE — merged via PR #89 (regular merge commit `86e2d0cd3d6d3eaf889ca6d674829f7ac541778c`, 2026-08-14); strict post-merge verification passed
- **WP-REC-05-PROVIDER-IMP (external chat-provider chain and grounded-output hardening):** COMPLETE — merged via PR #91 (regular merge commit `7d425c1d3f1e92e08d62360c28ced22481136fe7`, 2026-08-14); strict post-merge verification passed; external live interoperability subsequently demonstrated for OpenRouter `qwen/qwen3.7-flash` via the WP-REC-05-VFY formal rerun (DEC-049); the repository still has no Groq/OpenRouter key or ~USD 5 OpenRouter budget configured for general use

**Planning package status:**
- WP-REC-05-DEC (RAG integration decomposition and planning) — COMPLETE and CLOSED (planning artifact delivered via PR #87, regular merge commit `e3a9a4572075840e8f1aa71b671ef0dd50dc2eb1`, post-merge verification passed; originally authorized by DEC-044, 2026-08-14).
- WP-REC-04-DEC (Phase 6 contract and decomposition) — decision and planning package (DEC-052, Product Owner 2026-08-15); Phase 6 reconnaissance COMPLETE; decomposition `docs/planning/wp_rec_04_decomposition.md`. Documentation-only; completed and incorporated into main through PR #97 (regular merge commit `19d41f75cbaedfb652054fc11e5e46562f9581dc`); post-merge verification passed. WP-REC-04B (audit-event backend foundation) is COMPLETE and incorporated into main through PR #99 (regular merge commit `60574b65aec99bd7b33e24d8ff50cfc9299aad4f`); strict post-merge verification passed. WP-REC-04A (approval-request backend) is COMPLETE and incorporated into main through PR #102 (regular merge commit `6a8ab4447571c9a624a516e72f4a6930f1af3fa5`); strict post-merge verification passed. WP-REC-04C (procurement-task backend) is COMPLETE and incorporated into main through PR #104 (regular merge commit `d92a85a387b387ea0f1262c7f12f5dafb40941d8`); strict post-merge verification passed. WP-REC-04D (Approval Center frontend) is COMPLETE and incorporated into main through PR #106 (regular merge commit `03bea8d96fa48a2d51a1342dc93602a3a6f6ec83`); strict post-merge verification passed. WP-REC-04E (Audit Log frontend) is COMPLETE and incorporated into main through PR #108 (regular merge commit `b4c6fbc8beb96be8807d32e12b5236ce98e4ed38`); strict post-merge verification passed. Phase 6 implementation is now COMPLETE (all five implementation packages incorporated via PRs #99, #102, #104, #106, #108); WP-REC-04-VFY is ACCEPTED (accepted evidence run `wp-rec-04-vfy-20260816-03`, Product Owner acceptance 2026-08-16, DEC-053); AT-009 PASS; AT-010 PASS; AT-011 PASS; AT-012 PASS; Phase 6 CLOSED / ACCEPTED.

**Not authorized:**
- Phase 7 deployment execution (staging/production) — NOT STARTED
- SP-0B and forgemind-agent-runtime creation
- Agent automation activation (deferred)

The accepted sequence was WP-REC-05 implementation first, separate WP-REC-05-VFY verification second. WP-REC-05 implementation is COMPLETE (merged via PR #89, merge commit `86e2d0cd3d6d3eaf889ca6d674829f7ac541778c`) and WP-REC-05-PROVIDER-IMP is COMPLETE (merged via PR #91, merge commit `7d425c1d3f1e92e08d62360c28ced22481136fe7`); strict post-merge verification passed for both. WP-REC-05-VFY is ACCEPTED (composite of sealed packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02`, Product Owner acceptance 2026-08-15, DEC-049); AT-006 PASS; AT-007 PASS; Phase 4 CLOSED / ACCEPTED. WP-P7-02 through WP-P7-05 are COMPLETE / INCORPORATED / POST-MERGE VERIFIED. Active implementation package: WP-P7-CORR-01 (pre-staging architecture / resource correction, DEC-057 + DEC-058; Draft PR on branch `fix/wp-p7-corr-01-pre-staging-architecture`, base main @ `9b4e77119cec625389ff3f3afef198038b5f07df`). The next bounded action before VPS hardening is the WP-P7-CORR-01 correction-package lifecycle (independent review → merge → post-merge verification); PRE-STAGING VPS SECURITY HARDENING (separate operational action required by the authoritative Phase 7 deployment contract; not authorized or performed in this reconciliation) remains blocked until that lifecycle passes. WP-P7-06 — Staging deployment: NOT STARTED. No implementation package other than WP-P7-CORR-01 is authorized or inferred.
