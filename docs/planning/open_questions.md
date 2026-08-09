# Open Questions — Pending Product Owner Approval

All items below are tracked for Decision Log entry. Resolved questions are recorded in `forgemind_project_source_of_truth/08_DECISION_LOG.md`.

---

## Resolved Questions (Approved)

### Q-1 — Engineer RBAC Role (DEC-009) — RESOLVED ✓

**Decision:** Engineer is a distinct fifth role with `engineer.demo` account.
**Status:** APPROVED by Product Owner (2026-07-17)
**Recorded in:** 08_DECISION_LOG.md DEC-009

---

### Q-2 — Python Version Pin (DEC-010) — RESOLVED ✓

**Decision:** Pin to Python 3.12.
**Status:** APPROVED by Product Owner (2026-07-15)
**Recorded in:** 08_DECISION_LOG.md DEC-010

---

### Q-3 — Background Job Library (DEC-011) — RESOLVED ✓

**Decision:** ARQ + Redis.
**Status:** APPROVED by Product Owner (2026-07-15)
**Recorded in:** 08_DECISION_LOG.md DEC-011

---

### Q-4 — Real-Time Updates (DEC-012) — RESOLVED ✓

**Decision:** HTTP polling (3s interval for pending jobs, 10s for system status).
**Status:** APPROVED by Product Owner (2026-07-15, Phase 1 scope only)
**Recorded in:** 08_DECISION_LOG.md DEC-012

---

### Q-5 — Workflow Orchestration (DEC-013) — RESOLVED ✓

**Decision:** Custom explicit application-owned state machine. LangGraph not introduced.
**Status:** APPROVED by Product Owner (2026-08-09)
**Recorded in:** 08_DECISION_LOG.md DEC-013

---

### Q-6 — Reverse Proxy (DEC-014) — RESOLVED ✓

**Decision:** Caddy.
**Status:** APPROVED by Product Owner (2026-07-15)
**Recorded in:** 08_DECISION_LOG.md DEC-014

---

### Q-9 — Component Library (DEC-017) — RESOLVED ✓

**Decision:** shadcn/ui + Tailwind CSS.
**Status:** APPROVED by Product Owner (2026-07-15)
**Recorded in:** 08_DECISION_LOG.md DEC-017

---

### Q-10 — Redis in MVP (DEC-011) — RESOLVED ✓

**Decision:** Yes — Redis required for ARQ queue (DEC-011).
**Status:** APPROVED by Product Owner (2026-07-15)
**Recorded in:** 08_DECISION_LOG.md DEC-011
**Note:** Redis is established through DEC-011 and is not an unresolved strategic decision.

---

### Q-16 — Demo Account ↔ Role Mapping (DEC-028) — RESOLVED ✓

**Decision:** 5 demo accounts (manager, procurement, engineer, admin, auditor), one role each.
**Status:** APPROVED by Product Owner (2026-07-17)
**Recorded in:** 08_DECISION_LOG.md DEC-028

---

### Q-18 — Correlation ID Format (DEC-024) — RESOLVED ✓

**Decision:** UUID v4.
**Status:** APPROVED by Product Owner (2026-07-15)
**Recorded in:** 08_DECISION_LOG.md DEC-024

---

### Q-19 — Risk Engine ↔ AI Output Contract (TD-4) — DIRECTION ACCEPTED ✓

**Decision:** Two-phase approach — deterministic engine owns quantities, severity, constraints, feasible facts, and state transitions; AI enriches with explanations, business impact, and structured recommendations.
**Status:** DIRECTION ACCEPTED by Product Owner (2026-08-09). Formal decision recorded in 08_DECISION_LOG.md.
**Consistent with:** DEC-004 (deterministic business logic), SoT 02 §1.

---

### Q-20 — Document Permission Model (TD-5) — DIRECTION ACCEPTED ✓

**Decision:** Role-based access — each role has access to certain document access levels.
**Status:** DIRECTION ACCEPTED by Product Owner (2026-08-09). Formal decision recorded in 08_DECISION_LOG.md. AT-007 verification remains required.
**Current implementation:** `backend/app/ai/rag/retriever.py` (role filtering via SQL join on `document_permissions`), `backend/app/api/retrieval.py` (server-side role derivation).

---

## Deferred Questions (Not Blockers for WP-REC-03C or WP-ARCH-01)

### Q-7 — State Management (DEC-015)

**Context:** `02` §2 says "Zustand або мінімальний state layer."
**Status:** PROPOSED — Phase 1 approach (React hooks + TanStack Query) is sufficient for MVP. Revisit post-Phase 6 if state complexity provides demonstrated need.
**Owner:** Phase 6+ planning.
**Blocks WP-REC-03C:** NO
**Recorded in:** 08_DECISION_LOG.md DEC-015 (Proposed)

---

### Q-8 — Charts Library (DEC-016)

**Context:** `02` §2 says "ECharts або Recharts."
**Recommendation:** Recharts is sufficient for dashboard KPIs if visual charts are needed.
**Status:** DEFERRED — dashboard currently uses text-based widgets; not needed for MVP demo.
**Owner:** Phase 6+ planning (revisit if dashboard needs visual charts).
**Blocks WP-REC-03C:** NO

---

### Q-11 — Reranker in MVP (DEC-019)

**Context:** `02` §2 says "optional reranker."
**Recommendation:** No reranker — pgvector similarity only.
**Status:** DEFERRED — pgvector similarity is sufficient for synthetic data MVP.
**Owner:** Post-MVP optimization.
**Blocks WP-REC-03C:** NO

---

### Q-12 — Object Storage in MVP (DEC-020)

**Context:** `02` §2 says "object storage опціонально."
**Recommendation:** No — store document text and chunks in PostgreSQL.
**Status:** DEFERRED — synthetic documents are small; PostgreSQL text/jsonb is sufficient.
**Owner:** Post-MVP optimization.
**Blocks WP-REC-03C:** NO

---

### Q-13 — React Flow for Workflow Trace (DEC-021)

**Context:** `02` §2 says "React Flow лише для workflow trace, якщо виправдано."
**Recommendation:** No React Flow — use a vertical step/timeline component.
**Status:** DEFERRED — workflow steps are sequential; timeline is simpler and sufficient.
**Owner:** Post-MVP optimization.
**Blocks WP-REC-03C:** NO

---

### Q-14 — Demo Reset Mechanism (DEC-022)

**Context:** FR-12 says admin can reset. AT-015 requires demo reset.
**Status:** UNDECIDED — belongs to Phase 7 planning.
**Owner:** Phase 7 planning.
**Blocks WP-REC-03C:** NO
**Blocks WP-ARCH-01:** NO

---

### Q-15 — Reset Role (DEC-023)

**Context:** FR-12 says "Адміністратор".
**Recommendation:** AI Administrator only.
**Status:** UNDECIDED — belongs to Phase 7 planning.
**Owner:** Phase 7 planning.
**Blocks WP-REC-03C:** NO

---

### Q-17 — Rate Limit Values

**Context:** Gate D and `05` §6 mention rate limiting but specify no numbers.
**Status:** UNDECIDED — belongs to Phase 7 deployment configuration.
**Owner:** Phase 7 planning.
**Blocks WP-REC-03C:** NO
**Blocks WP-ARCH-01:** NO

---

## Summary

| Status | Count | Items |
|--------|-------|-------|
| RESOLVED | 11 | Q-1 (DEC-009), Q-2 (DEC-010), Q-3 (DEC-011), Q-4 (DEC-012), Q-5 (DEC-013), Q-6 (DEC-014), Q-9 (DEC-017), Q-10 (DEC-011), Q-16 (DEC-028), Q-18 (DEC-024), Q-19 (TD-4), Q-20 (TD-5) |
| DEFERRED | 7 | Q-7 (DEC-015 Proposed), Q-8 (DEC-016), Q-11 (DEC-019), Q-12 (DEC-020), Q-13 (DEC-021) |
| UNDECIDED | 3 | Q-14 (DEC-022), Q-15 (DEC-023), Q-17 |

No deferred question blocks WP-REC-03C or WP-ARCH-01. Deferred questions belong to their respective phase owners.
