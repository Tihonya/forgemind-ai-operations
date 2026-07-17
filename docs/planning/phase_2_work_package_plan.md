# Phase 2 — Work Package Plan

**Purpose:** Atomic, dependency-ordered work packages delivering Phase 2 exit criteria.  
**Base commit:** `e9beefdef3a753f95bfe193442b5acec96f69d83`  
**Branch:** `feature/phase-2-synthetic-erp-planning`  
**Reference documents:**  
- `docs/planning/phase_2_business_model_spec.md`  
- `docs/planning/phase_2_decision_sheet.md`  
- `forgemind_project_source_of_truth/08_DECISION_LOG.md` (DEC-009, DEC-028, DEC-029)

---

## WP-2.1 — Canonical business model specification

**Objective:** Define the conceptual business data model (entities, fields, relationships, semantics, Golden Dataset mapping) before any code is written.

**Included scope:**
- `docs/planning/phase_2_business_model_spec.md`
- Validation against Source of Truth (01, 02, 04)

**Excluded scope:**
- SQLAlchemy models, migrations, seed data, API contracts.

**Dependencies:** None. This WP is the foundation.

**Expected files:**
- `docs/planning/phase_2_business_model_spec.md` (already created and validated)

**Tests/checks:**
- PO review against Source of Truth
- Verification that RISK-001/002/003 derivation is explicit and deterministic

**Acceptance evidence:**
- Document marked "Accepted" by PO
- All mandatory sections present (entities, fields, keys, cardinalities, statuses, semantics, Golden Dataset mapping)

**Completion criteria:**
- PO-approved spec with no contradictions to Source of Truth
- Zero implementation code

**Proposed atomic commit:** Already committed in planning phase.

**Status:** ✅ COMPLETE (validated 2026-07-17)

---

## WP-2.2 — Business schema foundation

**Objective:** Translate WP-2.1 specification into SQLAlchemy 2 models with constraints, indexes, and a single reversible Alembic migration.

**Included scope:**
- All 14 Phase 2 entities from `phase_2_business_model_spec.md` §1
- SQLAlchemy 2 ORM models in `backend/app/models/`
- One Alembic migration creating all Phase 2 tables
- FK constraints, unique constraints, indexes

**Excluded scope:**
- Seed data (WP-2.3)
- Auth entities (WP-2.5)
- API endpoints (WP-2.7)
- Risk engine (WP-2.8)

**Dependencies:**
- WP-2.1 (spec) must be complete

**Expected files:**
- `backend/app/models/*.py` (one file per entity or grouped logically)
- `backend/alembic/versions/<timestamp>_business_schema.py`

**Tests/checks:**
- `alembic upgrade head` succeeds on clean DB
- `alembic downgrade -1` succeeds (reversible)
- All FK constraints enforced (tested via integration tests)
- Python types match conceptual spec (decimal(18,4), date vs datetime)
- `mypy --strict` passes on models

**Acceptance evidence:**
- Migration creates all 14 tables with correct columns
- Downgrade removes all tables cleanly
- No seed data present after migration

**Completion criteria:**
- Migration reversible
- Schema matches spec exactly
- Zero hardcoded values

**Proposed atomic commit:**
```text
feat(schema): implement Phase 2 business data models and migration
```

---

## WP-2.3 — Golden Dataset fixtures and seed generator

**Objective:** Create versioned deterministic seed data producing exactly RISK-001, RISK-002, RISK-003 with correct quantities and severity; provide `make seed` command for clean-state seeding.

**Included scope:**
- Seed data files (YAML or JSON) containing all 14 entities
- Seed generator script reading fixtures and inserting into DB
- `make seed` target in Makefile
- Clean-state behavior (idempotent: safe to run multiple times)
- Developer/test reset capability (`make reset` — truncates and re-seeds)

**Excluded scope:**
- AT-003 verification (WP-2.4)
- Auth entities (WP-2.5)
- Public demo reset (Phase 7)

**Dependencies:**
- WP-2.2 (schema must exist)

**Expected files:**
- `seed/fixtures/*.yaml` (one file per entity group)
- `seed/generator/*.py`
- `seed/generator/main.py` (entry point)
- `Makefile` updates (`seed`, `reset` targets)

**Tests/checks:**
- `make seed` on clean DB creates all rows
- After seed, risk engine returns exactly 3 risks (integration test placeholder)
- `make reset` truncates all business tables and re-seeds identically
- Seed is idempotent (running twice yields same state)
- No floating-point drift in quantities

**Acceptance evidence:**
- Seed command executes without errors
- RISK-001/002/003 derivation inputs match specification (verified by manual query or test)
- Dataset version/checksum recorded (preparation for WP-2.4)

**Completion criteria:**
- `make seed` works on clean DB
- Seed data produces correct risk inputs
- Developer reset functional

**Proposed atomic commit:**
```text
feat(seed): implement Golden Dataset fixtures and seed generator
```

---

## WP-2.4 — Golden Dataset integrity

**Objective:** Implement dataset version and checksum verification; provide automated AT-003 evidence proving fixture integrity after seed.

**Included scope:**
- Dataset version string (e.g., `GOLDEN_DATASET_V1.0`)
- Checksum or hash of seed fixtures (SHA-256 of concatenated YAML/JSON)
- Automated test querying dataset metadata and comparing to expected checksum
- `GET /api/v1/system/dataset/status` endpoint returning version + checksum

**Excluded scope:**
- Runtime dataset modification (read-only in Phase 2)
- Public demo reset (Phase 7)

**Dependencies:**
- WP-2.3 (seed must exist to compute checksum)

**Expected files:**
- `backend/app/services/dataset_integrity.py`
- `backend/app/api/system.py` (new endpoint)
- `backend/tests/unit/test_dataset_integrity.py`
- `backend/tests/integration/test_api_dataset_status.py`

**Tests/checks:**
- AT-003 acceptance test passes (automated)
- Checksum mismatch detected and reported
- Dataset version exposed via API

**Acceptance evidence:**
- `pytest tests/integration/test_api_dataset_status.py` passes
- Checksum matches expected value in source code
- Tampered fixture detected by test

**Completion criteria:**
- AT-003 automated evidence exists
- Dataset integrity verifiable via API

**Proposed atomic commit:**
```text
feat(seed): add dataset version and checksum verification (AT-003)
```

---

## WP-2.5 — Authentication data foundation

**Objective:** Add `users`, `roles`, `user_roles` tables and seed five DEC-028 demo accounts with single-role assignment.

**Included scope:**
- SQLAlchemy models for `users`, `roles`, `user_roles`
- Alembic migration adding auth tables (appended to WP-2.2 migration or separate)
- Seed data for 5 roles, 5 users, 5 user_roles rows
- Integration with WP-2.3 seed generator (auth seeded together with business data)

**Excluded scope:**
- Login endpoint (WP-2.6)
- Password hashing logic (WP-2.6)
- Middleware (WP-2.6)

**Dependencies:**
- WP-2.2 (schema foundation)
- WP-2.3 (seed infrastructure)

**Expected files:**
- `backend/app/models/auth.py` (or `user.py`, `role.py`)
- `backend/alembic/versions/<timestamp>_auth_tables.py`
- `seed/fixtures/auth.yaml` (roles, users, user_roles)
- `seed/generator/auth.py` (auth seeding logic)

**Tests/checks:**
- Migration creates auth tables
- Seed inserts 5 roles, 5 users, 5 user_roles
- Each user has exactly one role per DEC-028 mapping
- `user_roles` supports multi-role cardinality (schema allows N:N)

**Acceptance evidence:**
- `SELECT * FROM users` returns 5 demo accounts
- `SELECT * FROM user_roles` returns 5 rows with correct role assignments
- Role codes match DEC-028 exactly

**Completion criteria:**
- Auth tables seeded with DEC-028 mapping
- Schema supports future multi-role expansion

**Proposed atomic commit:**
```text
feat(auth): add users/roles tables and seed DEC-028 demo accounts
```

---

## WP-2.6 — Authentication and RBAC services

**Objective:** Implement login endpoint, password verification, JWT/session token contract, and role-checking middleware for backend authorization.

**Included scope:**
- `POST /api/v1/auth/login` accepting username + password
- Password hashing (bcrypt or argon2) in `users.hashed_password`
- JWT token generation (or session cookie — choose one; decision pending)
- `GET /api/v1/auth/me` returning current user + roles
- FastAPI dependency `get_current_user()` extracting user from token
- RBAC decorator or dependency `require_role(...)` checking user role
- Integration with existing dependency health endpoints (optional: restrict `/api/v1/system/*` to AI Administrator)

**Excluded scope:**
- Document-level permissions (deferred to Phase 4)
- Public demo access restrictions (Phase 7)
- OAuth/OIDC (out of scope)

**Dependencies:**
- WP-2.5 (auth tables must exist)

**Expected files:**
- `backend/app/services/auth.py` (login, password verification, token generation)
- `backend/app/api/auth.py` (login endpoint, /me endpoint)
- `backend/app/dependencies.py` (get_current_user, require_role)
- `backend/app/core/security.py` (password hashing, JWT utilities)
- `backend/tests/unit/test_auth_service.py`
- `backend/tests/integration/test_api_auth.py`

**Tests/checks:**
- Valid credentials return token
- Invalid credentials return 401
- Token decodes to correct user + roles
- `require_role("PRODUCTION_MANAGER")` allows manager.demo, denies auditor.demo
- Password stored as hash (never plaintext)
- Token expiration enforced

**Acceptance evidence:**
- AT-002 backend evidence only (login works, roles enforced via middleware dependency tests) — full role-specific UI evidence deferred to Phase 3
- Login flow verified via integration tests
- RBAC enforcement verified via dependency tests

**Completion criteria:**
- Login endpoint functional
- RBAC middleware enforces role checks
- Token contract stable

**Proposed atomic commit:**
```text
feat(auth): implement login, token contract and RBAC middleware
```

---

## WP-2.7A — Core production read APIs

**Objective:** Provide read-only REST endpoints for core production entities (plans, orders, components, BOM), enabling UI consumption (Phase 3) and integration testing.

**Included scope:**
- `GET /api/v1/products` (list)
- `GET /api/v1/products/{code}` (detail with versions)
- `GET /api/v1/product-versions/{code}` (detail with BOM)
- `GET /api/v1/components` (list)
- `GET /api/v1/components/{code}` (detail with alternatives)
- `GET /api/v1/production-plans` (list)
- `GET /api/v1/production-plans/{code}` (detail with orders)
- `GET /api/v1/production-orders` (list, filterable by plan)
- `GET /api/v1/production-orders/{code}` (detail, includes BOM explosion)
- `GET /api/v1/production-order-requirements` (list by order)
- All endpoints return JSON matching conceptual schema (no write operations)

**Excluded scope:**
- Write endpoints (Phase 6 approval flow)
- Supply and inventory endpoints (WP-2.7B)
- Risk endpoint (WP-2.9 will add `/api/v1/risks`)
- Auth restrictions per role (Phase 4 document-level; Phase 2 only protects system endpoints)

**Dependencies:**
- WP-2.2 (schema)
- WP-2.3 (seed data must exist for integration tests)

**Expected files:**
- `backend/app/api/products.py`
- `backend/app/api/components.py`
- `backend/app/api/production_plans.py`
- `backend/app/api/production_orders.py`
- `backend/app/schemas/product.py`, `component.py`, `production.py`
- `backend/tests/integration/test_api_products.py`
- `backend/tests/integration/test_api_components.py`
- `backend/tests/integration/test_api_production_plans.py`
- `backend/tests/integration/test_api_production_orders.py`

**Tests/checks:**
- All endpoints return 200 with correct JSON shape
- Filtering by query params works
- Natural identifiers (codes) used in URLs
- Response schemas match conceptual spec
- API documentation (OpenAPI) auto-generated

**Acceptance evidence:**
- `pytest tests/integration/test_api_*.py` passes
- Swagger UI (`/docs`) displays all endpoints
- Manual curl tests return expected data

**Completion criteria:**
- Core production entities readable via API
- API contract stable for Phase 3 UI consumption and WP-2.7B

**Proposed atomic commit:**
```text
feat(api): implement core production read APIs (plans, orders, components, BOM)
```

---

## WP-2.7B — Supply and inventory read APIs

**Objective:** Provide read-only REST endpoints for supply and inventory entities (warehouses, balances, reservations, suppliers, purchase orders), completing the Phase 2 API surface.

**Included scope:**
- `GET /api/v1/warehouses` (list)
- `GET /api/v1/warehouses/{code}` (detail with balances)
- `GET /api/v1/inventory` (list, filterable by component/warehouse)
- `GET /api/v1/inventory/{component_code}` (detail with balances + reservations)
- `GET /api/v1/inventory-reservations` (list, filterable by component/warehouse/order)
- `GET /api/v1/suppliers` (list)
- `GET /api/v1/suppliers/{code}` (detail with POs)
- `GET /api/v1/purchase-orders` (list)
- `GET /api/v1/purchase-orders/{po_number}` (detail with lines)
- All endpoints return JSON matching conceptual schema (no write operations)

**Excluded scope:**
- Write endpoints (Phase 6 approval flow)
- Core production endpoints (WP-2.7A)
- Risk endpoint (WP-2.9 will add `/api/v1/risks`)
- Auth restrictions per role (Phase 4 document-level; Phase 2 only protects system endpoints)

**Dependencies:**
- WP-2.2 (schema)
- WP-2.3 (seed data must exist for integration tests)
- WP-2.7A (infrastructure and patterns established)

**Expected files:**
- `backend/app/api/warehouses.py`
- `backend/app/api/inventory.py`
- `backend/app/api/inventory_reservations.py`
- `backend/app/api/suppliers.py`
- `backend/app/api/purchase_orders.py`
- `backend/app/schemas/inventory.py`, `supplier.py`, `purchase_order.py`
- `backend/tests/integration/test_api_warehouses.py`
- `backend/tests/integration/test_api_inventory.py`
- `backend/tests/integration/test_api_inventory_reservations.py`
- `backend/tests/integration/test_api_suppliers.py`
- `backend/tests/integration/test_api_purchase_orders.py`

**Tests/checks:**
- All endpoints return 200 with correct JSON shape
- Filtering by query params works
- Natural identifiers (codes) used in URLs
- Response schemas match conceptual spec
- API documentation (OpenAPI) auto-generated

**Acceptance evidence:**
- `pytest tests/integration/test_api_*.py` passes
- Swagger UI (`/docs`) displays all endpoints
- Manual curl tests return expected data

**Completion criteria:**
- All Phase 2 supply and inventory entities readable via API
- API contract stable for Phase 3 UI consumption and WP-2.9 risk endpoint

**Proposed atomic commit:**
```text
feat(api): implement supply and inventory read APIs (warehouses, inventory, suppliers, POs)
```

---

## WP-2.8 — Deterministic supply-risk engine

**Objective:** Implement pure Python/SQL risk calculation (BOM explosion, inventory availability, reservations, incoming supply, need-date calculations, severity rules) matching the derivation rules in `phase_2_business_model_spec.md` §7–8.

**Included scope:**
- `backend/app/services/risk_engine.py`
- BOM explosion logic (1 product_version → N components × quantity)
- Inventory availability calculation (on_hand − reservations for OTHER work orders)
- Incoming supply calculation (confirmed PO lines arriving before need_date)
- Need-date comparison (expected_delivery_date vs production_order.need_date)
- Severity rule engine (CRITICAL, HIGH, MEDIUM) per §8. LOW is documented in spec but not exercised by the Golden Dataset; no Phase 2 acceptance test depends on LOW
- Output: list of risk objects with component, required, available, shortage, severity, affected_wo

**Excluded scope:**
- API endpoint (WP-2.9 will expose)
- LLM integration (zero LLM in Phase 2)
- UI rendering (Phase 3)

**Dependencies:**
- WP-2.2 (schema must exist)
- WP-2.3 (seed data for integration tests)

**Expected files:**
- `backend/app/services/risk_engine.py` (core calculation)
- `backend/app/services/bom_explosion.py` (BOM traversal)
- `backend/app/services/inventory_service.py` (availability calculation)
- `backend/tests/unit/test_risk_engine.py`
- `backend/tests/integration/test_risk_engine_with_seed.py`

**Tests/checks:**
- Unit tests for each exercised severity level (CRITICAL, HIGH, MEDIUM — one per Golden Dataset risk)
- Integration test with seeded Golden Dataset returns exactly 3 risks
- Risk derivation matches spec §7 tables (RISK-001/002/003 inputs + outputs)
- No floating-point drift in quantity comparisons
- Performance acceptable for typical plan size (<1s for 100 work orders)

**Acceptance evidence:**
- Unit tests prove severity logic
- Integration test proves Golden Scenario derivation
- No LLM calls in risk engine code

**Completion criteria:**
- Risk engine deterministic and testable
- Output matches specification exactly

**Proposed atomic commit:**
```text
feat(risk): implement deterministic supply-risk engine (BOM, inventory, severity)
```

---

## WP-2.9 — Golden Scenario acceptance

**Objective:** Expose risk engine via API endpoint and provide automated AT-004 evidence proving exactly RISK-001, RISK-002, RISK-003 with correct quantities and severity.

**Included scope:**
- `GET /api/v1/production-plans/{plan_code}/risks` (returns list of risks for a plan)
- `GET /api/v1/risks/{risk_id}` (returns single risk with full derivation)
- Automated AT-004 test querying `/api/v1/production-plans/PLAN-2026-W31/risks`
- Test asserts exactly 3 risks returned with:
  - RISK-001: CTRL-X4, shortage=8, severity=CRITICAL, affected_wo=WO-2026-0142
  - RISK-002: MOTOR-M2, shortage=6, severity=HIGH, affected_wo=WO-2026-0150
  - RISK-003: SENSOR-L9, shortage=5, severity=MEDIUM, affected_wo=WO-2026-0156

**Excluded scope:**
- Risk remediation actions (Phase 6 approval flow)
- LLM explanation (Phase 5)
- UI rendering (Phase 3)

**Dependencies:**
- WP-2.7A (core production API infrastructure)
- WP-2.7B (supply and inventory API patterns)
- WP-2.8 (risk engine)

**Expected files:**
- `backend/app/api/risks.py` (risk endpoints)
- `backend/app/schemas/risk.py` (Pydantic response schema)
- `backend/tests/acceptance/test_at004_golden_scenario.py` (AT-004 evidence)

**Tests/checks:**
- AT-004 acceptance test passes (automated)
- Risk endpoint returns correct JSON structure
- Risk derivation trace visible in response (component, required, available, shortage, severity, affected_wo)
- Integration with seed data produces expected output

**Acceptance evidence:**
- `pytest tests/acceptance/test_at004_golden_scenario.py` passes
- API response matches Golden Dataset specification exactly
- No hardcoded values in endpoint code

**Completion criteria:**
- AT-004 automated evidence exists
- Risk API functional and tested

**Proposed atomic commit:**
```text
feat(risk): expose risk API and implement AT-004 Golden Scenario acceptance test
```

---

## WP-2.10 — Phase 2 integration and closeout

**Objective:** Provide backend/integration preparation for AT-005, verify zero-LLM dependency across Phase 2, run smoke tests, and produce completion report.

**Included scope:**
- AT-005 backend contract test: automated integration test proving that changing an input fixture quantity changes the freshly calculated API result without changing application code (Phase 2 preparation/evidence for the backend part of AT-005).
- Zero-LLM verification: grep backend code for LLM imports/calls; assert none in Phase 2 modules
- Smoke test: `make test` passes (all Phase 2 tests green)
- `mypy --strict` passes
- `ruff check` passes
- Documentation: `docs/phase_2/phase_2_completion_report.md` summarizing deliverables, tests, evidence

**Excluded scope:**
- Full AT-005 browser evidence (Phase 3 UI required)
- Public deployment (Phase 7)
- Phase 3 UI work

**Dependencies:**
- All prior WPs (WP-2.1 through WP-2.9)

**Expected files:**
- `backend/tests/acceptance/test_at005_backend_contract.py` (proves DB → API chain)
- `backend/tests/acceptance/test_zero_llm_dependency.py` (proves no LLM imports)
- `docs/phase_2/phase_2_completion_report.md`
- Makefile updates (Phase 2 verification targets if needed)

**Tests/checks:**
- All Phase 2 tests pass (`make test`)
- Type checks pass (`mypy --strict`)
- Linting passes (`ruff check`)
- Zero-LLM dependency verified
- AT-005 backend contract test passes (demonstrates DB → API chain; no hardcoded cache)
- Completion report documents all deliverables

**Acceptance evidence:**
- `make test` output shows all tests green
- Completion report lists all WPs completed
- Zero-LLM grep assertion passes
- AT-005 backend contract test passes (this is Phase 2 backend preparation only)

**Completion criteria:**
- Phase 2 exit criteria met (AT-003, AT-004, AT-005 backend preparation — *not* full AT-005)
- Full AT-005 browser evidence remains deferred to Phase 3 (Core UI required)
- Completion report written
- Ready for Phase 3 UI work

**Proposed atomic commit:**
```text
docs(phase-2): record completion and verify zero-LLM dependency
```

---

## Work-Package Dependency Graph

```
WP-2.1 (spec) ────────────────────────────────────────────────────────────────┐
  │                                                                           │
  ▼                                                                           │
WP-2.2 (schema) ──────────────────────────────────────────────────────────────┤
  │                                                                           │
  ├─► WP-2.3 (seed) ──► WP-2.4 (integrity)                                   │
  │                       │                                                   │
  ├─► WP-2.5 (auth data) ─┘                                                   │
  │       │                                                                   │
  │       ▼                                                                   │
  │     WP-2.6 (auth services)                                                │
  │                                                                           │
  ├─► WP-2.7A ──► WP-2.7B ─┤
  │                          │
  ├─► WP-2.8 (risk engine) ──► WP-2.9 (Golden Scenario) ──► WP-2.10 (closeout)
```

## WP Execution Order

1. WP-2.1 (already complete)
2. WP-2.2 (schema)
3. WP-2.3 (seed) — can be done in parallel with WP-2.5 if needed
4. WP-2.4 (integrity)
5. WP-2.5 (auth data)
6. WP-2.6 (auth services)
7. WP-2.7A (core production APIs: products, components, plans, orders)
8. WP-2.7B (supply and inventory APIs: warehouses, inventory, suppliers, POs)
9. WP-2.8 (risk engine)
10. WP-2.9 (Golden Scenario)
11. WP-2.10 (closeout)

Note: WP-2.3 and WP-2.5 both depend on WP-2.2 (schema) and can be implemented sequentially or in parallel. WP-2.5 should be done before WP-2.6 (auth data before auth services).

## Verification Gates

- After WP-2.2: migration reversible
- After WP-2.3: seed command works, reset works
- After WP-2.4: AT-003 passes
- After WP-2.5: auth tables seeded correctly
- After WP-2.6: login works, RBAC enforced
- After WP-2.7A: core production endpoints return 200
- After WP-2.7B: all supply and inventory endpoints return 200
- After WP-2.8: risk engine tests pass (unit + integration)
- After WP-2.9: AT-004 passes (Golden Scenario exact)
- After WP-2.10: all tests green, zero-LLM verified, completion report written

## Phase 2 Exit Criteria

Phase 2 is complete when:
- WP-2.1 through WP-2.10 are done (note: WP-2.7A and WP-2.7B are both included)
- AT-003 passes (dataset integrity)
- AT-004 passes (Golden Scenario RISK-001/002/003 exact)
- AT-005 backend preparation complete (API returns fresh results, test proves DB → API chain)
- Zero LLM dependencies in Phase 2 code
- Completion report written

---

**Next step:** Product Owner approval of this work-package plan before commencing WP-2.2 implementation.
