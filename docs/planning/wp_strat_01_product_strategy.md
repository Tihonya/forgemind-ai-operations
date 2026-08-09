# WP-STRAT-01 — Product Strategy and Release 1 Alignment

**Status:** COMPLETED — documentation-only mutation package
**Date:** 2026-08-09
**Baseline:** origin/main @ `47acbd87acf78df9ad3867f0a7da70461312da23`
**Branch:** `docs/wp-strat-01-product-strategy`
**Authority:** Product Owner approved the remediated reconnaissance report and accepted decisions SD-1 through SD-5 and TD-4/TD-5 on 2026-08-09.

---

## 1. Document Purpose, Authority, and Relationship to Source of Truth

This document is the canonical product-strategy reference for ForgeMind Release 1. It records accepted Product Owner decisions, defines the Release 1 product boundary, maps the remaining delivery sequence, and aligns all status documents to a consistent classification.

**Authority:** This document does not override the Source of Truth. It references and is subordinate to:

1. `forgemind_project_source_of_truth/03_DEFINITION_OF_DONE.md`
2. `forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md`
3. `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md`
4. `forgemind_project_source_of_truth/02_SYSTEM_BEHAVIOR_AND_DATA.md`
5. `forgemind_project_source_of_truth/05_DEPLOYMENT_AND_DEMO.md`
6. `forgemind_project_source_of_truth/06_AI_AGENT_EXECUTION_RULES.md`
7. `forgemind_project_source_of_truth/07_ROADMAP.md`
8. `forgemind_project_source_of_truth/08_DECISION_LOG.md`

The Source of Truth remains authoritative for product scope, acceptance tests, Definition of Done, system behavior, deployment, and AI agent execution rules. This strategy document records accepted decisions and aligns status classifications.

**Reconnaissance evidence:** Detailed implementation evidence is recorded in the reconnaissance report: `docs/planning/wp_strat_01_reconnaissance.md`. This document summarizes and references it; it does not duplicate the full 849-line report.

---

## 2. Current Product Definition

ForgeMind AI Operations is a web platform for AI-assisted supply chain risk assessment in engineering and manufacturing environments. It is a **partially implemented portfolio MVP** demonstrating one vertical scenario: Production Plan Supply Risk Review.

The MVP is explicitly scoped to one vertical scenario. The Source of Truth prohibits expanding into a general enterprise AI platform.

**Evidence:**
- SoT 00_PROJECT_CHARTER.md §1: "AI-assisted supply risk analysis for engineering and manufacturing operations."
- SoT 01_PRODUCT_AND_MVP_SCOPE.md §1: "web-платформа для контрольованого AI-assisted аналізу ризиків постачання."
- HERMES.md §"Current product boundary": "The MVP is one vertical scenario: Supply Risk Intelligence."
- DEC-002 (Accepted): "Перший реліз реалізує Supply Risk Intelligence, а не повну AI Operations Platform."

---

## 3. Target Audiences

### 3.1 Primary target user (product context)

**Production Manager** — views production plan supply risks, triggers analysis, receives AI recommendations, approves procurement actions.

**Evidence:** SoT 00 §5; SoT 01 §2 Golden Scenario; DEC-028.

### 3.2 Secondary users (product context)

| Role | Demo account | Purpose |
|------|-------------|---------|
| Procurement Specialist | procurement.demo | Receives draft procurement tasks |
| Engineer | engineer.demo | Views technical documents and alternatives |
| AI Administrator | admin.demo | Controls models, runs, errors, policies |
| Auditor | auditor.demo | Reviews execution trace, no write access |

### 3.3 Primary audience (portfolio context)

**Recruiters and technical reviewers** evaluating AI-assisted industrial workflow capabilities.

**Evidence:** README.md §"Target audience"; SoT 00 §7.

### 3.4 Secondary audience (portfolio context)

The Product Owner — using ForgeMind as a CV/portfolio artifact demonstrating full-stack AI engineering capability.

---

## 4. Accepted Release 1 Framing

> **"Controlled AI-assisted Supply Risk Intelligence portfolio MVP demonstrating one complete, auditable, human-approved vertical workflow."**

This framing emphasizes:
- **Controlled** — deterministic code owns arithmetic, quantities, severity, constraints, and state transitions.
- **AI-assisted** — the LLM explains, summarizes, and recommends; it does not compute deterministic values or make autonomous decisions.
- **Auditable** — every workflow step is traceable by correlation ID.
- **Human-approved** — no write action executes without explicit human approval.
- **One complete vertical workflow** — Supply Risk Intelligence, not a general platform.

**Source:** SD-5 (accepted by Product Owner 2026-08-09, recorded in 08_DECISION_LOG.md).

---

## 5. Release 1 Product Boundary

Release 1 = the complete Golden Scenario (13 steps from SoT 01 §2) deployed to a public VPS with HTTPS, backed by synthetic data, with all 15 acceptance tests passing and all 6 Definition of Done gates satisfied.

### What Release 1 is NOT

- Not a general-purpose AI platform (DEC-002).
- Not connected to real ERP/corporate/military systems (DEC-003, SoT 00 §6).
- Not dependent on agent-loop runtime (development-time tool only).
- Not a multi-tenant SaaS (SoT 00 §6 out-of-scope).
- Not production-grade high availability (SoT 00 §6 out-of-scope).

---

## 6. Required Release 1 Capabilities

| Capability | Golden Scenario step(s) | AT(s) | Phase | Current status |
|-----------|------------------------|-------|-------|----------------|
| Deterministic risk calculation | Steps 3–4 | AT-003, AT-004, AT-005 | Phase 2 | COMPLETE (AT PASS) |
| Authentication + RBAC | Step 1 | AT-002 | Phase 2 | COMPLETE (requires deployment verification) |
| Dashboard + Supply Risk UI | Steps 1–4, 8 (deterministic) | AT-005 | Phase 3 | COMPLETE (AT PASS) |
| RAG retrieval with citations | Step 6 | AT-006 | Phase 4 | IMPLEMENTED — NOT VERIFIED AS PASS |
| Document access control | Step 6 (restricted docs) | AT-007 | Phase 4 / WP-REC-05 | IMPLEMENTED AT SERVICE/API LEVEL — NOT VERIFIED AS AT-007 PASS |
| AI provider adapter | Step 5 | — | Phase 5 (03A) | COMPLETE |
| Workflow state machine + engine | Steps 5–7 | — | Phase 5 (03B) | COMPLETE |
| Structured-output validation | Step 7 | AT-008 | Phase 5 (03C) | NOT IMPLEMENTED |
| Provider outage handling | Resilience | AT-013 | Phase 5 (03D) | NOT IMPLEMENTED |
| Workflow-run detail API + recommendation UI | Step 8 (AI part) | FR-07 | Phase 5 (03E) | NOT IMPLEMENTED |
| Workflow start/retry API + ARQ worker | Step 5 (start) | AT-008, AT-013 | Phase 5 (03F) | NOT IMPLEMENTED |
| Frontend start/retry UI | Step 5 (user action) | AT-013 | Phase 5 (03G) | NOT IMPLEMENTED |
| Approval service + models | Steps 9–11 | AT-009, AT-010, AT-011 | Phase 6 | NOT IMPLEMENTED |
| Audit event service | Step 13 | AT-012 | Phase 6 | NOT IMPLEMENTED |
| Procurement task service | Step 12 | AT-010 | Phase 6 | NOT IMPLEMENTED |
| Approval Center UI | Steps 9–11 | AT-009, AT-010, AT-011 | Phase 6 | NOT IMPLEMENTED |
| Audit Log UI | Step 13 | AT-012 | Phase 6 | NOT IMPLEMENTED |
| Public HTTPS deployment | — | AT-001, AT-014 | Phase 7 | NOT STARTED |
| Demo reset | — | AT-015 | Phase 7 | NOT IMPLEMENTED |
| Rate limiting | — | Gate D | Phase 7 | NOT IMPLEMENTED |
| Backup/restore | — | Gate E | Phase 7 | NOT IMPLEMENTED |
| Operational runbooks | — | Gate E | Phase 7 | NOT IMPLEMENTED |

---

## 7. Explicitly Deferred Capabilities

| Capability | Rationale | Owner / Phase |
|-----------|-----------|---------------|
| Agent-loop runtime separation (SP-0B) | Zero runtime coupling; development-time tool only | Separate track; not a Release 1 blocker |
| forgemind-agent-runtime repository creation | NOT AUTHORIZED; not a Release 1 blocker | Separate approval required |
| Agent automation activation | Deferred until available on general terms | Not a Release 1 dependency |
| DEC-015 permanent state management (Zustand) | React hooks + TanStack Query sufficient for MVP | Revisit post-Phase 6 |
| Charts library (DEC-016) | Text-based widgets sufficient for MVP demo | Not a blocker for WP-REC-03C |
| Reranker (DEC-019) | pgvector similarity sufficient for synthetic data MVP | Post-MVP optimization |
| Object storage (DEC-020) | Synthetic documents are small; PostgreSQL text/jsonb sufficient | Not needed for MVP |
| React Flow for workflow trace (DEC-021) | Workflow steps are sequential; timeline is simpler | Not needed for MVP |
| All Post-MVP backlog items | Explicitly excluded by SoT 00 §6 and SoT 01 §5 | Post-Release 1 |

---

## 8. Current Demonstrable Journey

A reviewer can complete the following flow TODAY:

1. Open application → see login page with synthetic-data notice
2. Login as manager.demo → JWT auth, redirect to dashboard
3. Dashboard shows: active plan PLAN-2026-W31, status EXECUTING, 3 total risks, severity breakdown
4. Navigate to Supply Risk Analysis → see 3 risks in correct severity order
5. Click RISK-001 → see risk detail with deterministic evidence (component, inventory, supply, production order, formula explanation)
6. Navigate back to risk list
7. Logout → redirect to login
8. Access control: navigating to /supply-risk while logged out → redirect to /login

This covers Golden Scenario steps 1–4 (deterministic core) plus partial step 8 (deterministic risk display). It is verified by the Playwright E2E test (golden-scenario.spec.ts, 316 lines, 50+ assertions) and post-merge CI on origin/main.

**What is NOT demonstrable today:** AI recommendation (step 7), RAG wired into workflow (step 6), user selection of recommendation (step 9), approval flow (steps 10–11), procurement task creation (step 12), audit trace (step 13).

**Closest working vertical slice:** Login → Dashboard → Supply Risk list → Supply Risk detail (deterministic only).

---

## 9. Concise Implemented-Capability Summary

| Capability | Phase | AT Status |
|-----------|-------|-----------|
| FastAPI + PostgreSQL + Redis + ARQ skeleton | Phase 1 | AT-001 (requires deployment verification) |
| JWT auth + RBAC (5 roles, 5 demo accounts) | Phase 2 | AT-002 (requires deployment verification) |
| Synthetic ERP dataset (14 business tables) | Phase 2 | AT-003 PASS |
| Deterministic risk engine | Phase 2 | AT-004 PASS |
| Real backend data in UI (no hidden mocks) | Phase 3 | AT-005 PASS |
| Dashboard, Supply Risk list, Supply Risk detail UI | Phase 3 | — |
| Document ingestion + pgvector + retrieval + citations | Phase 4 | AT-006: IMPLEMENTED — NOT VERIFIED AS PASS |
| Document access control (role-filtered retrieval) | Phase 4 | AT-007: IMPLEMENTED AT SERVICE/API LEVEL — NOT VERIFIED AS AT-007 PASS |
| OpenAI-compatible chat provider adapter (03A) | Phase 5 (foundation) | No AT PASS |
| Workflow state machine + engine (03B) | Phase 5 (foundation) | No AT PASS |
| Correlation ID propagation (UUID v4) | Cross-cutting | — |
| Structured JSON logging | Cross-cutting | — |
| Docker Compose + CI (3 workflows) | Infra | — |

**Implementation evidence details:** See `docs/planning/wp_strat_01_reconnaissance.md` §6 for file-level evidence.

---

## 10. Remaining Release 1 Gap Map

### Phase 5 gaps (AI Workflow — WP-REC-03C through 03G)

| Gap | Package | AT impact |
|-----|---------|-----------|
| Structured-output validation | WP-REC-03C | AT-008 validator clauses (unit-level); full PASS after 03F+03E |
| Provider retry/outage handling | WP-REC-03D | AT-013 backend (partial); full PASS after 03F+03G |
| Workflow-run detail API + recommendation UI | WP-REC-03E | FR-07 trace visibility; partial AT-012 foundation |
| Backend start/retry API + ARQ worker | WP-REC-03F | AT-008 full PASS (with 03E); AT-013 backend PASS |
| Frontend start/retry UI | WP-REC-03G | AT-013 UI clauses PASS |

### Phase 4 completion gaps (RAG Integration — WP-REC-05)

| Gap | AT impact |
|-----|-----------|
| Formal AT-006 PASS evidence | AT-006 PASS |
| Formal AT-007 PASS evidence | AT-007 PASS |
| RAG integration into AI workflow | Gate C citation requirement |

Substantial RAG and role-filtering implementation already exists. The remaining gap is formal AT-006/AT-007 execution/evidence and workflow integration — not the absence of implementation.

### Phase 6 gaps (Approval and Audit)

Approval service + models, audit event service, procurement task service, Approval Center UI, Audit Log UI — all NOT IMPLEMENTED. AT-009 through AT-012 require these.

### Phase 7 gaps (Public Deployment)

VPS deployment, demo reset, rate limiting, backup/restore, operational runbooks — all NOT STARTED. AT-001, AT-014, AT-015 require these.

### Phase 8 gaps (Portfolio Release)

Demo video, screenshots, architecture diagram, CV-ready description, external user smoke test, release evidence pack — all NOT STARTED. Gate F requires these.

---

## 11. Delivery Sequence

The authorized delivery sequence is:

1. **WP-STRAT-01** (this package) — product strategy and Release 1 alignment. COMPLETED.
2. **WP-ARCH-01** — Architecture Hygiene and Agent Onboarding. NOT AUTHORIZED yet.
3. **WP-REC-03C** → **WP-REC-03D** → **WP-REC-03E** → **WP-REC-03F** → **WP-REC-03G** — Phase 5 AI Workflow packages. Sequence preserved per SD-3. Each requires separate authorization.
4. **WP-REC-05** — Phase 4 completion (AT-006/AT-007 verification + RAG workflow integration). Positioned after 03C–03G and before Phase 6 per SD-4.
5. **Phase 6** — Approval and Audit. Not started.
6. **Phase 7** — Public Deployment. Not started.
7. **Phase 8** — Portfolio Release. Not started.

**WP-REC-03C remains NOT AUTHORIZED** unless an already-authoritative document explicitly authorizes it. This document does not authorize it.

---

## 12. Accepted Strategic Decisions (SD-1 through SD-5)

These decisions were accepted by the Product Owner on 2026-08-09 and are recorded in `08_DECISION_LOG.md`.

| # | Decision | Summary |
|---|----------|---------|
| SD-1 | Phase 4 status | Reclassify Phase 4 as PARTIALLY COMPLETE until AT-006 and AT-007 have accepted PASS evidence. |
| SD-2 | AT-006/AT-007 verification | Use a separate bounded verification package. Do not assign acceptance-test execution to WP-ARCH-01. |
| SD-3 | 03C–03G sequence | Preserve the sequence: 03C → 03D → 03E → 03F → 03G. |
| SD-4 | WP-REC-05 positioning | Position after 03C–03G and before Phase 6. |
| SD-5 | Release 1 framing | "Controlled AI-assisted Supply Risk Intelligence portfolio MVP demonstrating one complete, auditable, human-approved vertical workflow." |

---

## 13. Accepted Technical Directions (TD-4 and TD-5)

### TD-4: Two-phase risk engine ↔ AI contract

- **Deterministic code owns:** quantities, severity, constraints, feasible facts, state transitions, and business-rule enforcement.
- **AI enriches:** explanations, business impact, and structured recommendations on top of validated facts.

This is consistent with DEC-004 (deterministic business logic) and SoT 02 §1.

### TD-5: Role-based document permissions

Role-based document permissions match the current implementation direction:
- `backend/app/ai/rag/retriever.py` — role filtering via SQL join on `document_permissions` before LIMIT.
- `backend/app/api/retrieval.py` — server-side role-ID derivation from authenticated user.
- `backend/app/models/document.py` — DocumentPermission model.

Formal decision recording (DEC entry) and AT-007 verification remain required.

---

## 14. Deferred Technical Questions and Package Owners

| # | Question | Status | Owner / Phase |
|---|----------|--------|---------------|
| TD-1 | Demo reset mechanism (DEC-022) | Undecided | Phase 7 planning |
| TD-2 | Rate limit values | Undecided | Phase 7 planning |
| TD-3 | Charts library (DEC-016) | Not a blocker | Deferred; revisit if dashboard needs visual charts |
| TD-6 | Permanent frontend state management (DEC-015) | Deferred | Revisit post-Phase 6 |
| TD-7 | Reranker (DEC-019), Object storage (DEC-020), React Flow (DEC-021) | All "no" or "minimal" for MVP | Deferred to post-MVP optimization |

**Redis note:** Redis is established through DEC-011 (Accepted). It is not an unresolved strategic decision.

---

## 15. Principal Product and Delivery Risks

| Risk | Classification | Impact | Mitigation |
|------|---------------|--------|------------|
| Phase 4 status/evidence contradiction | Documentation/status and acceptance-evidence contradiction | Phase 4 was marked COMPLETE without accepted AT-006/AT-007 PASS evidence | SD-1: reclassify as PARTIALLY COMPLETE; SD-2: bounded verification package |
| AT-006/AT-007 verification gap | Evidence gap — implementation exists, formal evidence does not | Unknown whether RAG retrieval and access control pass under the full acceptance contract | Bounded verification package (SD-2) |
| Requirements traceability staleness | Stale documentation | Matrix references nonexistent files; AT status table stale | Updated in this package |
| Open questions staleness | Stale documentation | Resolved questions still listed as unresolved | Updated in this package |
| README technology-stack staleness | Stale documentation | Provider adapter marked "planned" despite being merged | Updated in this package |
| No public deployment yet | Phase 7 not started | Cannot demonstrate public HTTPS demo | Phase 7 authorization required |
| External dependencies (VPS, OpenAI key, domain) | Evidence gaps | Unknown whether AI provider connects in production; unknown VPS specs | PO to confirm when Phase 5 end-to-end and Phase 7 are authorized |

---

## 16. Acceptance-Evidence Policy

- No acceptance test is marked PASS without accepted evidence (test file or CI evidence).
- AT-006 and AT-007 must not be inferred as PASS from inspection alone. Formal execution and accepted evidence are required.
- A passing subset of tests is not evidence that the full suite passes.
- Acceptance-test execution belongs to a bounded verification package (SD-2), not to WP-ARCH-01 or WP-STRAT-01.
- This package does not execute AT-006 or AT-007.

---

## 17. Relationship to WP-ARCH-01

WP-ARCH-01 (Architecture Hygiene and Agent Onboarding) is a separate package that follows WP-STRAT-01. It is NOT authorized by this document.

WP-STRAT-01 records strategic inputs for WP-ARCH-01 to evaluate:
- Architecture hygiene specifics (code structure, import patterns, module boundaries)
- Agent onboarding (agent-loop integration, runtime separation execution)
- SP-0B authorization (separate track; READY but NOT AUTHORIZED)

WP-STRAT-01 does not perform architecture work or agent onboarding.

---

## 18. Post-Release 1 Candidate: ForgeMind Spatial Operations Twin

### Classification

- **Post-Release 1 only.** Evaluated after PORTFOLIO_READY status is achieved.
- **Not required** for the current Supply Risk Intelligence MVP.
- **Not authorized** for implementation.
- **No WP number assigned.**
- **Must not alter or delay the Release 1 delivery sequence.**

### Concept

A future portfolio module built around a synthetic spatial digital twin of distributed edge PCs, robots, mobile autonomous assets, and mesh communication nodes. It extends the ForgeMind product narrative from supply chain risk into real-time distributed-operations intelligence.

### Boundaries (preserved constraints)

- **Synthetic only.** All geography, assets, network topology, telemetry, and scenarios must be invented. No real coordinates, facilities, network identifiers, or operational data.
- **Deterministic control preserved.** Deterministic graph algorithms and policy rules generate or validate all feasible candidates. The LLM may explain, compare, prioritize, and format only policy-valid candidates.
- **LLM does not control:** node trust, topology, isolation, or movement.
- **Human approval required.** No simulated write action is committed without human approval.
- **Post-Release 1.** This candidate must not delay or influence the Release 1 delivery sequence.
- **Separate approval required.** If the PO wishes to pursue this direction, a separate decision-log entry and work-package authorization are required.

### Relationship to Release 1

This candidate builds on the Release 1 architecture patterns — deterministic state ownership, structured AI output validation, human-in-the-loop approval, audit traceability, correlation-ID propagation, synthetic-data-only policy, and the explicit state machine. It does not alter, block, or redefine any Release 1 requirement.

**Detailed concept and constraints:** See `docs/planning/wp_strat_01_reconnaissance.md` §20.

---

## END OF DOCUMENT
