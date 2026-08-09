# WP-STRAT-01 — Product Strategy and Release Replanning Reconnaissance Report

**Status:** READ-ONLY RECONNAISSANCE (REMEDIATED) — prepared for Product Owner review
**Date:** 2026-08-09
**Author:** Agent (GLM-5.2), prepared for Product Owner
**Baseline:** origin/main @ `47acbd87acf78df9ad3867f0a7da70461312da23`
**Authorization:** Read-only reconnaissance and planning pass only. No branch, no mutations, no commits, no PRs.

---

## 1. Verified Repository and Baseline

### 1.1 Repository identity

| Item | Value | Status |
|------|-------|--------|
| Remote URL | https://github.com/Tihonya/forgemind-ai-operations.git | VERIFIED |
| Branch | docs/status-sync-after-wp-rec-03b | VERIFIED (session worktree) |
| Local HEAD | 0e2163c68eaa31cda2809a3f2f7a90575eba1c4f | VERIFIED (PR #66 second parent) |
| origin/main | 47acbd87acf78df9ad3867f0a7da70461312da23 | VERIFIED (matches expected) |
| Working tree | clean before report creation; one untracked report file after | VERIFIED |
| Local vs origin/main | 0 ahead, 1 behind | VERIFIED (expected — on feature branch, not main) |

### 1.2 PR #66 merge verification

| Item | Value | Status |
|------|-------|--------|
| Merge commit | 47acbd87acf78df9ad3867f0a7da70461312da23 | VERIFIED |
| Merge type | Two-parent merge commit | VERIFIED |
| First parent (main) | fc48aed557d20f516cf46fe94175ce2d22c61dba | VERIFIED (PR #65 merge) |
| Second parent (PR head) | 0e2163c68eaa31cda2809a3f2f7a90575eba1c4f | VERIFIED (matches expected) |
| No newer commit on origin/main | origin/main tip is exactly 47acbd8 | VERIFIED |

### 1.3 Preflight verdict

ALL PREFLIGHT CHECKS PASS. No divergence detected. Repository state matches the Product Owner's checkpoint exactly.

---

## 2. Documents and Implementation Areas Inspected

### 2.1 Source of Truth documents (complete)

| Document | Path | Read completely |
|----------|------|-----------------|
| 00 Project Charter | forgemind_project_source_of_truth/00_PROJECT_CHARTER.md | YES |
| 01 Product and MVP Scope | forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md | YES |
| 02 System Behavior and Data | forgemind_project_source_of_truth/02_SYSTEM_BEHAVIOR_AND_DATA.md | YES |
| 03 Definition of Done | forgemind_project_source_of_truth/03_DEFINITION_OF_DONE.md | YES |
| 04 Acceptance Tests | forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md | YES |
| 05 Deployment and Demo | forgemind_project_source_of_truth/05_DEPLOYMENT_AND_DEMO.md | YES |
| 06 AI Agent Execution Rules | forgemind_project_source_of_truth/06_AI_AGENT_EXECUTION_RULES.md | YES |
| 07 Delivery Roadmap | forgemind_project_source_of_truth/07_ROADMAP.md | YES |
| 08 Decision Log | forgemind_project_source_of_truth/08_DECISION_LOG.md | YES |
| 09 Master Task for Hermes | forgemind_project_source_of_truth/09_MASTER_TASK_FOR_HERMES.md | YES |
| SoT README | forgemind_project_source_of_truth/README.md | YES |
| SoT MANIFEST | forgemind_project_source_of_truth/MANIFEST.md | YES |

### 2.2 Planning and status documents (complete)

| Document | Path | Read completely |
|----------|------|-----------------|
| HERMES.md | HERMES.md | YES (in project context) |
| README.md | README.md | YES |
| ACTIVE_WORK.md | docs/ACTIVE_WORK.md | YES |
| next_steps.md | docs/next_steps.md | YES |
| WP-REC-03 Decomposition | docs/planning/wp_rec_03_decomposition.md | YES (926 lines, complete) |
| SP-1 Assessment | docs/reviews/sp1_recovery_mvp_separation_assessment.md | YES (1270 lines, complete) |
| SP-0A Separation Decision | docs/planning/sp0a_separation_decision.md | YES |
| Open Questions | docs/planning/open_questions.md | YES |
| Requirements Traceability Matrix | docs/planning/requirements_traceability_matrix.md | YES |

### 2.3 Implementation areas inspected

| Area | Evidence gathered |
|------|-------------------|
| Backend app structure | Full file listing: backend/app/ — 103 Python files across api/, ai/, config, core/, models/, schemas/, services/, seed/, jobs/ |
| Backend AI subsystem | backend/app/ai/provider/ (6 files: chat_provider, exceptions, factory, fake_chat_provider, openai_chat_provider, __init__); backend/app/ai/workflow/ (3 files: state_machine, engine, __init__); backend/app/ai/rag/ (3 files: retriever, citations, __init__) |
| Backend tests | 83 test files: unit (62), integration (19), seed (3) |
| Frontend src | 83 files: routes/ (7 pages), components/ (layout, dashboard, supply-risk, ui, common), hooks/, contexts/, lib/ |
| Frontend E2E | 2 spec files: golden-scenario.spec.ts (316 lines, 50+ assertions), example.spec.ts |
| Migrations | 7 Alembic versions: diagnostic_jobs, phase_2_business, auth_tables, document_schema, knowledge_chunks, document_version_content, workflow_tables |
| CI workflows | 3: ci-backend.yml, ci-e2e.yml, ci-frontend.yml |
| Docker Compose | Services: postgres (pgvector/pg16), redis, backend, frontend, caddy |
| PR history | PRs #56–#66 merge log verified |
| Document access control implementation | backend/app/models/document.py (DocumentPermission model, document_permissions table); backend/app/ai/rag/retriever.py (role filtering via SQL join on document_permissions before LIMIT); backend/app/api/retrieval.py (server-side role-ID derivation from authenticated user); backend/tests/integration/test_at006_rag_retrieval.py (test_at006_retrieval_returns_no_results_without_permission verifies unauthorized role receives zero results) |

---

## 3. Current Product Definition

### 3.1 What ForgeMind is today (evidence-based)

ForgeMind AI Operations is a web platform for AI-assisted supply chain risk assessment in engineering and manufacturing environments. It is currently a **partially implemented portfolio MVP** demonstrating one vertical scenario: Production Plan Supply Risk Review.

**Evidence:**
- README.md line 3: "Supply Risk Intelligence — a portfolio-grade industrial AI demonstration."
- SoT 00_PROJECT_CHARTER.md §1: "AI-assisted supply risk analysis for engineering and manufacturing operations."
- SoT 01_PRODUCT_AND_MVP_SCOPE.md §1: "web-платформа для контрольованого AI-assisted аналізу ризиків постачання."
- docs/next_steps.md §"What is ForgeMind?": "Release 1 is a public portfolio MVP."

### 3.2 What exists vs. what is targeted

The README distinguishes "Currently implemented" from "Release 1 targets (not yet implemented)":

**Currently implemented (README lines 32–35):**
- Deterministic business logic (Python/SQL) for risk calculation
- RAG-powered document intelligence for evidence retrieval (implementation complete; AT-006 not executed in review)

**Release 1 targets NOT YET implemented (README lines 37–39):**
- Structured AI recommendations with human-in-the-loop approval
- Complete audit traceability for every workflow step

**Evidence:** README.md lines 28–40; docs/next_steps.md §"Current Implementation Status."

### 3.3 Product boundary

The MVP is explicitly scoped to one vertical scenario. The Source of Truth prohibits expanding into a general enterprise AI platform.

**Evidence:**
- SoT 00 §6 "Межі проєкту" — explicit in-scope and out-of-scope lists.
- HERMES.md §"Current product boundary": "The MVP is one vertical scenario: Supply Risk Intelligence."
- DEC-002 (Accepted): "Перший реліз реалізує Supply Risk Intelligence, а не повну AI Operations Platform."

---

## 4. Target Users and Audiences Found in Existing Evidence

### 4.1 Primary target user (product context)

**Production Manager** — views production plan supply risks, triggers analysis, receives AI recommendations, approves procurement actions.

**Evidence:**
- SoT 00 §5: "Production Manager — Переглядає ризики виробничого плану та підтверджує запропоновані дії."
- SoT 01 §2 Golden Scenario: "Production Manager відкриває Dashboard."
- SP-1 Assessment §7.2 Q2: "Production Manager (role: PRODUCTION_MANAGER, demo account: manager.demo)."

### 4.2 Secondary users (product context)

| Role | Demo account | Purpose | Evidence |
|------|-------------|---------|----------|
| Procurement Specialist | procurement.demo | Receives draft procurement tasks | SoT 00 §5; DEC-028 |
| Engineer | engineer.demo | Views technical documents and alternatives | SoT 00 §5; DEC-009 |
| AI Administrator | admin.demo | Controls models, runs, errors, policies | SoT 00 §5; DEC-028 |
| Auditor | auditor.demo | Reviews execution trace, no write access | SoT 00 §5; DEC-028 |

### 4.3 Primary audience (portfolio context)

**Recruiters and technical reviewers** evaluating AI-assisted industrial workflow capabilities.

**Evidence:**
- README.md line 55: "Target audience: Recruiters and technical reviewers evaluating AI-assisted industrial workflow capabilities."
- README.md line 57: "Reviewer journey: CV → Live Demo → complete working scenario (3–5 minutes)."
- SoT 00 §7: "стороронній технічний спеціаліст за 10–15 хвилин може... пройти Golden Scenario."

### 4.4 Secondary audience (portfolio context)

The Product Owner themselves — using ForgeMind as a CV/portfolio artifact demonstrating full-stack AI engineering capability.

**Evidence:**
- SoT 00 §4: value proposition lists "process mapping, Python development, React/TypeScript, ERP integration, RAG, AI-agent orchestration, human-in-the-loop, RBAC, auditability, Docker/Linux deployment."
- SoT 09 §"Required final deliverables" include "release-evidence/" and "CV-ready project description."

---

## 5. Current Demonstrable User Journey

### 5.1 What a reviewer can do TODAY (evidence-based)

The current demonstrable journey covers Golden Scenario steps 1–4 (deterministic core) plus partial step 8 (risk display). It is verified by the Playwright E2E test (golden-scenario.spec.ts, 316 lines, 50+ assertions).

**Complete demonstrable flow:**

1. Open application → see login page with synthetic-data notice
2. Login as manager.demo → JWT auth, redirect to dashboard
3. Dashboard shows: active plan PLAN-2026-W31, status EXECUTING, 3 total risks, severity breakdown (1 CRITICAL, 1 HIGH, 1 MEDIUM, 0 LOW)
4. Navigate to Supply Risk Analysis → see 3 risks in correct severity order
5. Click RISK-001 → see risk detail with:
   - Component: CTRL-X4, severity CRITICAL, work order WO-2026-0142
   - Evidence panel: Required 20, Available 12, Confirmed early 0, Confirmed late 0, Shortage 8
   - Formula explanation: Shortage = max(0, required - available - confirmed_early)
   - Component, Inventory, Incoming Supply, Production Order, Plan Context panels
6. Navigate back to risk list
7. Logout → redirect to login
8. Access control: navigating to /supply-risk while logged out → redirect to /login

**Evidence:**
- frontend/e2e/golden-scenario.spec.ts — complete test with 50+ assertions covering AT-002, AT-003, AT-004, AT-005.
- Post-merge CI on origin/main: "Playwright Golden Scenario SUCCESS" (docs/ACTIVE_WORK.md line 23; docs/next_steps.md line 114).
- Frontend routes: dashboard.tsx, supply-risk.tsx, supply-risk-detail.tsx, login.tsx, protected.tsx, root.tsx, not-found.tsx.

### 5.2 What is NOT demonstrable today

| Golden Scenario step | Status | Evidence |
|----------------------|--------|----------|
| Step 5: Agent workflow receives structured result | NOT DEMONSTRABLE — workflow engine exists (03B) but no start/retry API or worker exists | docs/next_steps.md §"NOT IMPLEMENTED" |
| Step 6: RAG searches accessible documents for alternatives | IMPLEMENTED AT SERVICE/API LEVEL — retrieval with role filtering exists; NOT VERIFIED AS AT-006/AT-007 PASS; not wired into AI workflow | SoT 01 §2 step 6; retriever.py; retrieval.py; test_at006_rag_retrieval.py |
| Step 7: Model forms explained recommendation in JSON schema | NOT DEMONSTRABLE — provider adapter exists (03A) but no structured-output validation (03C), no worker execution (03F) | WP-REC-03 decomposition §4 |
| Step 8 (AI part): UI shows AI recommendation with sources, proposed action, confidence | NOT DEMONSTRABLE (AI part) — deterministic evidence panel exists; AI recommendation display does not | SoT 01 §3.6; README lines 130–131 |
| Step 9: User selects recommendation | NOT DEMONSTRABLE — no recommendation to select | SoT 01 §2 step 9 |
| Step 10: System creates Approval Request | NOT DEMONSTRABLE — no approval models, service, or UI | SoT 01 §2 step 10; Phase 6 |
| Step 11: No write action before approval | NOT DEMONSTRABLE — no approval flow at all | SoT 01 §2 step 11; AT-009 |
| Step 12: After approval, procurement task created | NOT DEMONSTRABLE — no procurement task service | SoT 01 §2 step 12; AT-010 |
| Step 13: Audit Log shows full trace | NOT DEMONSTRABLE — no audit event service or UI | SoT 01 §2 step 13; AT-012 |

### 5.3 Closest working vertical slice

Login → Dashboard → Supply Risk list → Supply Risk detail (deterministic only).

This is confirmed by the SP-1 Assessment §7.2 Q12 and verified by the golden-scenario.spec.ts E2E test.

---

## 6. Implemented-Capability Inventory

### 6.1 Implemented and tested capabilities

| Capability | Phase | Evidence | AT Status |
|-----------|-------|----------|-----------|
| FastAPI + PostgreSQL + Redis + ARQ running skeleton | Phase 1 | docker-compose.yml; 7 migrations; health checks | AT-001 (partial — clean local deploy works; no VPS) |
| JWT authentication + RBAC (5 roles, 5 demo accounts) | Phase 2 | backend/app/services/auth_service.py; backend/app/api/auth.py; DEC-028 mapping | AT-002 PASS (local; not tested on VPS) |
| Synthetic ERP dataset (14 business tables) | Phase 2 | backend/app/models/ (component, production, product, supplier, warehouse, user); seed/generator/ | AT-003 PASS |
| Deterministic risk engine (BOM explosion, inventory, severity) | Phase 2 | backend/app/services/risk_engine.py, bom_explosion.py, inventory_service.py | AT-004 PASS |
| Real backend data in UI (no hidden mocks) | Phase 3 | frontend/src/routes/ — all fetch from real API; golden-scenario.spec.ts verifies | AT-005 PASS |
| Dashboard, Supply Risk list, Supply Risk detail UI | Phase 3 | frontend/src/routes/dashboard.tsx, supply-risk.tsx, supply-risk-detail.tsx; component tests | — |
| Document ingestion + pgvector index + retrieval + citations | Phase 4 | backend/app/ai/rag/ (retriever, citations); backend/app/services/ (embedding_provider, chunking, ingestion); backend/app/api/ (ingestion, retrieval) | AT-006: IMPLEMENTED — NOT VERIFIED AS PASS (test exists, requires live DB) |
| Document access control (role-filtered retrieval) | Phase 4 | backend/app/models/document.py (DocumentPermission); backend/app/ai/rag/retriever.py (SQL join on document_permissions before LIMIT); backend/app/api/retrieval.py (server-side role-ID derivation); test_at006_retrieval_returns_no_results_without_permission | AT-007: IMPLEMENTED AT SERVICE/API LEVEL — NOT VERIFIED AS AT-007 PASS |
| OpenAI-compatible chat provider adapter (03A) | Phase 5 (foundation) | backend/app/ai/provider/ (chat_provider, openai_chat_provider, fake_chat_provider, factory, exceptions) | No AT PASS |
| Workflow state machine (7 states, immutable transitions) (03B) | Phase 5 (foundation) | backend/app/ai/workflow/state_machine.py; backend/app/ai/workflow/engine.py; backend/app/models/workflow.py; migration f1a2b3c4d5e6 | No AT PASS |
| WorkflowEngine (create run, state transitions, step recording, provider call) | Phase 5 (foundation) | backend/app/ai/workflow/engine.py; backend/tests/unit/test_workflow_engine.py; backend/tests/integration/test_workflow_run_lifecycle.py | No AT PASS |
| Correlation ID propagation (UUID v4) | Cross-cutting | backend/app/core/correlation.py; backend/app/api/middleware/correlation.py; DEC-024 | — |
| Structured JSON logging | Cross-cutting | backend/app/core/logging.py | — |
| Docker Compose (Caddy, backend, frontend, postgres, redis) | Infra | docker-compose.yml, docker-compose.dev.yml; infra/caddy/Caddyfile; infra/docker/*.dockerfile | — |
| CI (3 workflows: backend, frontend, E2E) | Infra | .github/workflows/ci-backend.yml, ci-e2e.yml, ci-frontend.yml | — |
| Agent-loop development tooling (883 pytest tests, 40 harness scenarios) | Dev-time tool | scripts/agent-loop/, .agent-loop/ — zero runtime coupling to Product | — |

### 6.2 Implemented but NOT end-to-end tested

| Capability | What exists | What's missing | Evidence |
|-----------|-------------|----------------|----------|
| RAG retrieval with citations | Infrastructure: retriever, citations, ingestion, chunking, embedding provider, pgvector index; role-filtered retrieval with SQL join on document_permissions | Not wired into AI workflow; AT-006 test exists but requires live DB and was not executed in review | docs/next_steps.md AT-006; test_at006_rag_retrieval.py |
| Document access control | DocumentPermission model; retriever role filtering before LIMIT; retrieval API server-side role derivation; test verifies unauthorized role gets zero results | Formal AT-007 execution/evidence and confirmation that restricted content is excluded from the complete authenticated retrieval context/response path | backend/app/models/document.py; backend/app/ai/rag/retriever.py; backend/app/api/retrieval.py; test_at006_rag_retrieval.py |
| AI provider call | ChatProvider ABC, OpenAIChatProvider, FakeChatProvider, factory | No workflow execution path calls the provider in an end-to-end user flow | backend/app/ai/provider/ |
| Workflow run lifecycle | State machine, engine, ORM models, migration, unit/integration tests | No start/retry API, no ARQ worker, no vertical wiring, no UI | WP-REC-03 decomposition §4 |

### 6.3 Acceptance test status summary

| AT | Description | Status | Evidence |
|----|-------------|--------|----------|
| AT-001 | Clean deployment | NOT TESTED (requires deployment/environment verification) | docs/next_steps.md |
| AT-002 | Demo authentication | IMPLEMENTED (not tested on VPS; requires deployment verification) | golden-scenario.spec.ts; backend tests |
| AT-003 | Golden Dataset integrity | PASS | test_risk_engine_with_seed.py; golden-scenario.spec.ts |
| AT-004 | Deterministic risk calculation | PASS | test_risk_endpoint_at004.py (284 lines); golden-scenario.spec.ts |
| AT-005 | No hidden UI mocks | PASS | golden-scenario.spec.ts |
| AT-006 | RAG retrieval | IMPLEMENTED — NOT VERIFIED AS PASS (test exists, requires live DB) | test_at006_rag_retrieval.py |
| AT-007 | Document access control | IMPLEMENTED AT SERVICE/API LEVEL — NOT VERIFIED AS AT-007 PASS | retriever.py (role filtering); retrieval.py (role derivation); test_at006_retrieval_returns_no_results_without_permission |
| AT-008 | Structured output validation | NOT IMPLEMENTED | docs/next_steps.md; WP-REC-03C |
| AT-009 | Human approval blocks write | NOT IMPLEMENTED | docs/next_steps.md; Phase 6 |
| AT-010 | Approval executes action | NOT IMPLEMENTED | docs/next_steps.md; Phase 6 |
| AT-011 | Reject path | NOT IMPLEMENTED | docs/next_steps.md; Phase 6 |
| AT-012 | Audit trace completeness | NOT IMPLEMENTED | docs/next_steps.md; Phase 6 |
| AT-013 | Model outage | NOT IMPLEMENTED | docs/next_steps.md; WP-REC-03D/F/G |
| AT-014 | Public HTTPS smoke | NOT TESTED (requires deployment/environment verification) | docs/next_steps.md; Phase 7 |
| AT-015 | Demo reset | NOT IMPLEMENTED | docs/next_steps.md; Phase 7 |

**Summary:**
- 3 ATs are PASS: AT-003, AT-004, AT-005.
- 2 ATs have relevant implementation but lack accepted PASS evidence: AT-006, AT-007.
- 3 ATs require deployment/environment verification: AT-001, AT-002, AT-014.
- 7 ATs require capabilities that are not implemented: AT-008, AT-009, AT-010, AT-011, AT-012, AT-013, AT-015.

AT-006 and AT-007 must not be inferred as PASS from inspection alone. Formal execution and accepted evidence are required.

---

## 7. Remaining Release 1 Gap Map

### 7.1 Phase 5 gaps (AI Workflow — WP-REC-03C through 03G)

| Gap | Package | What it delivers | AT impact |
|-----|---------|-----------------|-----------|
| Structured-output validation | WP-REC-03C | JSON-schema validator, Pydantic recommendation schema, versioned prompt template | AT-008 validator clauses (unit-level); full PASS after 03F+03E |
| Automatic provider retry/outage | WP-REC-03D | Outage handler, retry policy, exponential backoff, FAILED_PROVIDER state | AT-013 backend (partial); full PASS after 03F+03G |
| Workflow-run detail API + recommendation UI | WP-REC-03E | Read-only REST API for workflow runs, frontend run-detail page, recommendation display | FR-07 trace visibility; partial AT-012 foundation |
| Backend workflow start/retry API + ARQ worker | WP-REC-03F | POST start/retry endpoints, ARQ worker, vertical wiring (risk→provider→validation→persistence), reconciler | AT-008 full PASS (with 03E); AT-013 backend PASS |
| Frontend start/retry UI interaction | WP-REC-03G | "Start AI Analysis" button, "Retry" button, non-freezing UI, polling | AT-013 UI clauses PASS |

**Evidence:** docs/planning/wp_rec_03_decomposition.md §4 (complete decomposition table); §7 (AT mapping summary); §12 (NOT AUTHORIZED items).

### 7.2 Phase 4 completion gaps (RAG Integration — WP-REC-05)

| Gap | What it delivers | AT impact |
|-----|-----------------|-----------|
| Formal AT-006 PASS evidence | Execute test_at006_rag_retrieval.py against live DB and confirm accepted PASS | AT-006 PASS |
| Formal AT-007 PASS evidence | Execute and confirm restricted content is excluded from the complete authenticated retrieval context/response path | AT-007 PASS |
| RAG integration into AI workflow | Wire retrieval into workflow context; citations in AI recommendation | Gate C citation requirement |

**Note:** Substantial RAG and role-filtering implementation already exists (retriever, citations, DocumentPermission model, role-filtered SQL query, server-side role derivation, unauthorized-role test). The remaining gap is formal AT-006/AT-007 execution/evidence and confirmation that restricted content is excluded from the complete authenticated retrieval context/response path — not the absence of document access control implementation.

**Evidence:** WP-REC-03 decomposition §3 finding 9: "RAG integration remains assigned to WP-REC-05"; §7: "AT-007 is NOT mapped to any Phase 5 package."

### 7.3 Phase 6 gaps (Approval and Audit)

| Gap | What it delivers | AT impact |
|-----|-----------------|-----------|
| Approval service + models | ApprovalRequest model, approve/reject service, approval API | AT-009, AT-010, AT-011 |
| Audit event service | AuditEvent model, audit service, immutable audit trail | AT-012 |
| Procurement task service | ProcurementTask model, task creation after approval | AT-010 |
| Approval Center UI | Pending approvals, structured action preview, approve/reject, comment | AT-009, AT-010, AT-011 |
| Audit Log UI | Actor, event, timestamp, entity, correlation ID display | AT-012 |

**Evidence:** SoT 07_ROADMAP.md Phase 6; docs/next_steps.md §"NOT IMPLEMENTED (Release 1 blockers)"; SP-1 §18.2 WP-REC-04 decomposition (provisional: 04A–04E).

### 7.4 Phase 7 gaps (Public Deployment)

| Gap | What it delivers | AT impact |
|-----|-----------------|-----------|
| VPS deployment | Public HTTPS deployment, domain, TLS | AT-001, AT-014 |
| Demo reset | Admin-triggered dataset restoration | AT-015 |
| Rate limiting | Public demo protection | Gate D |
| Backup/restore | PostgreSQL backup procedure | Gate E |
| Operational runbooks | Deploy, rollback, backup, restore, reset, secrets, logs, health, emergency | Gate E |

**Evidence:** SoT 07_ROADMAP.md Phase 7; SoT 05_DEPLOYMENT_AND_DEMO.md §9; docs/next_steps.md §"NOT IMPLEMENTED."

### 7.5 Phase 8 gaps (Portfolio Release)

| Gap | What it delivers | Gate impact |
|-----|-----------------|-------------|
| Demo video (3–5 min) | Screen recording of Golden Scenario | Gate F |
| Screenshots | Key screens captured | Gate F |
| Architecture diagram | Visual architecture overview | Gate F |
| CV-ready project description | Ukrainian and English | Gate F |
| External user smoke test | Third-party completes scenario without author assistance | Gate F |
| Release evidence pack | release-evidence/ directory with test summaries, health, screenshots | SoT 04 §"Release checklist evidence" |

**Evidence:** SoT 07_ROADMAP.md Phase 8; SoT 03_DEFINITION_OF_DONE.md Gate F; SoT 04_ACCEPTANCE_TESTS.md "Release checklist evidence."

---

## 8. Current Roadmap Assessment

### 8.1 Roadmap structure (SoT 07_ROADMAP.md)

| Phase | Objective | Exit Criteria | Status |
|-------|-----------|---------------|--------|
| Phase 0 | Repository and governance | Documents approved, CI skeleton | COMPLETE |
| Phase 1 | Running skeleton | Clean deploy, connections, smoke test | COMPLETE |
| Phase 2 | Synthetic ERP core | AT-003, AT-004, AT-005 pass | COMPLETE (ATs PASS) |
| Phase 3 | Core UI | Real backend data, no hardcoded results, frontend tests | COMPLETE |
| Phase 4 | Knowledge and RAG | AT-006, AT-007 pass | PARTIALLY COMPLETE — substantial implementation exists (retriever, DocumentPermission, role-filtered SQL, retrieval API, unauthorized-role test); formal AT-006/AT-007 PASS evidence incomplete |
| Phase 5 | Controlled AI workflow | AT-008, AT-013 pass, model response validated | IN PROGRESS (03A+03B complete; 03C–03G NOT AUTHORIZED) |
| Phase 6 | Approval and audit | AT-009…AT-012 pass | NOT STARTED |
| Phase 7 | Public deployment | AT-001, AT-002, AT-014, AT-015 pass on public environment | NOT STARTED |
| Phase 8 | Portfolio release | All gates satisfied, 24h no P1/P2, PORTFOLIO_READY | NOT STARTED |

### 8.2 Roadmap sequence assessment

The current Phase 5→6→7→8 sequence is **architecturally sound** for the following reasons:

1. **Phase 5 before Phase 6 is correct.** AI recommendation (Phase 5) must exist before approval (Phase 6) can act on it. The write-action chain (SoT 02 §8: "recommendation → draft action → approval request → human decision → procurement task → audit event") is sequential by design.
2. **Phase 6 before Phase 7 is correct.** The Golden Scenario requires approval and audit to be functional before public deployment can demonstrate them.
3. **Phase 7 before Phase 8 is correct.** Portfolio presentation requires a working public deployment.
4. **WP-REC-05 (Phase 4 completion) is interleaved.** Per PO recommendation SD-4 (§13.1), WP-REC-05 should be positioned after WP-REC-03C–03G completion and before Phase 6.

### 8.3 Phase 4 status contradiction

**Finding:** SoT 07_ROADMAP.md Phase 4 exit criteria require "AT-006, AT-007 pass." docs/next_steps.md marks Phase 4 as COMPLETE. However:
- AT-006 has a test file and retrieval infrastructure but has NOT been verified as PASS (requires live database execution).
- AT-007 has implementation at service/API level (DocumentPermission model, role-filtered retriever SQL, server-side role derivation, unauthorized-role test) but has NOT been verified as PASS under its complete Source of Truth acceptance contract.

**Classification:** Documentation/status and acceptance-evidence contradiction. The project claims Phase 4 complete, but the formal exit criteria (AT-006 + AT-007 PASS) have not been met with accepted evidence.

**Important nuance:** Substantial RAG and role-filtering implementation exists. This is not a case of missing implementation — it is a case of incomplete formal acceptance evidence. Phase 5 builds on real, implemented infrastructure (retriever, citations, provider adapter, workflow engine). The technical foundation is not false; the formal Phase 4 exit evidence is incomplete.

**Evidence:**
- SoT 07_ROADMAP.md Phase 4 exit criteria: "AT-006, AT-007 pass; evaluation fixtures created."
- docs/next_steps.md §"IMPLEMENTED": "Phase 4: Knowledge and RAG — COMPLETE."
- docs/next_steps.md AT-006: "TEST EXISTS — NOT VERIFIED IN THIS REVIEW."
- docs/next_steps.md AT-007: "NOT IMPLEMENTED." (This classification is itself stale — implementation exists; see §6.1 and §6.2 of this report.)

### 8.4 WP-REC-03C–03G sequence

**Product Owner recommendation (SD-3, §13.1):** Keep the current sequence 03C → 03D → 03E → 03F → 03G. User-visible velocity does not justify violating the established dependency sequence. The decomposition's dependency chain is internally consistent — each package depends on its predecessor.

**Observation:** 03C and 03D are "internal architectural enablement" packages that produce no user-visible demo progress. 03E is the first "externally observable demo progress" package. While an alternative sequence could prioritize 03E earlier, this would violate the established dependency chain. The PO recommendation is to preserve the sequence as decomposed.

---

## 9. Proposed Release 1 Product Boundary

### 9.1 Release 1 definition (from existing evidence)

Release 1 = the complete Golden Scenario (13 steps from SoT 01 §2) deployed to a public VPS with HTTPS, backed by synthetic data, with all 15 acceptance tests passing and all 6 Definition of Done gates satisfied.

**Evidence:**
- README.md §"Release 1 Deliverables": Live Demo, public GitHub, synthetic data, real workflows, persisted state, recruiter-friendly README, verified tech stack.
- SoT 03_DEFINITION_OF_DONE.md §8: "MVP Done = all AT-001…AT-015 PASS locally and in CI. Portfolio Ready = MVP Done plus public HTTPS deployment, 3 consecutive Golden Scenario passes, 24h no P1/P2, demo video, external smoke test."
- SoT 09_MASTER_TASK_FOR_HERMES.md §"Non-negotiable product scope": 8-step end-to-end scenario.

### 9.2 Recommended Release 1 framing (PO recommendation SD-5)

**Recommended framing:** "Controlled AI-assisted Supply Risk Intelligence portfolio MVP demonstrating one complete, auditable, human-approved vertical workflow."

This framing emphasizes: controlled (deterministic owns arithmetic and state), AI-assisted (not autonomous), auditable (full trace), human-approved (no write without approval), one complete vertical workflow (not a platform).

### 9.3 What Release 1 is NOT

- Not a general-purpose AI platform (DEC-002)
- Not connected to real ERP/corporate/military systems (DEC-003, SoT 00 §6)
- Not dependent on agent-loop runtime (docs/next_steps.md §"Product / Runtime Boundary")
- Not a multi-tenant SaaS (SoT 00 §6 out-of-scope)
- Not production-grade high availability (SoT 00 §6 out-of-scope)

---

## 10. Capabilities Proposed as Required for Release 1

### 10.1 Required capabilities (must-have for Release 1)

These map directly to Golden Scenario steps and acceptance tests:

| Capability | Golden Scenario step(s) | AT(s) | Phase | Current status |
|-----------|------------------------|-------|-------|----------------|
| Deterministic risk calculation | Steps 3–4 | AT-003, AT-004, AT-005 | Phase 2 | COMPLETE |
| Authentication + RBAC | Step 1 | AT-002 | Phase 2 | COMPLETE |
| Dashboard + Supply Risk UI | Steps 1–4, 8 (deterministic) | AT-005 | Phase 3 | COMPLETE |
| RAG retrieval with citations | Step 6 | AT-006 | Phase 4 | IMPLEMENTED — NOT VERIFIED AS PASS |
| Document access control | Step 6 (restricted docs) | AT-007 | Phase 4 / WP-REC-05 | IMPLEMENTED AT SERVICE/API LEVEL — NOT VERIFIED AS AT-007 PASS |
| AI provider adapter | Step 5 (provider call) | — | Phase 5 (03A) | COMPLETE |
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

### 10.2 Required portfolio artifacts (Gate F)

| Artifact | Evidence |
|----------|----------|
| Recruiter-friendly README | SoT 03 Gate F; README.md exists but needs final polish |
| Architecture diagram | SoT 03 Gate F; README has ASCII diagram; Gate F likely expects visual |
| Screenshots | SoT 03 Gate F; not yet captured |
| 3–5 min demo video | SoT 03 Gate F; not yet recorded |
| Demo credentials | SoT 03 Gate F; 5 accounts defined (DEC-028) |
| Trade-offs and limitations | SoT 03 Gate F; not yet documented |
| CV-ready description (UA + EN) | SoT 03 Gate F; not yet written |
| External user smoke test | SoT 03 Gate F; not yet performed |

---

## 11. Capabilities Proposed for Deferral

### 11.1 Capabilities that can be deferred without weakening the core product story

| Capability | Rationale | Evidence |
|-----------|-----------|----------|
| Agent-loop runtime separation (SP-0B through SP-5) | Zero runtime coupling; not a Release 1 dependency; development-time tool only; SP-0B is READY but NOT AUTHORIZED | docs/next_steps.md §"Product / Runtime Boundary"; SP-0A decision; SP-1 §5.5 coupling analysis |
| forgemind-agent-runtime repository creation | NOT AUTHORIZED; not a Release 1 blocker | docs/next_steps.md; WP-REC-03 decomposition §10 |
| Agent automation activation | Deferred until available on general terms; not a Release 1 dependency | docs/next_steps.md |
| DEC-015 permanent state management (Zustand) | Phase 1 approach (React hooks + TanStack Query) is sufficient for MVP; revisit post-Phase 6; not a blocker for WP-REC-03C | open_questions.md Q-7; DEC-013 decomposition §5 DEC-015 |
| Charts library (DEC-016) | Dashboard currently uses text-based widgets; Recharts not yet needed for MVP demo; not a blocker for WP-REC-03C | open_questions.md Q-8 |
| Reranker (DEC-019) | pgvector similarity is sufficient for synthetic data MVP; not a blocker | open_questions.md Q-11 |
| Object storage (DEC-020) | Synthetic documents are small; PostgreSQL text/jsonb is sufficient; not a blocker | open_questions.md Q-12 |
| React Flow for workflow trace (DEC-021) | Workflow steps are sequential; timeline component is simpler and sufficient; not a blocker | open_questions.md Q-13 |
| All Post-MVP backlog items | Explicitly excluded by SoT 00 §6 and SoT 01 §5 | SoT 00 §6, SoT 01 §5 |

### 11.2 Capabilities that should NOT be deferred

All items in §10.1 are required for Release 1. Deferring any of them would break the Golden Scenario or fail an acceptance test. The Source of Truth is explicit: "Будь-який невиконаний пункт означає, що проєкт ще не завершений" (SoT README.md).

---

## 12. Strategic Risks and Contradictions

### 12.1 Phase 4 status/acceptance-evidence contradiction

**Finding:** SoT 07_ROADMAP.md Phase 4 exit criteria require "AT-006, AT-007 pass." docs/next_steps.md marks Phase 4 as COMPLETE. However:
- AT-006 has a test file and retrieval infrastructure but has NOT been verified as PASS.
- AT-007 has implementation at service/API level but has NOT been verified as PASS under its complete Source of Truth acceptance contract. (docs/next_steps.md classifies AT-007 as "NOT IMPLEMENTED" — this is itself stale; implementation exists, see §6.1 and §6.2 of this report.)

**Classification:** Documentation/status and acceptance-evidence contradiction. The project claims Phase 4 complete, but the formal exit criteria have not been met with accepted evidence.

**Important nuance:** This is not a case of missing implementation. Substantial RAG and role-filtering implementation exists (retriever, citations, DocumentPermission, role-filtered SQL, server-side role derivation, unauthorized-role test). Phase 5 builds on real, implemented infrastructure. The technical foundation is not false; the formal Phase 4 exit evidence is incomplete.

**Evidence:** SoT 07 Phase 4 exit criteria; docs/next_steps.md §"IMPLEMENTED" (Phase 4: COMPLETE); docs/next_steps.md AT-006 and AT-007 status table; backend/app/ai/rag/retriever.py; backend/app/models/document.py; backend/app/api/retrieval.py; test_at006_rag_retrieval.py.

### 12.2 AT-006 and AT-007 verification gap

**Finding:** AT-006 (RAG retrieval) and AT-007 (document access control) both have relevant implementation but neither has been confirmed as PASS under the complete Source of Truth acceptance contract. AT-006 requires live database execution. AT-007 requires formal execution and confirmation that restricted content is excluded from the complete authenticated retrieval context/response path.

**Classification:** Evidence gap — implementation exists; formal acceptance evidence does not.

**Evidence:** docs/next_steps.md AT-006; test_at006_rag_retrieval.py (includes test_at006_retrieval_returns_no_results_without_permission); backend/app/ai/rag/retriever.py; backend/app/api/retrieval.py; backend/app/models/document.py.

**Resolution:** Per PO recommendation SD-2 (§13.1), use a separate, bounded verification package for AT-006 and AT-007. Do not assign acceptance-test execution to WP-ARCH-01.

### 12.3 Requirements traceability matrix staleness

**Finding:** docs/planning/requirements_traceability_matrix.md references files that do not exist in the current implementation:
- FR-06 references `backend/app/schemas/ai_output.py` and `backend/app/ai/output_validator.py` — these files do NOT exist (structured-output validation is WP-REC-03C, not yet implemented).
- FR-07 references `backend/app/ai/workflow/runner.py`, `backend/app/ai/workflow/machine.py`, `backend/app/ai/workflow/steps.py` — the actual files are `state_machine.py` and `engine.py` (different names, implemented in 03B).
- FR-08 references `backend/app/services/approval_service.py` and `backend/app/api/approvals.py` — these do NOT exist (Phase 6, not yet implemented).
- FR-09 references `backend/app/services/audit_service.py` and `backend/app/api/audit.py` — these do NOT exist (Phase 6).
- FR-12 references `backend/app/services/reset_service.py` — does NOT exist (Phase 7).
- AT status table says all ATs are "PENDING" (pre-implementation), which is stale — AT-003/004/005 are PASS.
- FR-05 references `backend/app/ai/rag/indexer.py` — the actual file is `backend/app/services/ingestion.py` (different name).

**Classification:** Stale documentation — the traceability matrix was written pre-implementation and has not been updated.

**Evidence:** docs/planning/requirements_traceability_matrix.md lines 9–23, 28–44.

### 12.4 Open questions document staleness

**Finding:** docs/planning/open_questions.md lists Q-1 through Q-20 as "Unresolved Questions" requiring PO decisions. However, many have already been resolved:
- Q-1 (DEC-009 Engineer role): ACCEPTED (2026-07-17) — but open_questions.md still lists it under "Unresolved."
- Q-4 (DEC-012 polling): ACCEPTED — but listed as unresolved.
- Q-5 (DEC-013): ACCEPTED (2026-08-09) — but listed as unresolved.
- Q-7 through Q-20: Most have recommendations but no recorded decision status.

**Classification:** Stale documentation — open_questions.md has not been updated to reflect accepted decisions.

**Evidence:** docs/planning/open_questions.md §"Unresolved Questions" vs. 08_DECISION_LOG.md (DEC-009, DEC-012, DEC-013, DEC-014, DEC-017, DEC-024, DEC-028 all Accepted).

### 12.5 README technology-stack staleness

**Finding:** README.md line 152 states "AI/ML | ARQ + Redis (AI provider adapter: planned for Phase 5, not yet implemented)" even though WP-REC-03A is merged and the OpenAI-compatible chat provider adapter exists at backend/app/ai/provider/ (6 files, merged via PR #63).

**Classification:** Small documentation-staleness finding for the later strategy/status mutation package.

**Evidence:** README.md line 152; backend/app/ai/provider/ (chat_provider.py, openai_chat_provider.py, fake_chat_provider.py, factory.py, exceptions.py); PR #63 merge at 5c86000.

### 12.6 Demo reset mechanism undecided

**Finding:** Open question Q-14 (DEC-022) proposes demo reset options but no decision has been recorded. AT-015 requires demo reset. The README (line 98) already notes "make reset — placeholder — reset_service.py not yet implemented."

**Classification:** Undecided decision for Phase 7 planning. Not a blocker for WP-REC-03C.

### 12.7 Rate limit values undecided

**Finding:** Open question Q-17 proposes rate limit values but no decision has been recorded. Gate D requires rate limiting. Phase 7 needs concrete values.

**Classification:** Undecided decision for Phase 7 planning. Not a blocker for WP-REC-03C.

### 12.8 Risk engine ↔ AI output contract direction

**Finding:** Open question Q-19 (risk engine ↔ AI output contract) has a recommended two-phase approach: deterministic engine owns quantities, severity, constraints, and feasible facts; AI enriches them with explanation, business impact, and structured recommendations.

**PO direction:** Accept the two-phase direction for later formal recording in the Decision Log. This direction is consistent with DEC-004 (deterministic business logic) and the architectural principle in SoT 02 §1. Formal decision recording remains for the later mutation package. This is not a blocker for WP-REC-03C — the two-phase direction is clear enough to proceed.

**Evidence:** open_questions.md Q-19; SoT 02 §6 (recommendation schema); DEC-004.

### 12.9 Document permission model direction

**Finding:** Open question Q-20 (document permission model) recommends role-based access. The current implementation already uses role-based behavior: retriever.py filters via document_permissions join on role_id, and retrieval.py derives role IDs server-side from the authenticated user.

**PO direction:** Role-based behavior matches the current implementation. Formal decision recording and AT-007 verification remain. This is not a blocker for WP-REC-03C.

**Evidence:** open_questions.md Q-20; backend/app/ai/rag/retriever.py (role_id join); backend/app/api/retrieval.py (server-side role derivation).

---

## 13. Product Owner Decisions and Recommendations

### 13.1 Strategic decisions — Product Owner recommendations

These are Product Owner recommendations for the later WP-STRAT-01 mutation package. They do not authorize repository changes beyond editing this untracked report.

| # | Decision | PO Recommendation | Rationale |
|---|----------|-------------------|-----------|
| SD-1 | Phase 4 completion status | **Reclassify Phase 4 as PARTIALLY COMPLETE** until AT-006 and AT-007 have accepted PASS evidence. Reject the option of keeping Phase 4 COMPLETE while its unchanged exit criteria remain unmet. | SoT 07 exit criteria require AT-006+AT-007 PASS. Evidence is incomplete. Keeping COMPLETE while exit criteria are unmet creates a documentation contradiction. |
| SD-2 | AT-006/AT-007 verification plan | **Use a separate, bounded verification package** for AT-006 and AT-007. Do not assign acceptance-test execution to WP-ARCH-01. | WP-ARCH-01 owns architecture hygiene and agent onboarding, not acceptance-test verification. A bounded verification package keeps scope clean. |
| SD-3 | WP-REC-03C–03G sequence | **Keep the current sequence:** 03C → 03D → 03E → 03F → 03G. User-visible velocity does not justify violating the established dependency sequence. | The decomposition's dependency chain is internally consistent. Reordering would break dependencies and increase risk. |
| SD-4 | WP-REC-05 positioning | **Position WP-REC-05 after WP-REC-03C–03G completion and before Phase 6.** | RAG integration into the AI workflow requires the workflow pipeline (03F) to exist. Phase 6 (approval/audit) requires RAG citations in recommendations. |
| SD-5 | Release 1 framing | **"Controlled AI-assisted Supply Risk Intelligence portfolio MVP demonstrating one complete, auditable, human-approved vertical workflow."** | Emphasizes deterministic control, AI assistance (not autonomy), auditability, human approval, and single vertical workflow. |

### 13.2 Technical decisions — current status

The following technical decisions are NOT all blockers for WP-ARCH-01 or WP-REC-03C. Their current status is recorded below.

| # | Decision | Status | Blocks WP-REC-03C? | Blocks WP-ARCH-01? |
|---|----------|--------|---------------------|---------------------|
| TD-1 | DEC-022: Demo reset mechanism | Undecided; belongs to Phase 7 planning | NO | NO |
| TD-2 | Rate limit values | Undecided; belongs to Phase 7 planning | NO | NO |
| TD-3 | DEC-016: Charts library | Not a blocker; not needed for WP-REC-03C | NO | NO |
| TD-4 | Risk engine ↔ AI output contract | Two-phase direction accepted for later formal recording; not a blocker for 03C | NO | NO |
| TD-5 | Document permission model | Role-based behavior matches current implementation; formal recording and AT-007 verification remain; not a blocker for 03C | NO | NO |
| TD-6 | DEC-015: Permanent state management | Deferred; not a blocker for WP-REC-03C | NO | NO |
| TD-7 | Reranker, object storage, React Flow | All recommended as "no" or "minimal"; not blockers | NO | NO |

**Redis note:** Redis is already required and established through DEC-011 (ARQ + Redis, Accepted). Redis existence is not a new unresolved strategic blocker. The docker-compose.yml includes the redis service, and ARQ uses it for background job dispatch.

### 13.3 Decisions that are NOT required for WP-STRAT-01

The following are explicitly out of scope for WP-STRAT-01 and belong to WP-ARCH-01:
- Architecture hygiene specifics (code structure, import patterns, module boundaries)
- Agent onboarding (agent-loop integration, runtime separation execution)
- SP-0B authorization (separate track, not a Release 1 blocker; SP-0B is READY but NOT AUTHORIZED)
- Any code changes

---

## 14. Proposed WP-STRAT-01 Deliverables

A later WP-STRAT-01 execution package (separately authorized) should produce:

### 14.1 Documents to create

| Document | Purpose |
|----------|---------|
| docs/planning/wp_strat_01_product_strategy.md | Primary strategy artifact. Contains: product definition, target users, Release 1 boundary, capability inventory, gap map, roadmap assessment, proposed sequence, risk register, PO decision record. |

### 14.2 Documents to update

| Document | Changes |
|----------|---------|
| docs/planning/requirements_traceability_matrix.md | Fix stale file references (FR-05, FR-06, FR-07, FR-08, FR-09, FR-12); update AT status table to reflect actual PASS/FAIL; add WP-REC-03A/03B references |
| docs/planning/open_questions.md | Move resolved questions (Q-1/DEC-009, Q-4/DEC-012, Q-5/DEC-013, Q-6/DEC-014, Q-9/DEC-017, Q-16/DEC-024, Q-10/DEC-028) from "Unresolved" to "Resolved"; update remaining with current decision status |
| README.md | Ensure Release 1 framing is consistent (SD-5); update technology-stack table (line 152: provider adapter exists); update implementation status to reflect 03A/03B; correct stale claims |
| docs/next_steps.md | Reclassify Phase 4 as PARTIALLY COMPLETE (SD-1); update AT-006 and AT-007 status to reflect implementation existence and evidence gap; add WP-STRAT-01 as completed when done |
| docs/ACTIVE_WORK.md | Update to reflect WP-STRAT-01 reconnaissance complete; record PO decisions when made |

### 14.3 Source of Truth updates (require explicit PO authorization in the mutation package)

| Document | Changes |
|----------|---------|
| forgemind_project_source_of_truth/07_ROADMAP.md | If PO authorizes: reclassify Phase 4 as PARTIALLY COMPLETE per SD-1; record WP-REC-05 positioning per SD-4. If no change authorized, leave unchanged. |
| forgemind_project_source_of_truth/08_DECISION_LOG.md | If PO authorizes: record new accepted decisions (SD-1 through SD-5, TD-4 two-phase contract, TD-5 role-based permissions). |

Any Source of Truth change remains conditional on explicit authorization in the later mutation package.

### 14.4 What WP-STRAT-01 does NOT deliver

- No code changes
- No test changes
- No dependency changes
- No infrastructure changes
- No migration changes
- No branch creation (until separately authorized for execution)
- No WP-ARCH-01 work
- No WP-REC-03C redesign

---

## 15. Exact Files That a Later Mutation Package Would Update or Create

### 15.1 Files to CREATE (new)

1. `docs/planning/wp_strat_01_product_strategy.md` — Primary product strategy document

### 15.2 Files to UPDATE (existing)

2. `docs/planning/requirements_traceability_matrix.md` — Fix stale references and AT status
3. `docs/planning/open_questions.md` — Move resolved questions, update status
4. `README.md` — Ensure consistent Release 1 framing, fix technology-stack staleness (line 152), update implementation status
5. `docs/next_steps.md` — Reclassify Phase 4 (SD-1), update AT-006/AT-007 status, add WP-STRAT-01
6. `docs/ACTIVE_WORK.md` — Update to reflect WP-STRAT-01 completion and PO decisions

### 15.3 Files that MAY be updated (conditional on explicit PO authorization in the mutation package)

7. `forgemind_project_source_of_truth/07_ROADMAP.md` — Only if PO authorizes reclassification or sequence changes
8. `forgemind_project_source_of_truth/08_DECISION_LOG.md` — Only if PO authorizes recording new accepted decisions

### 15.4 Files that MUST NOT be changed

- All files under `backend/`, `frontend/`, `infra/`, `seed/`, `scripts/`
- All Alembic migrations
- All test files
- `docker-compose*.yml`, `Makefile`, `.env.example`
- `.github/workflows/`
- `HERMES.md` (project contract, not strategy)
- `forgemind_project_source_of_truth/00–06, 09` (Source of Truth — protected)
- `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md` (protected unless PO explicitly requests)
- `forgemind_project_source_of_truth/02_SYSTEM_BEHAVIOR_AND_DATA.md` (protected)
- `forgemind_project_source_of_truth/03_DEFINITION_OF_DONE.md` (protected)
- `forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md` (protected)
- `forgemind_project_source_of_truth/05_DEPLOYMENT_AND_DEMO.md` (protected)
- `forgemind_project_source_of_truth/06_AI_AGENT_EXECUTION_RULES.md` (protected)
- `docs/planning/sp0a_separation_decision.md` (verified internally consistent at baseline; no correction needed)

---

## 16. Explicit Non-Goals for WP-STRAT-01

1. **No implementation.** WP-STRAT-01 is a planning and documentation package. No code, tests, migrations, dependencies, or infrastructure changes.
2. **No WP-ARCH-01 work.** Architecture hygiene and agent onboarding are separate. WP-STRAT-01 records only strategic inputs or questions for WP-ARCH-01 to evaluate.
3. **No WP-REC-03C redesign.** The decomposition plan is not modified. WP-STRAT-01 records PO recommendations on sequencing (SD-3: keep current sequence) but does not redesign packages.
4. **No Source of Truth modification.** Unless the PO explicitly authorizes a change to 07_ROADMAP.md or 08_DECISION_LOG.md in the mutation package, Source of Truth documents are protected.
5. **No branch creation.** This reconnaissance is read-only. A later execution package would create a branch when separately authorized.
6. **No commit, push, or PR.** Explicitly prohibited by authorization.
7. **No deployment infrastructure access.** No VPS access, no Docker operations, no database operations.
8. **No classification of files as obsolete.** Obsolescence hypotheses may be recorded with evidence, but no file is classified as obsolete during reconnaissance.
9. **No invention of release dates or completion percentages.** Per PO restriction.
10. **No marking of acceptance tests as PASS without existing evidence.** Per PO restriction.
11. **No description of Phase 5 or Golden Scenario as complete.** Per PO restriction.

---

## 17. Proposed Validation Criteria

When WP-STRAT-01 is executed (separately authorized), the following criteria validate its completion:

### 17.1 Document quality criteria

| # | Criterion | Verification method |
|---|-----------|-------------------|
| VC-1 | Product strategy document is unambiguous and single-sourced | A fresh session can answer "What is Release 1?" from the strategy document |
| VC-2 | AT status table is accurate and evidence-cited | Each AT status has a file/test/PR citation; AT-006 and AT-007 are not marked PASS without accepted evidence |
| VC-3 | Requirements traceability matrix references only existing files | grep for each referenced path; verify existence |
| VC-4 | Open questions document reflects actual decision status | Cross-check against 08_DECISION_LOG.md |
| VC-5 | Phase 4 status is reclassified as PARTIALLY COMPLETE per SD-1 | docs/next_steps.md and SoT 07_ROADMAP.md are consistent |
| VC-6 | No invented dates or percentages | Scan all new/updated documents for date/percentage claims |
| VC-7 | No AT marked PASS without evidence | Each PASS has a test file or CI evidence citation |
| VC-8 | No file classified as obsolete without PO approval | No "obsolete" classification in any document |
| VC-9 | All strategic decisions have PO verdicts recorded | SD-1 through SD-5 have Accepted/Rejected/Deferred status |
| VC-10 | README technology-stack table reflects provider adapter existence | Line 152 no longer says "planned for Phase 5, not yet implemented" |

### 17.2 Fresh-session test

A new Hermes session should be able to answer these questions from documentation alone:

1. What is ForgeMind Release 1?
2. What is implemented now?
3. What is not implemented?
4. What blocks Release 1?
5. What is the delivery sequence?
6. What decisions are pending?
7. Is WP-REC-03C authorized?
8. What is the Phase 4 completion status?
9. What evidence supports each AT status?
10. What is the product/runtime boundary?

---

## 18. Open Evidence Gaps

| # | Gap | Impact | Resolution path |
|---|-----|--------|-----------------|
| EG-1 | AT-006 has never been confirmed PASS against a live database | Unknown whether RAG retrieval works end-to-end under the full acceptance contract | Execute test_at006_rag_retrieval.py against live PostgreSQL in a bounded verification package (SD-2) |
| EG-2 | AT-007 has never been confirmed PASS under its complete Source of Truth acceptance contract | Implementation exists at service/API level; formal evidence that restricted content is excluded from the complete authenticated retrieval context/response path is missing | Execute formal AT-007 verification in a bounded verification package (SD-2) |
| EG-3 | AT-002 not tested on VPS | Unknown whether auth works in production environment | Phase 7 deployment |
| EG-4 | VPS specifications unknown (CPU, RAM, disk) | Cannot plan deployment resource limits | PO to provide VPS specs when Phase 7 is authorized |
| EG-5 | OpenAI API key availability unverified | Unknown whether AI provider can connect in production | PO to confirm when Phase 5 end-to-end is authorized |
| EG-6 | Domain availability unverified | Cannot plan HTTPS deployment | PO to confirm domain for Phase 7 |
| EG-7 | External user availability for Gate F smoke test | Cannot complete Portfolio Ready | PO to identify external tester |
| EG-8 | Exact backend test count at current origin/main | docs reference "239 backend tests" (Phase 1) and "883 pytest tests" (agent-loop) but current count unverified | Run `make test` or `pytest --co -q` when environment is available |
| EG-9 | GitHub repository settings and secrets not inspected | Unknown whether CI secrets are configured for deployment | PO to verify when Phase 7 is authorized |
| EG-10 | Post-merge CI status on origin/main for latest commit (47acbd8) | docs/next_steps.md references CI SUCCESS for PR #65 merge but not for PR #66 | Check GitHub Actions status for commit 47acbd8 |

---

## 19. Blockers or Deviations

### 19.1 Blockers for WP-STRAT-01 execution

**NONE.** This reconnaissance has completed successfully. No blockers were encountered. All required documents were read. All preflight checks passed. All reviewer findings have been remediated in this updated report.

### 19.2 Deviations from authorization

**NONE.** This session was authorized as read-only reconnaissance.

**Precise confirmation:**
- No tracked repository file was modified.
- Exactly one untracked deliverable file was created: `docs/planning/wp_strat_01_reconnaissance.md`.
- No branch, commit, push, PR, test execution, infrastructure access, or implementation occurred.

**Pre-report state:** The working tree was clean (empty `git status --porcelain=v1`) before the report file was created. After report creation, the working tree contains exactly one untracked file (`docs/planning/wp_strat_01_reconnaissance.md`) and zero modifications to tracked files.

### 19.3 Items requiring PO attention before next step

1. **Review this remediated reconnaissance report.**
2. **Confirm or adjust strategic recommendations SD-1 through SD-5** (§13.1).
3. **Confirm or adjust technical decision statuses TD-1 through TD-7** (§13.2).
4. **Authorize or reject WP-STRAT-01 execution package** (the mutation package that would create/update the documents in §15).
5. **After WP-STRAT-01: authorize WP-ARCH-01** (Architecture Hygiene and Agent Onboarding).
6. **After WP-ARCH-01: reassess WP-REC-03C** authorization.
7. **Authorize a bounded AT-006/AT-007 verification package** (SD-2) — separate from WP-ARCH-01.

---

## 20. Post-Release 1 Strategic Candidate — ForgeMind Spatial Operations Twin

### 20.1 Classification

This is a **post-Release 1 strategic candidate** recorded for future portfolio direction. It is:

- **Not required** for the current Supply Risk Intelligence MVP (Release 1).
- **Not authorized** for implementation.
- **Not assigned** a work-package number.
- **Does not change** the current roadmap sequence (Phases 0–8 and WP-REC-03C–03G remain as defined).
- **Requires separate Product Owner approval** after the portfolio release (PORTFOLIO_READY status achieved).
- **Must use synthetic data and synthetic geography** — no real coordinates, assets, networks, or facilities. All data is invented for the project.

### 20.2 Concept

ForgeMind Spatial Operations Twin is a future "wow-effect" portfolio module built around a **synthetic spatial digital twin** of distributed edge PCs, robots, mobile autonomous assets, and mesh communication nodes. It extends the ForgeMind product narrative from supply chain risk into real-time distributed-operations intelligence.

### 20.3 Proposed capabilities

- **Real-time spatial movement and changing network topology** — assets move through a synthetic geographic space; their positions, connections, and mesh topology update continuously, producing a live, animated operational picture.
- **Link quality, node health, and network-partition visualization** — signal strength, latency, packet loss, battery, CPU/mem load, and node liveness are rendered on the twin; network partitions and island formation are visualized as they emerge.
- **Zero Trust node states** — every node carries a verifiable trust state: `VERIFIED`, `UNKNOWN`, `DEGRADED`, `SUSPECTED`, `ISOLATED`. State transitions are explicit, auditable, and driven by deterministic rules (not LLM guesses), consistent with the architectural principle that deterministic code owns state and permissions (DEC-004). The LLM does not independently control node trust state.
- **Anomaly and connectivity-risk detection** — deterministic detection of connectivity loss, degraded links, node drift, partition formation, and trust-state regression, surfaced as spatial risk events with severity.
- **Deterministic candidate generation + AI explanation** — deterministic graph algorithms and policy rules generate or validate feasible rerouting, isolation, relay-placement, and task-reallocation candidates. The LLM may explain, compare, prioritize, and format only policy-valid candidates. The LLM does not independently control node trust, topology, isolation, or movement. Structured output validation (same schema-validation discipline as Release 1) prevents invalid AI output from being persisted as a decision.
- **What-if simulation before approval** — the operator can preview the projected effect of a proposed action (e.g. "isolate node X", "place relay at position P", "reallocate task T to node Y") on the twin before committing, seeing the simulated topology, connectivity, and risk impact. Human approval remains required before any simulated write action is committed.
- **Human approval and audit replay** — no write action executes without human approval (DEC-005 discipline preserved). Every action, decision, and state transition is recorded in an audit trail that can be replayed as a timeline — showing who approved what, when, and what the spatial state was at that moment.
- **Synthetic industrial, logistics, emergency-response, or field-operations scenarios** — scenario packs (invented assets, invented geography, invented missions) that demonstrate the twin across multiple operational domains without any real-world data. All data, geography, assets, and scenarios remain synthetic.

### 20.4 Portfolio value

A single portfolio scenario that demonstrates in one cohesive demonstration:

- **Distributed systems** — mesh networking, network partitions, eventual consistency, node churn.
- **Event streaming** — real-time position/health/link telemetry flowing through a streaming pipeline.
- **Graph analysis** — topology analysis, connectivity-risk computation, shortest-path and relay-placement reasoning.
- **AI orchestration** — structured AI proposals with validation, retry, and outage handling (extending the Release 1 workflow pattern).
- **Explainability** — every AI proposal includes rationale and cited spatial evidence; every action is replayable.
- **Human-in-the-loop workflows** — approval gate, What-if preview, reject path, audit replay.
- **Real-time visualization** — an animated spatial twin with live state changes, not a static dashboard.

### 20.5 Relationship to Release 1

This candidate **builds on** the Release 1 architecture patterns — deterministic state ownership, structured AI output validation, human-in-the-loop approval, audit traceability, correlation-ID propagation, synthetic-data-only policy, and the explicit state machine. It does **not** alter, block, or redefine any Release 1 requirement. It is recorded here only as a strategic direction for the PO to evaluate after Release 1 achieves PORTFOLIO_READY.

### 20.6 Explicit constraints

- **Not authorized.** No implementation, no design, no branch, no WP number.
- **Synthetic only.** All geography, assets, network topology, telemetry, and scenarios must be invented. No real coordinates, real facilities, real network identifiers, or real operational data.
- **Deterministic control preserved.** Deterministic graph algorithms and policy rules generate or validate all feasible candidates. The LLM may explain, compare, prioritize, and format only policy-valid candidates. The LLM does not independently control node trust, topology, isolation, or movement.
- **Human approval required.** No simulated write action is committed without human approval.
- **Post-Release 1.** This candidate must not delay or influence the Release 1 delivery sequence. It is evaluated only after PORTFOLIO_READY.
- **Separate approval required.** If the PO wishes to pursue this direction, a separate decision-log entry and work-package authorization are required, following the same governance discipline as all ForgeMind work.

---

## END OF REPORT

**Next action:** Product Owner review of this remediated reconnaissance report. STOP and wait for Product Owner decisions.
