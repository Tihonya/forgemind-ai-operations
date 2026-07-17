# Phase 2 — Product Owner Decision Sheet

**Date:** 2026-07-17  
**Phase:** Phase 2 — Synthetic ERP Core  
**Status:** DEC-009 and DEC-028 APPROVED by Product Owner.

---

## DEC-009 — Engineer RBAC role (UPDATED)

**Date:** 2026-07-15  
**Status:** **Accepted** (updated from Proposed, 2026-07-17)  
**Context:** `01_PRODUCT_AND_MVP_SCOPE.md` §5 lists five target users; FR-01 listed four roles.  
**Decision:** Engineer is a 5th distinct RBAC role with `engineer.demo` account. Engineer must not inherit Production Manager or AI Administrator privileges automatically.  
**Reason:** Engineer has distinct behavior (views technical docs and alternatives) and warrants a separate RBAC identity.  
**Consequences:** `roles` table contains 5 codes; seed creates 5 demo accounts; auth middleware supports 5 role codes.  
**Affected documents/tests:** FR-01, FR-02, AT-002, `roles` table, `users` table, `user_roles` table, seed generator.  
**Approved by:** Product Owner (2026-07-17)

---

## DEC-028 — Demo account ↔ role mapping (OFFICIALLY RECORDED)

**Date:** 2026-07-17  
**Status:** **Accepted**  
**Context:** Five demo accounts existed as candidates in planning since Phase 1 closeout (`docs/next_steps.md`, `docs/phase_1/phase_1_completion_report.md`, `docs/planning/product_owner_decision_sheet.md`) but were not recorded as an official Decision Log entry.

**Numbering note:** DEC-028 was assigned in planning documents during Phase 1 closeout (it is the 28th decision identifier in project history: DEC-001 through DEC-033 minus skipped). This entry preserves that established number rather than reassigning it.

**Decision:** One primary role per demo account in Phase 2. The `user_roles` data model must support multiple roles per user (for future phases), but in Phase 2 each Golden Dataset account receives exactly one role.

**Account mapping:**

| Username | Role |
|---|---|
| `manager.demo` | Production Manager |
| `procurement.demo` | Procurement Specialist |
| `engineer.demo` | Engineer |
| `admin.demo` | AI Administrator |
| `auditor.demo` | Auditor |

**Constraints:**
- Document-level authorization and RAG filtering are deferred to Phase 4.
- Phase 2 must not implement `document_permissions` or RAG-based access control.
- Phase 2 must preserve `user_roles` cardinality of 1 → N (multi-role capable).

**Consequences:** `users` table has 5 initial rows; `roles` table has 5 rows; `user_roles` has 5 rows (one per user). Auth middleware and seed generator must match this mapping exactly.  
**Affected documents/tests:** `users`, `roles`, `user_roles` tables, seed generator, auth middleware, AT-002.  
**Approved by:** Product Owner (2026-07-17)

---

## Phase 2 Boundary — Approved

### In scope
- Canonical business-domain specification (this document set).
- Business schema (SQLAlchemy 2 models + Alembic migration).
- Reversible Alembic migrations.
- Deterministic Golden Dataset (RISK-001, RISK-002, RISK-003).
- Seed command (`make seed`).
- Dataset version/checksum verification (AT-003).
- Users, roles and user-role mapping (entities, no login yet).
- Five demo accounts (DEC-028 mapping).
- Backend authentication (login endpoint, JWT/session tokens).
- RBAC foundation (role-checking middleware).
- CRUD/read REST APIs for Phase 2 entities.
- Deterministic BOM, inventory and supply-risk calculations.
- Automated evidence for AT-003 and AT-004.
- Backend/integration preparation for AT-005 (no UI required).
- Zero LLM dependencies.

### Out of scope
- RAG, embeddings, model calls, AI workflow.
- Document-level authorization (Phase 4).
- Complete Dashboard and Core UI (Phase 3).
- Approval workflow and procurement-task execution (Phase 6).
- Public HTTPS deployment, Caddy, production rate limiting (Phase 7).
- Authenticated public demo reset (Phase 7); developer/test seed reset is allowed in Phase 2.

### AT-005 handling
Full browser evidence for AT-005 (UI reflects backend result after fixture change) requires Core UI (Phase 3). Phase 2 delivers the backend contract: risk calculation reads from the database and returns fresh results; any seed change is reflected in API output without code changes. Automated integration tests verify the deterministic-to-API chain — the UI verification is deferred to Phase 3.

---

## Work-Package Plan

| WP | Name | Purpose |
|---|---|---|
| WP-2.1 | Canonical business model specification | Planning artifact: entities, fields, relationships, Golden Dataset mapping. Complete when this spec is PO-approved. |
| WP-2.2 | Business schema foundation | SQLAlchemy 2 models, constraints, indexes and reversible Alembic migration for all Phase 2 entities. |
| WP-2.3 | Golden Dataset fixtures and seed generator | Versioned deterministic seed data + `make seed` command producing RISK-001/002/003 exactly; clean-state and idempotent. |
| WP-2.4 | Golden Dataset integrity | Dataset version/checksum; automated AT-003 evidence proving fixture integrity after seed. |
| WP-2.5 | Authentication data foundation | `users`, `roles`, `user_roles` tables + five DEC-028 single-role demo accounts seeded by WP-2.3. |
| WP-2.6 | Authentication and RBAC services | Login endpoint, password verification, JWT/session contract, role-checking middleware; no document-level permissions. |
| WP-2.7 | Business read/CRUD APIs | Read-only endpoints for plans, orders, BOM, components, inventory, reservations, suppliers, purchase orders, alternatives. |
| WP-2.8 | Deterministic supply-risk engine | BOM explosion, inventory availability, reservations, incoming supply, need-date calculations and severity rules. |
| WP-2.9 | Golden Scenario acceptance | Exactly RISK-001, RISK-002, RISK-003 with expected quantities and severity; automated AT-004 evidence. |
| WP-2.10 | Phase 2 integration and closeout | Backend/integration preparation for AT-005, zero-LLM verification, smoke evidence and completion report. |

WP order reflects dependency chain. WP-2.1 (spec) is first — no code depends on it, all subsequent WPs do. WP-2.3 produces the Golden Dataset that WP-2.9 consumes. WP-2.5 depends on WP-2.2; WP-2.6 depends on WP-2.5. WP-2.7 is readable independently of WP-2.8/2.9 but integrates with them for end-to-end evidence. WP-2.10 closes the phase.

---

*End of decision sheet.*
