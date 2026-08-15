# Requirements Traceability Matrix

Mapping each functional requirement (FR-01 through FR-12) to its implementation component, test file(s), and acceptance test(s).

---

## Matrix

| Req | Description | Implementation Component | Backend Test | Frontend Test | Acceptance Test |
|-----|-------------|--------------------------|--------------|---------------|-----------------|
| FR-01 | Authentication — demo users with roles | `backend/app/services/auth_service.py`, `backend/app/api/auth.py` | `tests/integration/test_wp26_auth_integration.py`, `tests/unit/test_auth_service.py` | `frontend/src/contexts/auth.context.test.tsx` | **AT-002** |
| FR-02 | RBAC — users see only allowed documents and actions | `backend/app/dependencies.py` (RBAC middleware), `backend/app/ai/rag/retriever.py` (role-filtered retrieval) | `tests/unit/test_auth_dependencies.py`, `tests/integration/test_retriever_access_filtering.py` | — | **AT-007** |
| FR-03 | Seed Data — one command creates full synthetic dataset | `backend/app/seed/generator/main.py`, `backend/app/seed/generator/*.py` | `tests/seed/test_golden_dataset.py`, `tests/integration/test_risk_engine_with_seed.py` | — | **AT-003** |
| FR-04 | Deterministic Risk Engine — risks calculated by Python/SQL | `backend/app/services/risk_engine.py`, `backend/app/services/bom_explosion.py`, `backend/app/services/inventory_service.py` | `tests/unit/test_risk_engine.py`, `tests/unit/test_bom_explosion.py`, `tests/unit/test_inventory_service.py` | — | **AT-004**, **AT-005** |
| FR-05 | RAG — index synthetic docs, retrieval, cited fragments | `backend/app/services/ingestion.py`, `backend/app/ai/rag/retriever.py`, `backend/app/ai/rag/citations.py` | `tests/integration/test_at006_rag_retrieval.py`, `tests/integration/test_retriever_access_filtering.py` | — | **AT-006**, **AT-007** |
| FR-06 | Structured AI Output — versioned JSON schema, validation | `backend/app/ai/workflow/schema_validator.py`, `backend/app/schemas/recommendation.py`, `backend/app/ai/workflow/prompts.py` (WP-REC-03C, COMPLETE) | `tests/unit/test_schema_validator.py` | — | **AT-008** |
| FR-07 | Workflow Trace — correlation ID, status, timestamps, steps, errors | `backend/app/ai/workflow/state_machine.py`, `backend/app/ai/workflow/engine.py`, `backend/app/core/correlation.py` | `tests/unit/test_workflow_state_machine.py`, `tests/unit/test_workflow_engine.py`, `tests/integration/test_workflow_run_lifecycle.py` | — | **AT-012**, **AT-013** |
| FR-08 | Human Approval — procurement task needs explicit confirmation | _Planned — Phase 6 (WP-REC-04A/04C); decomposition `docs/planning/wp_rec_04_decomposition.md`, DEC-052_ | _Not yet implemented_ | _Not yet implemented_ | **AT-009**, **AT-010** |
| FR-09 | Audit — critical reads, agent runs, approvals, writes logged | _Planned — Phase 6 (WP-REC-04B); decomposition `docs/planning/wp_rec_04_decomposition.md`, DEC-052_ | _Not yet implemented_ | — | **AT-011**, **AT-012** |
| FR-10 | Dashboard — shows actual backend data, not fixtures | `backend/app/api/risks.py`, `frontend/src/routes/dashboard.tsx` | `tests/integration/test_api_risks.py` | `frontend/src/components/dashboard/__tests__/ActivePlanWidget.test.tsx` | **AT-005** |
| FR-11 | Public Demo — HTTPS on VPS | `infra/docker/*.dockerfile`, `infra/caddy/Caddyfile`, `docker-compose.yml` | — | — | **AT-001**, **AT-014** |
| FR-12 | Demo Reset — admin safely restores demo dataset | _Not yet implemented — Phase 7_ | _Not yet implemented_ | — | **AT-015** |

---

## Acceptance Test → Phase Mapping

| Acceptance Test | Phase | Status |
|-----------------|-------|--------|
| AT-001 — Clean deployment | Phase 1 + Phase 7 | REQUIRES DEPLOYMENT/ENVIRONMENT VERIFICATION |
| AT-002 — Demo authentication | Phase 2 | IMPLEMENTED — requires deployment verification |
| AT-003 — Golden Dataset integrity | Phase 2 | ✅ PASS |
| AT-004 — Deterministic risk calculation | Phase 2 | ✅ PASS |
| AT-005 — No hidden UI mocks | Phase 2 + Phase 3 | ✅ PASS |
| AT-006 — RAG retrieval | Phase 4 | ✅ PASS — composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02` (Product Owner acceptance 2026-08-15; DEC-049) |
| AT-007 — Document access control | Phase 4 | ✅ PASS — composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02` (Product Owner acceptance 2026-08-15; DEC-049) |
| AT-008 — Structured output validation | Phase 5 | ✅ PASS — WP-REC-03C (validator) + WP-REC-03E (trace) + WP-REC-03F (worker execution); accepted evidence run `wp-rec-03h-phase-c-20260813-02` (Product Owner acceptance 2026-08-14) |
| AT-009 — Human approval blocks write | Phase 6 | NOT PASS — not implemented; decomposition planned (WP-REC-04-DEC, DEC-052) |
| AT-010 — Approval executes action | Phase 6 | NOT PASS — not implemented; decomposition planned (WP-REC-04-DEC, DEC-052) |
| AT-011 — Reject path | Phase 6 | NOT PASS — not implemented; decomposition planned (WP-REC-04-DEC, DEC-052) |
| AT-012 — Audit trace completeness | Phase 5 + Phase 6 | NOT PASS — not implemented; decomposition planned (WP-REC-04-DEC, DEC-052) |
| AT-013 — Model outage | Phase 5 | ✅ PASS — WP-REC-03D (automatic retry) + WP-REC-03E (trace) + WP-REC-03F (backend start/retry/worker) + WP-REC-03G (UI); accepted evidence run `wp-rec-03h-phase-c-20260813-02` (Product Owner acceptance 2026-08-14) |
| AT-014 — Public HTTPS smoke test | Phase 7 | REQUIRES DEPLOYMENT/ENVIRONMENT VERIFICATION |
| AT-015 — Demo reset | Phase 7 | NOT IMPLEMENTED |

**AT-006 and AT-007 are PASS** via the accepted composite of sealed packages `wp-rec-05-vfy-20260814-01` and `wp-rec-05-vfy-20260815-02` (Product Owner acceptance 2026-08-15, DEC-049).

---

## WP-REC-03 Package References

| Package | Status | Evidence |
|---------|--------|----------|
| WP-REC-03A (AI Provider Adapter) | COMPLETE | PR #63 merged at `5c86000`; `backend/app/ai/provider/` (chat_provider, openai_chat_provider, fake_chat_provider, factory, exceptions) |
| WP-REC-03B (Workflow/State-Machine Foundation) | COMPLETE | PR #65 merged at `fc48aed`; `backend/app/ai/workflow/` (state_machine, engine); `backend/app/models/workflow.py`; Alembic migration |
| WP-REC-03C (Structured-Output Validation) | COMPLETE | PR #72 merged at `d82b9aa`; `backend/app/ai/workflow/schema_validator.py`, `backend/app/schemas/recommendation.py`, `backend/app/ai/workflow/prompts.py` |
| WP-REC-03D (Automatic Provider Retry/Outage — Backend) | COMPLETE | PR #73 merged at `212735e`; automatic provider retry/outage handler, retry policy |
| WP-REC-03E (Workflow-Run Detail + Recommendation UI) | COMPLETE | PR #74 merged at `82b4497`; read-only workflow-run detail API, recommendation UI, TanStack Query hook |
| WP-REC-03F (Backend Workflow Start/Retry API + ARQ Worker) | COMPLETE | PR #78 merged at `aab1323`; backend start/retry API, ARQ worker functions, D6 reconciler cron job, dispatch generation |
| WP-REC-03G (Frontend Start/Retry UI Interaction) | COMPLETE | PR #80 merged at `1582c39`; frontend start/retry controls, stale-mutation protection, deterministic polling lifecycle |
| WP-REC-05-DEC (RAG integration planning) | COMPLETE — CLOSED | Planning artifact `docs/planning/wp_rec_05_rag_integration.md` delivered via PR #87, regular merge commit `e3a9a4572075840e8f1aa71b671ef0dd50dc2eb1`; successful post-merge verification; accepted decisions DEC-044, DEC-045, DEC-046. Does not authorize implementation or verification |
| WP-REC-05 (RAG integration implementation) | COMPLETE | Merged via PR #89 (regular merge commit `86e2d0cd3d6d3eaf889ca6d674829f7ac541778c`, 2026-08-14); strict post-merge verification passed. Implementation-completion owner for the AT-006/AT-007 workflow path |
| WP-REC-05-PROVIDER-IMP (external chat-provider chain and grounded-output hardening) | COMPLETE | Merged via PR #91 (regular merge commit `7d425c1d3f1e92e08d62360c28ced22481136fe7`, 2026-08-14); strict post-merge verification passed; DEC-048. This package did not itself perform live inference; external live interoperability was subsequently demonstrated for OpenRouter `qwen/qwen3.7-flash` via the WP-REC-05-VFY formal rerun (DEC-049). AT-006/AT-007 PASS belongs to WP-REC-05-VFY and the Product Owner acceptance (DEC-049), not to this package. No provider credentials/budget are configured in the repository for general use. |
| WP-REC-05-VFY (AT-006/AT-007 verification) | ACCEPTED | Composite of sealed packages `wp-rec-05-vfy-20260814-01` (aggregate `f37f0ac8…`) and `wp-rec-05-vfy-20260815-02` (aggregate `2ce0ba6f…`) accepted by the Product Owner 2026-08-15 (DEC-049); AT-006 PASS; AT-007 PASS. Separate bounded verification package (DEC-035); follows WP-REC-05 implementation |
| WP-REC-04-DEC (Phase 6 contract and decomposition) | PREPARED — documentation-only | Decision and planning package (DEC-052, accepted 2026-08-15); decomposition `docs/planning/wp_rec_04_decomposition.md`; Phase 6 reconnaissance COMPLETE; AT-009–AT-012 NOT PASS; Phase 6 implementation NOT STARTED; next planned implementation package WP-REC-04B (audit-event backend foundation) |

---

## Coverage Summary

- **12 functional requirements** mapped to implementation + tests.
- **15 acceptance tests** mapped to phases.
- FR-06 now has implementation via WP-REC-03C (COMPLETE). FR-08, FR-09, FR-12 reference capabilities not yet implemented — marked as such; no nonexistent file paths cited.
- AT-006 and AT-007 are PASS (composite accepted evidence packages `wp-rec-05-vfy-20260814-01` + `wp-rec-05-vfy-20260815-02`, Product Owner acceptance 2026-08-15, DEC-049).
- AT-006/AT-007 implementation completion is owned by WP-REC-05 (COMPLETE, merged via PR #89) and WP-REC-05-PROVIDER-IMP (COMPLETE, merged via PR #91); formal verification is owned by the separate WP-REC-05-VFY package (ACCEPTED, DEC-049). Phase 4 is closed/accepted.
- AT-001, AT-002, AT-014 require deployment/environment verification.
- AT-008 and AT-013 are PASS (accepted evidence run `wp-rec-03h-phase-c-20260813-02`, Product Owner acceptance 2026-08-14; durable review `docs/reviews/wp_rec_03h_phase_d_independent_evidence_review.md`, durable acceptance declaration `docs/reviews/wp_rec_03h_phase_d_product_owner_acceptance_declaration.md`).
- AT-009, AT-010, AT-011, AT-012, AT-015 require capabilities that are not implemented. AT-009 through AT-012 remain NOT PASS: Phase 6 is decomposed via `docs/planning/wp_rec_04_decomposition.md` (WP-REC-04-DEC, DEC-052) and Phase 6 implementation remains NOT STARTED. The next planned implementation package after WP-REC-04-DEC closure is WP-REC-04B (audit-event backend foundation).
