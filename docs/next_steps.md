# ForgeMind — Next Steps

**Last Updated:** 2026-08-09
**Current Status:** Development in progress — Release 1 NOT READY
**Authoritative baseline:** `origin/main` @ `47acbd87acf78df9ad3867f0a7da70461312da23`

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
| Phase 4: Knowledge and RAG | PARTIALLY COMPLETE | Substantial implementation exists (document ingestion, pgvector index, retrieval with citations, role-filtered retrieval, DocumentPermission model); formal AT-006/AT-007 PASS evidence incomplete |
| Authentication + RBAC | COMPLETE | JWT auth, 5 demo accounts (manager/procurement/engineer/admin/auditor) |
| AI provider adapter (chat/reasoning) | COMPLETE | OpenAI-compatible ChatProvider adapter, merged via PR #63 |
| WP-REC-03B: Workflow/state-machine foundation | COMPLETE | Explicit state machine (7 states, immutable transition table), WorkflowEngine with conditional UPDATE concurrency safety, WorkflowRun/WorkflowStep/Recommendation ORM models, Alembic migration, Pydantic run/step schemas, unit and integration tests — merged via PR #65 |
| AT-003 (Golden Dataset) | PASS | Seed produces deterministic RISK-001/002/003 |
| AT-004 (Deterministic risk) | PASS | Risk engine returns exact expected values |
| AT-005 (No hidden mocks) | PASS | UI displays real backend data |

**Phase 4 is PARTIALLY COMPLETE.** Substantial RAG and role-filtering implementation exists (retriever, citations, DocumentPermission model, role-filtered SQL query, server-side role derivation, unauthorized-role test). The remaining gap is formal AT-006/AT-007 PASS evidence and RAG integration into the AI workflow — not the absence of document access control implementation. This is a documentation/status and acceptance-evidence contradiction, not a false technical foundation. Phase 5 builds on real, implemented infrastructure.

**WP-REC-03B is a foundation package.** It delivers the workflow state machine, engine, models, and migration — but does NOT deliver end-to-end AI workflow execution. The following remain incomplete and are owned by subsequent packages (03C–03G): structured-output validation, automatic provider retry/outage handling, workflow-run detail API and recommendation UI, backend start/retry API + ARQ worker + reconciler, and frontend start/retry UI interaction. No acceptance test newly passes as a result of 03B alone.

### ❌ NOT IMPLEMENTED (Release 1 blockers)

| Capability | Required For | Phase |
|-----------|--------------|-------|
| Structured output validation | AT-008 | Phase 5 (WP-REC-03C) |
| Model outage handling | AT-013 | Phase 5 (WP-REC-03D) |
| Workflow-run detail API + recommendation UI | AT-008 trace, FR-07 | Phase 5 (WP-REC-03E) |
| Backend workflow start/retry API + ARQ worker | AT-008 full PASS, AT-013 backend | Phase 5 (WP-REC-03F) |
| Frontend start/retry UI interaction | AT-013 UI clauses | Phase 5 (WP-REC-03G) |
| Formal AT-006/AT-007 verification | Achieve AT-006 PASS, AT-007 PASS | Bounded verification package (SD-2, DEC-035) — separate from WP-REC-05 |
| RAG integration into AI workflow | Gate C citations | WP-REC-05 — RAG integration into the AI workflow; Phase 4 closure also depends on the separately authorized AT-006/AT-007 verification package. Positioned after WP-REC-03C–03G and before Phase 6 (SD-4) |
| Approval service | AT-009, AT-010, AT-011 | Phase 6 |
| Audit event service | AT-012 | Phase 6 |
| Procurement task service | AT-010 | Phase 6 |
| Approval Center UI | AT-009, AT-010, AT-011 | Phase 6 |
| Audit log UI | AT-012 | Phase 6 |
| Demo reset | AT-015 | Phase 7 |
| Rate limiting | Gate D | Phase 7 |
| Backup/restore | Gate E | Phase 7 |
| Public HTTPS deployment | AT-014 | Phase 7 |
| Operational runbooks | Gate E | Phase 7 |

### Current MVP completion

Two of five condensed MVP milestones have implementation evidence (step 1 verified by passing integration tests; step 2 has implementation and a test file but formal AT-006/AT-007 PASS evidence is incomplete). The canonical 13-step Golden Scenario (defined in `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md` §2) remains incomplete. Steps 3–5 of the condensed milestones (AI recommendation → approval → procurement → audit → deployment) are not implemented. WP-REC-03B provides the foundational state machine and engine for step 3 but does not complete the end-to-end AI workflow execution path.

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
2. **WP-ARCH-01** (Architecture Hygiene and Agent Onboarding) — NOT AUTHORIZED. Follows WP-STRAT-01. Requires separate Product Owner authorization.
3. **WP-REC-03C → 03D → 03E → 03F → 03G** (Phase 5 AI Workflow) — NOT AUTHORIZED. Sequence preserved per SD-3. Each requires separate authorization. Reassessment after WP-STRAT-01 and WP-ARCH-01.
4. **WP-REC-05** (RAG integration into the AI workflow) — NOT AUTHORIZED. Positioned after WP-REC-03C–03G and before Phase 6 per SD-4.
5. **Phase 6** (Approval and Audit) — NOT STARTED.
6. **Phase 7** (Public Deployment) — NOT STARTED.
7. **Phase 8** (Portfolio Release) — NOT STARTED.

**Required package with timing not yet established:**

- **Bounded AT-006/AT-007 verification package** — formal execution and accepted PASS evidence for AT-006 and AT-007. Separate from WP-REC-05 (DEC-035). Its execution timing and position relative to WP-REC-05 and Phase 6 remain intentionally undecided. NOT AUTHORIZED. Authorization of any package does not authorize the verification package. Phase 4 cannot become COMPLETE until its unchanged exit criteria, including accepted AT-006/AT-007 PASS evidence, are satisfied.

This is a planning sequence, not an execution authorization. Every future package remains separately authorized. Authorization of one package must not authorize any other.

**WP-REC-03C through 03G remain NOT AUTHORIZED.** Their content, priority, and authorization will be reassessed only after WP-STRAT-01 and WP-ARCH-01 are complete.

**SP-0B (Runtime migration manifest):** READY but NOT AUTHORIZED. Creation of `forgemind-agent-runtime` is NOT AUTHORIZED. Activation of agent automation is deferred until available on general terms; neither the second repository nor agent automation is a runtime dependency or blocker for Release 1.

---

## What Must NOT Be Started Automatically

Without explicit Product Owner authorization, do not:
- Implement any MVP phase (Phase 5, 6, or 7)
- Start WP-ARCH-01
- Start or redesign WP-REC-03C through 03G
- Start WP-REC-05 or the bounded AT-006/AT-007 verification package
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
| AT-006 | RAG retrieval | IMPLEMENTED — NOT VERIFIED AS PASS |
| AT-007 | Document access control | IMPLEMENTED AT SERVICE/API LEVEL — NOT VERIFIED AS AT-007 PASS |
| AT-008 | Structured output validation | NOT IMPLEMENTED |
| AT-009 | Human approval blocks write | NOT IMPLEMENTED |
| AT-010 | Approval executes action | NOT IMPLEMENTED |
| AT-011 | Reject path | NOT IMPLEMENTED |
| AT-012 | Audit trace completeness | NOT IMPLEMENTED |
| AT-013 | Model outage | NOT IMPLEMENTED |
| AT-014 | Public HTTPS smoke | REQUIRES DEPLOYMENT/ENVIRONMENT VERIFICATION |
| AT-015 | Demo reset | NOT IMPLEMENTED |

**Summary:**
- 3 ATs are PASS: AT-003, AT-004, AT-005.
- 2 ATs have relevant implementation but lack accepted PASS evidence: AT-006, AT-007.
- 3 ATs require deployment/environment verification: AT-001, AT-002, AT-014.
- 7 ATs require capabilities that are not implemented: AT-008, AT-009, AT-010, AT-011, AT-012, AT-013, AT-015.

**AT-006 and AT-007 must not be inferred as PASS from inspection alone.** Formal execution and accepted evidence are required via a bounded verification package (SD-2). This package does not authorize that verification.

**WP-REC-03B does not cause any AT to newly pass.** The state machine and engine are foundational; AT coverage accrues in later packages (03C–03G and Phase 6).

---

## Decision Log Status

See `forgemind_project_source_of_truth/08_DECISION_LOG.md` for full history.

**Accepted:**
- DEC-001 through DEC-014, DEC-017, DEC-024, DEC-028, DEC-029, DEC-033
- DEC-034 through DEC-040 (WP-STRAT-01 strategic and technical decisions)
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

**Next Milestone:** Product Owner decision required:
1. **Review and approve/reject** the WP-STRAT-01 documentation draft PR (`docs/wp-strat-01-product-strategy`).
2. **If merged:** authorize **WP-ARCH-01** (Architecture Hygiene and Agent Onboarding) — a separate controlled execution package.
3. **After WP-ARCH-01:** reassess the content, priority, and authorization of **WP-REC-03C** — implementation remains paused and unauthorized until reassessed and separately authorized.
4. **WP-REC-03C through 03G** remain **NOT AUTHORIZED**. WP-REC-05 (RAG integration into the AI workflow) and the bounded AT-006/AT-007 verification package remain NOT AUTHORIZED as separate packages — authorization of one must not authorize the other. SP-0B and forgemind-agent-runtime creation remain NOT AUTHORIZED. Agent automation activation remains deferred.
