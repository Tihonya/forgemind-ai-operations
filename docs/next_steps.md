# ForgeMind — Next Steps

**Last Updated:** 2026-08-08
**Current Status:** Development in progress — Release 1 NOT READY
**Authoritative baseline:** `origin/main` @ `417c8688facad539508d435d8110970798d0cc30`

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

**Assessment evidence:** `docs/reviews/sp1_recovery_mvp_separation_assessment.md` (SP-1 assessment, 2026-08-08)

---

## Current Implementation Status

### ✅ IMPLEMENTED

| Capability | Status | Evidence |
|-----------|--------|----------|
| Phase 1: Running Skeleton | COMPLETE | FastAPI + PostgreSQL + Redis + ARQ, 239 backend tests |
| Phase 2: Synthetic ERP Core | COMPLETE | 14 business tables, seed generator, deterministic risk engine |
| Phase 3: Core UI | COMPLETE | Dashboard, supply risk list, supply risk detail |
| Phase 4: Knowledge and RAG | COMPLETE | Document ingestion, pgvector index, retrieval with citations |
| Authentication + RBAC | COMPLETE | JWT auth, 5 demo accounts (manager/procurement/engineer/admin/auditor) |
| AT-003 (Golden Dataset) | PASS | Seed produces deterministic RISK-001/002/003 |
| AT-004 (Deterministic risk) | PASS | Risk engine returns exact expected values |
| AT-005 (No hidden mocks) | PASS | UI displays real backend data |
| AT-006 (RAG retrieval) | PASS | Citations include document_id, version, chunk_id |

### ❌ NOT IMPLEMENTED (Release 1 blockers)

| Capability | Required For | Phase |
|-----------|--------------|-------|
| AI provider adapter | AT-008, AT-013 | Phase 5 |
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

### Current MVP completion: ~40%

Steps 1–2 of the Golden Scenario work (deterministic risk calculation + RAG retrieval). Steps 3–5 (AI recommendation → approval → procurement → audit → deployment) are not implemented.

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

**NONE beyond this documentation recovery.**

Previous authorization (WP-REC-01 + WP-REC-02): COMPLETE — this documentation update.

**Next authorized work package requires separate Product Owner decision.**

Recommended candidate: **WP-REC-03: MVP Phase 5 (AI Workflow)** — implement AI provider adapter, workflow engine, structured output validation, model outage handling. See SP-1 assessment §18 for full WP definitions.

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
| AT-006 | RAG retrieval | ✅ PASS |
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

---

## Decision Log Status

See `forgemind_project_source_of_truth/08_DECISION_LOG.md` for full history.

**Accepted:**
- DEC-001 through DEC-012, DEC-014, DEC-017, DEC-024, DEC-028, DEC-029, DEC-033
- SP-0A: Option C approved, repository name `forgemind-agent-runtime` approved

**Proposed (pending PO decision):**
- DEC-013: Workflow orchestration (custom state machine)
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
- SP-1 Assessment: `docs/reviews/sp1_recovery_mvp_separation_assessment.md`
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

**Next Milestone:** Product Owner decision on WP-REC-03 (MVP Phase 5: AI Workflow).
