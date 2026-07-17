# Phase 2 — Product Owner Decision Sheet

**Date:** 2026-07-17
**Branch:** `feature/phase-2-synthetic-erp-planning`
**Status:** Accepted planning artifact

---

## DEC-009 — Engineer RBAC role

**Date:** 2026-07-15
**Status:** Accepted
**Context:** `01_PRODUCT_AND_MVP_SCOPE.md` §5 lists five target users; FR-01 listed four roles.
**Decision:** Engineer is a distinct fifth role and must not automatically inherit privileges from any other role, including Production Manager, Procurement Specialist or AI Administrator.
**Consequence:** `users` table contains 5 initial rows; `roles` table contains 5 rows; `user_roles` table contains 5 rows. Role codes: `PRODUCTION_MANAGER`, `PROCUREMENT_SPECIALIST`, `ENGINEER`, `AI_ADMINISTRATOR`, `AUDITOR`.
**Affected documents/tests:** AT-002, `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md`, `08_DECISION_LOG.md`.
**Phase 2 implementation scope:** Implement login endpoint + role middleware; enforce role-based access to system endpoints (e.g., `/api/v1/system/dataset/reset` restricted to AI_ADMINISTRATOR). Full role-specific UI behavior deferred to Phase 3.

**Resolution note (2026-07-17):** Phase 2 implements authentication and backend RBAC enforcement. AT-002 full UI evidence (Dashboard per role) is deferred to Phase 3 because Core UI does not yet exist.

---

## DEC-028 — Demo account ↔ role mapping

**Date:** 2026-07-17
**Status:** Accepted
**Context:** 5 demo accounts must map to 5 roles for Phase 2 seed data.
**Decision:** One primary role per demo account in Phase 2.

**Mapping table:**

| Username | Display | Password (bcrypt demo hash) | Role code |
|----------|---------|-----------------------------|-----------|
| `manager.demo` | Production Manager | `manager123` | `PRODUCTION_MANAGER` |
| `procurement.demo` | Procurement Specialist | `procurement123` | `PROCUREMENT_SPECIALIST` |
| `engineer.demo` | Engineer | `engineer123` | `ENGINEER` |
| `admin.demo` | AI Administrator | `admin123` | `AI_ADMINISTRATOR` |
| `auditor.demo` | Auditor | `auditor123` | `AUDITOR` |

**Schema constraint:** `user_roles` supports multiple roles per user (N:N relationship via join table) — future-proof for later phases.
**Affected documents/tests:** AT-002, seed fixtures, `users`/`roles`/`user_roles` tables.

---

## DEC-029 — Phase 1 authentication deferral

**Date:** 2026-07-15
**Status:** Accepted
**Context:** `07_ROADMAP.md` Phase 1 deliverables include "basic login page." `04_ACCEPTANCE_TESTS.md` AT-002 (demo authentication) is mapped to Phase 1. The Phase 1 brief focuses on the Operations Control Plane.
**Decision:** Defer all authentication to Phase 2. Phase 1 does not implement login, JWT, sessions, RBAC, or demo accounts.
**Consequences:** `07_ROADMAP.md` Phase 1 deliverable "basic login page" is deferred to Phase 2. AT-002 moves to Phase 2. This is a scope change approved by the Product Owner.
**Constraints (approved by Product Owner):**
- Phase 1 must not be publicly deployed.
- Phase 1 must not process real, sensitive, or production data.
- Diagnostic endpoints must be documented as development/demo-only.
**Affected documents/tests:** AT-002, `07_ROADMAP.md` Phase 1 deliverables, requirements_traceability_matrix.md.

**Resolution note (2026-07-17):** Phase 2 implements authentication and backend RBAC; full role-specific UI evidence for AT-002 is completed in Phase 3.

---

## Resolution Summary (2026-07-17, Phase 2 planning review)

All BLOCKING findings from the Phase 2 planning review have been resolved:

### 1. RISK-003 source document — RESOLVED
- **Finding:** Business model spec §7 RISK-003 derivation stated "Alternative candidate exists in component_alternatives (SENSOR-L9, status=PROPOSED)" but Source of Truth `02_SYSTEM_BEHAVIOR_AND_DATA.md` §4 RISK-003 said "Candidate alternative exists in draft document but is not approved" — implying document retrieval (Phase 4).
- **Resolution:** `component_alternatives` is a deterministic business projection of an engineering alternative and its approval status (planning clarification derived from DEC-004 + Phase 2 zero-LLM constraint + Phase 4 RAG scope). Phase 2 risk engine reads only structured data. Phase 4 adds actual document entities and verifies the documentary evidence behind structural alternatives. The Phase 2 arithmetic is unchanged; Phase 4 enriches the data. Source of Truth `02_SYSTEM_BEHAVIOR_AND_DATA.md` is NOT modified — its RISK-003 description is the intended end-state description; Phase 2 implements the deterministic precursor.
- **Files modified:** `docs/planning/phase_2_business_model_spec.md` §1.3, §7, §10; `docs/planning/phase_2_work_package_plan.md` WP-2.8 notes.

### 2. Inventory reservation subtraction rule — RESOLVED
- **Finding:** Business model spec §4 lines 189-195 contained contradictory statements: line 189 said "subtract ALL reservations", line 190-195 said "subtract only reservations for OTHER work orders".
- **Resolution:** Business model spec §4 now states the canonical rule unambiguously: for WO-X, `available = on_hand − sum(reservations where po_id ≠ WO-X.id and parent_order.status in (PLANNED, RELEASED, IN_PROGRESS))`. The current WO's own reservation is NOT subtracted — the WO is the claimant of the available quantity.
- **Files modified:** `docs/planning/phase_2_business_model_spec.md` §4.

### 3. PO line late delivery semantics — RESOLVED
- **Finding:** Business model spec §5 lines 200-204 were contradictory: lines 200-201 said PO line does NOT contribute if date > need_date, line 203 said PO line with date > need_date → HIGH severity.
- **Resolution:** Business model spec §5 now clarifies:
  - PO lines with `status ∈ {CONFIRMED, IN_TRANSIT, DELIVERED}` AND `expected_delivery_date ≤ need_date` contribute to `confirmed_early_supply` (reduces shortage).
  - PO lines with `status ∈ {CONFIRMED, IN_TRANSIT}` AND `expected_delivery_date > need_date` do NOT reduce shortage but are recorded as `confirmed_late_supply` to trigger HIGH severity.
  - PO lines with `status ∈ {PLACED, CANCELLED}` are excluded from all supply calculations.
  - PO lines with header status `RECEIVED` or line status `DELIVERED` have their received quantities already reflected in `inventory_balances.quantity_on_hand` (no double counting).
- **Files modified:** `docs/planning/phase_2_business_model_spec.md` §5.

### 4. WP-2.7 atomicity — RESOLVED
- **Finding:** WP-2.7 "Business read/CRUD APIs" delivered 10+ files (production_plans, production_orders, components, inventory, purchase_orders, suppliers + schemas + tests). Too large for atomic commit.
- **Resolution:** WP-2.7 split into WP-2.7A (core: plans/orders/components/products) and WP-2.7B (supply: inventory/warehouses/purchase_orders/suppliers). Both are now atomic work packages with separate commits.
- **Files modified:** `docs/planning/phase_2_work_package_plan.md` WP-2.7.

### 5. AT-005 "preparation" ambiguity — RESOLVED
- **Finding:** WP-2.10 line 454 said "AT-005 preparation" is vague. AT-005 requires UI (Phase 3).
- **Resolution:** WP-2.10 now states: "AT-005 backend contract test proving API returns fresh results after seed change. Full AT-005 UI evidence deferred to Phase 3 (Core UI required)."
- **Files modified:** `docs/planning/phase_2_work_package_plan.md` WP-2.10.

### 6. LOW severity safety-margin threshold undefined — RESOLVED
- **Finding:** Business model spec §8 line 262 defined LOW severity as "available − required < safety-margin threshold" but threshold was undefined.
- **Resolution:** Business model spec §8 now clarifies: LOW severity is part of the domain vocabulary but is not exercised by the Phase 2 Golden Dataset. No Phase 2 acceptance criterion depends on producing a LOW risk. A precise LOW rule (e.g., threshold = 10% of required) may be approved later when a scenario requires it.
- **Files modified:** `docs/planning/phase_2_business_model_spec.md` §8.

### 7. AT-002 partial vs full evidence — RESOLVED
- **Finding:** AT-002 requires "Dashboard per role" (UI, Phase 3), but WP-2.6 claimed "partial evidence".
- **Resolution:** WP-2.6 now states: "AT-002 backend evidence only (login works, roles enforced) — full role-specific UI evidence deferred to Phase 3."
- **Files modified:** `docs/planning/phase_2_work_package_plan.md` WP-2.6.

---

## Work-Package Plan Summary

| WP ID | Name | Status | Dependencies | Notes |
|-------|------|--------|--------------|-------|
| WP-2.1 | Canonical business model spec | ✅ Complete | — | Accepted 2026-07-17 |
| WP-2.2 | Business schema foundation | Pending | WP-2.1 | Phase 2 entities (no auth yet) |
| WP-2.3 | Golden Dataset fixtures and seed generator | Pending | WP-2.2 | Deterministic seed (all entities incl. auth) |
| WP-2.4 | Golden Dataset integrity | Pending | WP-2.3 | AT-003 |
| WP-2.5 | Auth data foundation | Pending | WP-2.2, WP-2.3 | Users/roles/role mappings |
| WP-2.6 | Auth and RBAC services | Pending | WP-2.5 | AT-002 backend |
| WP-2.7A | Core production read APIs | Pending | WP-2.2, WP-2.3 | Production, orders, components |
| WP-2.7B | Supply and inventory read APIs | Pending | WP-2.2, WP-2.3, WP-2.7A | Inventory, suppliers, POs |
| WP-2.8 | Deterministic supply-risk engine | Pending | WP-2.7A, WP-2.7B | BOM/inventory/PO/severity logic |
| WP-2.9 | Golden Scenario acceptance | Pending | WP-2.8 | AT-004 |
| WP-2.10 | Phase 2 integration and closeout | Pending | WP-2.1–WP-2.9 | AT-005 backend, completion report |

**Execution order:** WP-2.1 → 2.2 → {2.3 → 2.4, 2.5 → 2.6} → {2.7A, 2.7B} → 2.8 → 2.9 → 2.10

---

**End of decision sheet.**
