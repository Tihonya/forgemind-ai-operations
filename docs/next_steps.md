# ForgeMind — Next Steps

**Last Updated:** 2026-08-09
**Current Status:** Development in progress — Release 1 NOT READY
**Authoritative baseline:** `origin/main` @ `5c86000046ea265c799dab05d6e23601d0fe79c0`

---

## What is ForgeMind?

ForgeMind is a web platform for AI-assisted supply chain risk assessment in engineering and manufacturing environments. **Release 1 is a public portfolio MVP** demonstrating one complete vertical scenario: **Production Plan Supply Risk Review**.

**Release 1 deliverables:**
- **Live Demo:** Public HTTPS deployment on Product Owner's VPS
- **Source Code:** Public GitHub repository (this repo)
- **Data policy:** Synthetic data only — no real corporate or military systems

**Target reviewer journey:**
CV → Live Demo → complete working scenario (3–5 minutes) → inspect results and state transitions → open GitHub → understand architecture, implementation, tests, deployment, and limitations.

**Canonical Source of Truth:** `forgemind_project_source_of_truth/` (9 documents, 00–08)

**Assessment evidence:** `docs/reviews/sp1_recovery_mvp_separation_assessment.md` (SP-1 assessment, 2026-08-08). This assessment is a time-scoped historical snapshot. Earlier status classifications in the assessment (e.g., AT-006 "PARTIAL") reflect the state at assessment time and are not canonical current-state authorization. Current acceptance-test status is reported in the table below.

---

## Current Implementation Status

### ✅ IMPLEMENTED

| Capability | Status | Evidence |
|-----------|--------|----------|
| Phase 1: Running Skeleton | COMPLETE | FastAPI + PostgreSQL + Redis + ARQ (Phase 1 baseline: 239 backend tests; additional tests added in later phases) |
| Phase 2: Synthetic ERP Core | COMPLETE | 14 business tables, seed generator, deterministic risk engine |
| Phase 3: Core UI | COMPLETE | Dashboard, supply risk list, supply risk detail |
| Phase 4: Knowledge and RAG | COMPLETE | Document ingestion, pgvector index, retrieval with citations |
| Authentication + RBAC | COMPLETE | JWT auth, 5 demo accounts (manager/procurement/engineer/admin/auditor) |
| AI provider adapter (chat/reasoning) | COMPLETE | OpenAI-compatible ChatProvider adapter, merged via PR #63 |
| AT-003 (Golden Dataset) | PASS | Seed produces deterministic RISK-001/002/003 |
| AT-004 (Deterministic risk) | PASS | Risk engine returns exact expected values |
| AT-005 (No hidden mocks) | PASS | UI displays real backend data |
| AT-006 (RAG retrieval) | NOT VERIFIED IN THIS REVIEW | Integration test `test_at006_rag_retrieval.py` exists; requires live PostgreSQL database; was skipped in review environment due to DB unavailability |

### ❌ NOT IMPLEMENTED (Release 1 blockers)

| Capability | Required For | Phase |
|-----------|--------------|-------|
| Workflow engine | AT-007, AT-012 | Phase 5 |
| Structured output validation | AT-008 | Phase 5 |
| Model outage handling | AT-013 | Phase 5 |
| Approval service | AT-009, AT-010, AT-011 | Phase 6 |
| Audit event service | AT-012 | Phase 6 |
| Procurement task service | AT-010 | Phase 6 |
| Approval Center UI | AT-009, AT-010, AT-011 | Phase 6 |
| Workflow run detail UI | AT-007, AT-012 | Phase 5 |
| Audit log UI | AT-012 | Phase 6 |
| Demo reset | AT-015 | Phase 7 |
| Rate limiting | Gate D | Phase 7 |
| Backup/restore | Gate E | Phase 7 |
| Public HTTPS deployment | AT-014 | Phase 7 |
| Operational runbooks | Gate E | Phase 7 |

### Current MVP completion

Two of five condensed MVP milestones have implementation evidence (step 1 verified by passing integration tests; step 2 has implementation and a test file but the integration test requires a live database and was not executed in this review). The canonical 13-step Golden Scenario (defined in `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md` §2) remains incomplete. Steps 3–5 of the condensed milestones (AI recommendation → approval → procurement → audit → deployment) are not implemented.

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

## Currently Authorized Work

**DEC-013 documentation finalization** (branch `docs/dec-013-explicit-state-machine`). Product Owner directed DEC-013 acceptance and project-state synchronization on 2026-08-09. This is documentation-only: no WP-REC-03B implementation code is started.

PR #61 (WP-REC-01/02) is **MERGED** at `a859c0d0fbee721ad0ea44a00682370d3da9355f` (two-parent merge commit, 2026-08-08). WP-REC-01/02 are COMPLETE.

PR #62 (WP-REC-03-DEC) is **MERGED** at `1bc79ca55e86311d2f042dd830163896ebc32275`. WP-REC-03-DEC is COMPLETE. The decomposition plan decomposes WP-REC-03 (MVP Phase 5: AI Workflow) into seven small, separately authorizable implementation packages (WP-REC-03A through 03G) plus one decision gate (DEC-013). See `docs/planning/wp_rec_03_decomposition.md` for the full plan.

PR #63 (WP-REC-03A) is **MERGED** at `5c86000046ea265c799dab05d6e23601d0fe79c0` (merge commit, 2026-08-09). WP-REC-03A is COMPLETE. The OpenAI-compatible chat provider adapter (`backend/app/ai/provider/`) is live on main.

**DEC-013 (workflow orchestration): ACCEPTED.** Product Owner accepted on 2026-08-09. ForgeMind will use its own explicit application-owned workflow state machine. LangGraph is not introduced. ARQ + Redis (DEC-011) remains the background dispatch/execution mechanism. Domain workflow state is not inferred from ARQ job state. See `forgemind_project_source_of_truth/08_DECISION_LOG.md` DEC-013 for the full decision.

**Next implementation package:** WP-REC-03B (Workflow/State-Machine Foundation) — **NOT YET AUTHORIZED**. The DEC-013 decision gate (WP-REC-03-DEC-GATE-1) is now satisfied. The remaining blocker is explicit Product Owner authorization to implement WP-REC-03B. WP-REC-03C through 03G remain **unauthorized** — each requires separate explicit Product Owner authorization before any implementation begins.

**SP-0B (Runtime migration manifest):** READY but NOT AUTHORIZED. Creation of `forgemind-agent-runtime` is NOT AUTHORIZED — not postponed merely because agent automation is unavailable. Activation of agent automation is deferred until available on general terms; neither the second repository nor agent automation is a runtime dependency or blocker for Release 1.

---

## What Must NOT Be Started Automatically

Without explicit Product Owner authorization, do not:
- Implement any MVP phase (Phase 5, 6, or 7)
- Start SP-0B or create forgemind-agent-runtime
- Copy or move Runtime files
- Access or modify the VPS
- Install dependencies or run migrations
- Create branches, commits, tags, releases, or PRs
- Change Source of Truth or Decision Log

---

## Acceptance Test Status

| AT | Description | Status |
|----|-------------|--------|
| AT-001 | Clean deployment | NOT TESTED (no VPS) |
| AT-002 | Demo authentication | IMPLEMENTED (not tested on VPS) |
| AT-003 | Golden Dataset integrity | ✅ PASS |
| AT-004 | Deterministic risk calculation | ✅ PASS |
| AT-005 | No hidden UI mocks | ✅ PASS |
| AT-006 | RAG retrieval | ⚠️ TEST EXISTS — NOT VERIFIED IN THIS REVIEW (requires live database) |
| AT-007 | Document access control | NOT IMPLEMENTED |
| AT-008 | Structured output validation | NOT IMPLEMENTED |
| AT-009 | Human approval blocks write | NOT IMPLEMENTED |
| AT-010 | Approval executes action | NOT IMPLEMENTED |
| AT-011 | Reject path | NOT IMPLEMENTED |
| AT-012 | Audit trace completeness | NOT IMPLEMENTED |
| AT-013 | Model outage | NOT IMPLEMENTED |
| AT-014 | Public HTTPS smoke | NOT TESTED |
| AT-015 | Demo reset | NOT IMPLEMENTED |

**8 of 15 ATs cannot pass.** All require Phases 5–7 implementation.
**1 AT (AT-006) has a test file but was not executed** in this review environment due to integration database unavailability. The test is skipped when the database is unavailable.

---

## Decision Log Status

See `forgemind_project_source_of_truth/08_DECISION_LOG.md` for full history.

**Accepted:**
- DEC-001 through DEC-012, DEC-013, DEC-014, DEC-017, DEC-024, DEC-028, DEC-029, DEC-033
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

**Next Milestone:** Product Owner decision required:
1. **Immediate decision:** review and approve/reject the DEC-013 documentation draft PR (`docs/dec-013-explicit-state-machine`).
2. **If merged:** decide whether to authorize WP-REC-03B (Workflow/State-Machine Foundation) — the DEC-013 decision gate (WP-REC-03-DEC-GATE-1) is now satisfied; the remaining blocker is implementation authorization.
3. **Implementation authorization:** WP-REC-03B through 03G remain **unauthorized** until separately approved. SP-0B and forgemind-agent-runtime creation remain NOT AUTHORIZED. Agent automation activation remains deferred.
