# Requirements Traceability Matrix

Mapping each functional requirement (FR-01 through FR-12) to its implementation component, test file(s), and acceptance test(s).

---

## Matrix

| Req | Description | Implementation Component | Backend Test | Frontend Test | Acceptance Test |
|-----|-------------|--------------------------|--------------|---------------|-----------------|
| FR-01 | Authentication — demo users with roles | `backend/app/services/auth_service.py`, `backend/app/api/auth.py` | `tests/integration/test_api_auth.py` | `frontend/tests/login.test.tsx` | **AT-002** |
| FR-02 | RBAC — users see only allowed documents and actions | `backend/app/dependencies.py` (RBAC middleware), `backend/app/ai/rag/retriever.py` (role-filtered retrieval) | `tests/unit/test_rbac.py`, `tests/integration/test_rag_retrieval.py` | — | **AT-007** |
| FR-03 | Seed Data — one command creates full synthetic dataset | `seed/generator/main.py`, `seed/generator/*.py` | `tests/integration/test_seed.py` | — | **AT-003** |
| FR-04 | Deterministic Risk Engine — risks calculated by Python/SQL | `backend/app/services/risk_engine.py`, `backend/app/services/bom_explosion.py`, `backend/app/services/inventory_service.py` | `tests/unit/test_risk_engine.py`, `tests/unit/test_bom_explosion.py`, `tests/unit/test_inventory.py` | — | **AT-004**, **AT-005** |
| FR-05 | RAG — index synthetic docs, retrieval, cited fragments | `backend/app/ai/rag/indexer.py`, `backend/app/ai/rag/retriever.py`, `backend/app/ai/rag/citations.py` | `tests/integration/test_rag_retrieval.py` | — | **AT-006**, **AT-007** |
| FR-06 | Structured AI Output — versioned JSON schema, validation | `backend/app/schemas/ai_output.py`, `backend/app/ai/output_validator.py` | `tests/unit/test_output_validator.py` | — | **AT-008** |
| FR-07 | Workflow Trace — correlation ID, status, timestamps, steps, errors | `backend/app/ai/workflow/runner.py`, `backend/app/ai/workflow/machine.py`, `backend/app/ai/workflow/steps.py`, `backend/app/core/correlation.py` | `tests/integration/test_workflow_trace.py` | — | **AT-012**, **AT-013** |
| FR-08 | Human Approval — procurement task needs explicit confirmation | `backend/app/services/approval_service.py`, `backend/app/api/approvals.py` | `tests/unit/test_approval_service.py`, `tests/integration/test_api_approvals.py` | `frontend/tests/approval.test.tsx` | **AT-009**, **AT-010** |
| FR-09 | Audit — critical reads, agent runs, approvals, writes logged | `backend/app/services/audit_service.py`, `backend/app/api/audit.py` | `tests/integration/test_audit_trace.py` | — | **AT-011**, **AT-012** |
| FR-10 | Dashboard — shows actual backend data, not fixtures | `backend/app/api/dashboard.py`, `frontend/src/routes/dashboard.tsx` | `tests/integration/test_api_dashboard.py` | `frontend/tests/dashboard.test.tsx` | **AT-005** |
| FR-11 | Public Demo — HTTPS on VPS | `infra/docker/*.dockerfile`, `infra/caddy/Caddyfile`, `docker-compose.yml` | — | — | **AT-001**, **AT-014** |
| FR-12 | Demo Reset — admin safely restores demo dataset | `backend/app/services/reset_service.py`, `backend/app/api/admin.py` | `tests/integration/test_reset.py` | — | **AT-015** |

---

## Acceptance Test → Phase Mapping

| Acceptance Test | Phase | Status (pre-implementation) |
|-----------------|-------|----------------------------|
| AT-001 — Clean deployment | Phase 1 + Phase 7 | PENDING |
| AT-002 — Demo authentication | Phase 1 | PENDING |
| AT-003 — Golden Dataset integrity | Phase 2 | PENDING |
| AT-004 — Deterministic risk calculation | Phase 2 | PENDING |
| AT-005 — No hidden UI mocks | Phase 2 + Phase 3 | PENDING |
| AT-006 — RAG retrieval | Phase 4 | PENDING |
| AT-007 — Document access control | Phase 4 | PENDING |
| AT-008 — Structured output validation | Phase 5 | PENDING |
| AT-009 — Human approval blocks write | Phase 6 | PENDING |
| AT-010 — Approval executes action | Phase 6 | PENDING |
| AT-011 — Reject path | Phase 6 | PENDING |
| AT-012 — Audit trace completeness | Phase 5 + Phase 6 | PENDING |
| AT-013 — Model outage | Phase 5 | PENDING |
| AT-014 — Public HTTPS smoke test | Phase 7 | PENDING |
| AT-015 — Demo reset | Phase 7 | PENDING |

---

## Coverage Summary

- **12 functional requirements** mapped to implementation + tests.
- **15 acceptance tests** mapped to phases.
- Every FR has at least one backend test.
- Every AT is assigned to exactly one or two phases.
- No requirement is untested; no test is orphaned.
