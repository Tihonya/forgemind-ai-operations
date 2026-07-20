# WP-3.6 Specification — Supply Risk Detail & Evidence

**Status:** APPROVED FOR IMPLEMENTATION
**Work Package:** WP-3.6
**Phase:** 3 (Core UI)
**Base:** main at cbcac23be77bf525acac021213cd0ce382d92708
**Branch:** feature/phase-3-wp-3-6-risk-detail
**Depends on:** WP-3.3, WP-3.5 (both merged)

---

## 1. Objective

Deliver the Supply Risk Detail & Evidence screen: open one risk, show WHY it exists by displaying the deterministic calculation breakdown, affected component, supplier context, and plan context. Compose detail from existing backend endpoints (Phase 3 §5.2). No new backend endpoints. No recalculation of shortage or severity in frontend.

---

## 2. Backend Contract Verification (Verified from Source)

### 2.1 Risk Response Fields

**Endpoint:** `GET /api/v1/production-plans/{plan_code}/risks`
**Response:** `list[RiskRecordWithId]`
**Source:** `backend/app/schemas/risk_response.py`

Fields (all DecimalStr4 = JSON string, 4 decimal places):
- `risk_id` (str): Ephemeral ID (RISK-001, RISK-002, ...)
- `component_code` (str)
- `component_name` (str)
- `affected_wo_code` (str)
- `required` (DecimalStr4)
- `available` (DecimalStr4)
- `confirmed_early` (DecimalStr4)
- `confirmed_late` (DecimalStr4)
- `shortage` (DecimalStr4)
- `severity` (str): CRITICAL, HIGH, MEDIUM, LOW
- `has_approved_alternative` (bool)
- `has_proposed_alternative` (bool)
- `need_date` (date)
- `plan_code` (str)

### 2.2 Shortage Calculation (Canonical)

**Source:** `backend/app/services/risk_engine.py` lines 56-59

```python
shortage = max(
    Decimal("0"),
    row.required - availability.available - availability.confirmed_early,
)
```

**Formula:** `shortage = max(0, required - available - confirmed_early)`

**Key findings:**
- `confirmed_late` does NOT participate in shortage calculation
- `confirmed_late` is evidence context only (shown but not in formula)
- Frontend must NOT recalculate; display backend values as-is

### 2.3 Severity Derivation (Canonical)

**Source:** `backend/app/services/risk_engine.py` lines 98-140

Precedence (first match wins):
1. `shortage <= 0` → None (no risk emitted)
2. `shortage > 0 AND has_proposed_alternative` → MEDIUM
3. `shortage > 0 AND confirmed_late > 0` → HIGH
4. `shortage > 0 AND NOT has_approved_alternative` → CRITICAL
5. `shortage > 0 AND has_approved_alternative` → LOW

**Key findings:**
- Severity depends on shortage, alternatives, and confirmed_late
- No human-readable formula exists in backend
- Frontend must NOT invent severity rule text
- Show severity badge only; do not explain derivation

### 2.4 Component Endpoint

**Endpoint:** `GET /api/v1/components/{code}`
**Response:** `ComponentDetail`
**Source:** `backend/app/schemas/component.py`

Fields:
- `code` (str)
- `name` (str)
- `unit` (str)
- `description` (str | None)
- `alternatives` (list[ComponentAlternativeSummary])
  - `alternative_code` (str)
  - `status` (str)
  - `rationale` (str | None)

**Error:** 404 if component not found

### 2.5 Inventory Endpoint

**Endpoint:** `GET /api/v1/inventory/{component_code}`
**Response:** `InventoryDetail`
**Source:** `backend/app/schemas/inventory.py`

Fields:
- `component_code` (str)
- `component_name` (str)
- `unit` (str)
- `description` (str | None)
- `balances` (list[InventoryBalanceInDetail])
  - `warehouse_code` (str)
  - `quantity_on_hand` (DecimalStr)
- `reservations` (list[ReservationInInventoryDetail])
  - `order_code` (str)
  - `warehouse_code` (str)
  - `quantity` (DecimalStr)

**Multiplicity:** Multiple balances (one per warehouse), multiple reservations (one per order+warehouse)

**Error:** 404 if component not found

### 2.6 Purchase Order Endpoint

**Endpoint:** `GET /api/v1/purchase-orders`
**Response:** `PurchaseOrderListResponse`
**Source:** `backend/app/schemas/purchase_order.py`, `backend/app/api/purchase_orders.py`

**Pagination:**
- `limit` (int, 1-200, default 50)
- `offset` (int, default 0)
- Response includes `total` count

**Filters:**
- `supplier_code` (str | None)
- `status` (str | None) — **no component_code filter**

**Completeness conclusion:**
- Endpoint is paginated (limit/offset)
- No component_code filter exists
- Golden Scenario dataset is small (< 50 POs)
- **Resolution:** Fetch with `limit=200`, filter client-side by component_code
- If `total > 200`, log warning and show partial data with note
- No backend changes permitted (§5.5)

**List response fields:**
- `po_number` (str)
- `supplier_code` (str)
- `status` (str)
- `placed_at` (datetime)
- `total_lines` (int)
- `total_ordered_quantity` (DecimalStr)

**Detail endpoint:** `GET /api/v1/purchase-orders/{po_number}`
**Response:** `PurchaseOrderDetail` with lines

**Line fields:**
- `component_code` (str)
- `component_name` (str)
- `ordered_quantity` (DecimalStr)
- `received_quantity` (DecimalStr)
- `expected_delivery_date` (date)
- `status` (str)

### 2.7 Production Order Endpoint

**Endpoint:** `GET /api/v1/production-orders/{code}`
**Response:** `ProductionOrderDetail`
**Source:** `backend/app/schemas/production.py`

Fields:
- `code` (str)
- `plan_code` (str)
- `product_code` (str)
- `product_version` (str)
- `quantity` (DecimalStr)
- `need_date` (date)
- `status` (str)
- `requirements` (list[ProductionOrderRequirementDetail])
  - `component_code` (str)
  - `component_name` (str)
  - `required_quantity` (DecimalStr)
  - `reserved_quantity` (DecimalStr)

**Error:** 404 if order not found

### 2.8 Production Plan Endpoint

**Endpoint:** `GET /api/v1/production-plans/{code}`
**Response:** `ProductionPlanDetail`
**Source:** `backend/app/schemas/production.py`

Fields:
- `code` (str)
- `status` (str)
- `period_start` (date)
- `period_end` (date)
- `production_orders` (list[ProductionOrderSummary])

**Error:** 404 if plan not found

### 2.9 Error Behavior (Canonical)

**Risk endpoint:**
- Unknown plan → HTTP 404 with detail: `"Production plan '<code>' not found"`
- Missing auth → HTTP 401 (canonical from WP-2.6)

**Component/Inventory/PO/ProductionOrder endpoints:**
- Not found → HTTP 404 with structured detail

**Authentication:**
- ProtectedRoute handles route-level auth
- API-level 401/403: handle per-request in error states
- No global Axios interceptor (do not add)
- Broader auth hardening deferred to WP-3.7

---

## 3. In-Scope Deliverables

### 3.1 Route and Deep-Link

- **Route:** `/supply-risk/:riskId` (e.g., `/supply-risk/RISK-001`)
- **Deep-link refresh:**
  1. Fetch risk list for active plan
  2. Match by `risk_id`
  3. If found → proceed with detail composition
  4. If not found → 404 state: "Risk not found or the production-plan data has changed"

### 3.2 Navigation from List

- **View column:** Add dedicated "View" action column to WP-3.5 risk list
- **Link:** `<Link to={/supply-risk/${risk.risk_id}}>` with accessible name "View {risk_id}"
- **Risk ID cell:** Remains plain text (not a link)
- **Whole-row click:** NOT added (forbidden)
- **Breadcrumb:** "Supply Risk Analysis > RISK-XXX" or "← Back to risks" link

### 3.3 Page Hierarchy

1. **Breadcrumb and back navigation**
2. **Risk summary** (severity badge, ID, component, need_date, WO)
3. **Evidence breakdown** (required, available, confirmed_early, confirmed_late, shortage)
4. **Affected component** (name, code, alternatives)
5. **Inventory context** (balances by warehouse, reservations)
6. **Incoming supply** (purchase orders for this component)
7. **Production-order and plan context** (affected WO detail, plan period)

### 3.4 Evidence Panel

**Display (backend-authoritative, no recalculation):**
- Required: `{required}`
- Available: `{available}`
- Confirmed early: `{confirmed_early}`
- Confirmed late: `{confirmed_late}`
- Shortage: `{shortage}`

**Formula narrative (ONLY if proven by backend source):**
- Show: "Shortage = max(0, required − available − confirmed_early)"
- Do NOT show severity rule text (not canonical in backend)
- Do NOT invent explanatory business rules

**Inventory breakdown:**
- Show warehouse-level balances from `/inventory/{component_code}`
- Show reservations from same endpoint

**Incoming supply breakdown:**
- Fetch `/purchase-orders?limit=200`
- Filter client-side by component_code (from PO lines)
- Show PO number, supplier, status, expected delivery, ordered quantity
- If `total > 200`, show note: "Showing first 200 purchase orders"

### 3.5 UX States

| State | Behavior |
|-------|----------|
| Loading | Skeleton for each panel |
| Risk not found (invalid risk_id) | 404 screen: "Risk not found or the production-plan data has changed" with link back to list |
| Plan not found (404 on risks endpoint) | "Production plan not found" with link to dashboard |
| Component not found (404 on /components/{code}) | Partial failure: "Component data unavailable" placeholder, show other panels |
| Inventory 404/5xx | Partial failure: "Inventory data unavailable" placeholder with retry |
| Purchase-orders failure | Partial failure: "Incoming supply data unavailable" placeholder with retry |
| Production-order 404/5xx | Partial failure: "Work order data unavailable" placeholder with retry |
| 401 | Redirect to /login (existing ProtectedRoute) |
| 403 | Access denied screen |
| 5xx / network error on primary risk | Alert with retry button |
| No active plan | Message: "No active production plan" |

**Partial-failure policy:**
- Risk record and evidence are primary content
- Component, inventory, PO, production-order panels may fail independently
- Show explicit unavailable placeholders and panel-level retry
- Do NOT hide whole detail page because enrichment endpoint failed

### 3.6 Role Behavior

**Inherit Supply Risk Analysis role matrix:**
- Visible to: `production_manager`, `procurement_specialist`, `platform_admin`
- Not exposed to: `ai_administrator`, `auditor`

**Frontend enforcement:**
- Navigation hiding is UX only (§5.4)
- Backend authorization remains authoritative
- If 403 returned → clean access-denied screen

---

## 4. Explicit Out-of-Scope

- Recommendations, approvals, mitigation execution (Phase 5/6)
- What-if simulation (Post-MVP)
- AI-generated explanation text (Phase 5)
- New backend endpoints (§5.5 — zero backend changes)
- Hardcoded Golden Scenario identifiers or values (§5.6)
- Whole-row navigation (forbidden)
- Invented formulas or severity rules
- WP-3.7+ loading/error state polish
- E2E Golden Scenario test (WP-3.9)
- Mobile responsive mode (Post-MVP)
- Global auth interceptor (deferred to WP-3.7)

---

## 5. Files Allowed to Change

```
docs/planning/wp_3_6_supply_risk_detail_spec.md          (new)
frontend/src/
├── App.tsx                                               (updated — add route)
├── routes/
│   ├── supply-risk-detail.tsx                            (new)
│   └── supply-risk.tsx                                   (updated — add View column)
├── components/
│   ├── supply-risk/
│   │   ├── RiskList.tsx                                  (updated — add View column)
│   │   ├── RiskDetail.tsx                                (new)
│   │   ├── RiskSummary.tsx                               (new)
│   │   ├── EvidencePanel.tsx                             (new)
│   │   ├── ComponentPanel.tsx                            (new)
│   │   ├── InventoryPanel.tsx                            (new)
│   │   ├── IncomingSupplyPanel.tsx                       (new)
│   │   ├── ProductionOrderPanel.tsx                      (new)
│   │   ├── PartialFailurePlaceholder.tsx                 (new)
│   │   ├── RiskDetail.test.tsx                           (new)
│   │   ├── EvidencePanel.test.tsx                        (new)
│   │   └── ComponentPanel.test.tsx                       (new)
│   └── ui/
│       └── breadcrumb.tsx                                (new — shadcn/ui)
├── hooks/
│   ├── useRiskDetail.ts                                  (new)
│   └── useRiskDetail.test.ts                             (new)
└── lib/
    ├── risk-detail-api.ts                                (new)
    └── risk-detail-api.test.ts                           (new)
```

---

## 6. Files That MUST NOT Change

- Every file under `backend/`
- Every file under `seed/`
- Every file under `forgemind_project_source_of_truth/`
- Every file under `infra/`
- `docker-compose.yml`, `docker-compose.dev.yml`
- `Makefile`
- `.github/`
- `docs/planning/phase_3_planning_handoff.md`
- `HERMES.md`
- `frontend/src/hooks/useRisks.ts` (WP-3.5 boundary)
- `frontend/src/hooks/useActivePlan.ts` (WP-3.4 boundary)
- `frontend/src/lib/risks-api.ts` (WP-3.5 boundary)
- Any route file other than `supply-risk.tsx` and `supply-risk-detail.tsx`

---

## 7. Test Requirements

### 7.1 Route and Navigation Tests

- [ ] Route `/supply-risk/:riskId` renders detail page
- [ ] Deep-link refresh works (re-fetches list, matches risk_id)
- [ ] Invalid risk_id → 404 screen
- [ ] Navigation from list via View link (not whole-row click)
- [ ] Breadcrumb/back navigation works

### 7.2 Evidence Tests

- [ ] Evidence panel shows all 5 quantity fields
- [ ] Backend values displayed as-is (no recalculation)
- [ ] Formula narrative shown (if proven by backend)
- [ ] Shortage formula: "Shortage = max(0, required − available − confirmed_early)"

### 7.3 Composition Tests

- [ ] Component detail loaded from `/components/{code}`
- [ ] Inventory balances shown from `/inventory/{component_code}`
- [ ] Purchase orders fetched and filtered by component
- [ ] Production order shown from `/production-orders/{wo_code}`

### 7.4 Partial-Failure Tests

- [ ] Component 404 → placeholder, other panels shown
- [ ] Inventory 5xx → placeholder with retry, other panels shown
- [ ] Purchase-orders failure → placeholder with retry
- [ ] Production-order 404 → placeholder, other panels shown

### 7.5 Role Tests

- [ ] Visible to production_manager, procurement_specialist, platform_admin
- [ ] Not exposed to ai_administrator, auditor (UX enforcement)
- [ ] Backend 403 → access-denied screen

### 7.6 Regression Tests

- [ ] WP-3.5 risk list still works
- [ ] View column added to risk list
- [ ] No whole-row click added
- [ ] No backend changes
- [ ] No hardcoded Golden Scenario values in source

---

## 8. Test Gates

All must pass before PR submission:

- [ ] `npm run lint` — zero warnings
- [ ] `npm run type-check` — zero errors
- [ ] `npm test` — Vitest green (new tests included)
- [ ] `npm run build` — zero errors
- [ ] `npm run test:e2e` — Playwright trivial spec still green
- [ ] `make lint` — backend lint still clean
- [ ] `make test` — backend ≥ 709 tests, zero regressions

---

## 9. Implementation Sequence

1. Create spec document (this file)
2. Create and checkout branch
3. Install shadcn/ui Breadcrumb component
4. Implement `lib/risk-detail-api.ts` (fetch component, inventory, POs, production-order)
5. Implement `hooks/useRiskDetail.ts` (orchestrate parallel fetches with partial-failure)
6. Implement `components/supply-risk/RiskSummary.tsx`
7. Implement `components/supply-risk/EvidencePanel.tsx`
8. Implement `components/supply-risk/ComponentPanel.tsx`
9. Implement `components/supply-risk/InventoryPanel.tsx`
10. Implement `components/supply-risk/IncomingSupplyPanel.tsx`
11. Implement `components/supply-risk/ProductionOrderPanel.tsx`
12. Implement `components/supply-risk/PartialFailurePlaceholder.tsx`
13. Implement `components/supply-risk/RiskDetail.tsx` (orchestrator)
14. Implement `routes/supply-risk-detail.tsx` (route component)
15. Update `App.tsx` to add route `/supply-risk/:riskId`
16. Update `components/supply-risk/RiskList.tsx` to add View column
17. Write unit tests for API client
18. Write unit tests for composition logic
19. Write component tests for detail panels
20. Write component tests for partial-failure
21. Run all test gates
22. Perform pre-push focused review
23. Remove unauthorized/generated artifacts
24. Stage files explicitly, create single WP-3.6 commit
25. Stop before push

---

## 10. Acceptance Criteria

- [ ] Route `/supply-risk/:riskId` renders detail page
- [ ] Risk identified by risk_id matched against risk-list response
- [ ] Evidence panel shows all 5 quantity fields from backend
- [ ] No recalculation of shortage or severity in frontend
- [ ] Component detail loaded from `/components/{code}`
- [ ] Inventory balances shown from `/inventory/{component_code}`
- [ ] Purchase orders fetched and filtered by component (client-side)
- [ ] Affected work order shown from `/production-orders/{wo_code}`
- [ ] Deep-link refresh works (re-fetches list, matches risk_id)
- [ ] Invalid risk_id → 404 screen with message
- [ ] Navigation from list via View link (not whole-row click)
- [ ] Breadcrumb/back navigation works
- [ ] Partial-failure handled (component 404 → placeholder, others shown)
- [ ] Panel-level retry for failed enrichment endpoints
- [ ] No hardcoded Golden Scenario values in UI source (§5.6)
- [ ] Role behavior inherited from WP-3.5 (UX enforcement)
- [ ] Backend 403 → access-denied screen
- [ ] All test gates pass
- [ ] No unauthorized artifacts in working tree
- [ ] Single intentional WP-3.6 commit
- [ ] No WP-3.7 work

---

## 11. Architecture Decision Records Respected

- DEC-015: State management — TanStack Query + Context only
- DEC-017: shadcn/ui over existing Tailwind theme
- DEC-028: Five canonical demo roles
- Phase 3 §5.1: Risk filtering is client-side
- Phase 3 §5.2: Risk detail is composed (this WP)
- Phase 3 §5.3: Placeholders do not make network requests
- Phase 3 §5.4: Navigation hiding is UX only
- Phase 3 §5.5: No new backend endpoints
- Phase 3 §5.6: Golden Scenario values never hardcoded

---

## 12. Verification Commands

```bash
npm run lint
npm run type-check
npm test
npm run build
npm run test:e2e
make lint
make test
```

---

## 13. Demo Narrative Contribution

WP-3.6 advances the 60–90 second portfolio demonstration:

**Before (WP-3.5):** Dashboard → Risk list → identify critical risks by severity

**After (WP-3.6):** Dashboard → Risk list → click View on critical risk → see exact calculation → understand WHY it's critical → see evidence (inventory, incoming supply, shortage formula)

This is the "wow moment" — transparent deterministic intelligence. The user sees: "The system calculated that CTRL-X4 has a shortage of 5 units because we need 20, have 5 in stock, and only 10 arriving on time." This is audit-ready explainability.

**Next beat (WP-3.7+):** Polish loading/error states, then E2E Golden Scenario.

---

**END OF WP-3.6 SPECIFICATION**
