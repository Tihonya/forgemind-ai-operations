# WP-3.5 Specification — Supply Risk List

**Status:** APPROVED FOR IMPLEMENTATION
**Work Package:** WP-3.5
**Phase:** 3 (Core UI)
**Base:** main at f37e306db8cb9ee749984ff3575a6c6a272c70aa
**Branch:** feature/phase-3-wp-3-5-risk-list
**Depends on:** WP-3.3, WP-3.4 (both merged)

---

## 1. Objective

Deliver the Supply Risk Analysis list page: display production risks from the backend deterministic engine with client-side filtering, severity badges, and fixed severity-descending ordering. Reuse the WP-3.4 active-plan selection logic. No risk detail, no row navigation, no sorting headers.

---

## 2. Backend Contract (Verified)

**Endpoint:** `GET /api/v1/production-plans/{plan_code}/risks`

**Response:** `list[RiskRecordWithId]`

**Fields:**
- `risk_id` (str): Ephemeral ID (RISK-001, RISK-002, ...) assigned by position
- `component_code` (str): Natural identifier (e.g., CTRL-X4)
- `component_name` (str): Human-readable name
- `affected_wo_code` (str): Work order code
- `required` (DecimalStr4): Total quantity required (JSON string, 4 decimals)
- `available` (DecimalStr4): Available inventory (JSON string, 4 decimals)
- `confirmed_early` (DecimalStr4): Confirmed supply arriving before need_date
- `confirmed_late` (DecimalStr4): Confirmed supply arriving after need_date
- `shortage` (DecimalStr4): Shortage quantity (JSON string, 4 decimals)
- `severity` (str): CRITICAL, HIGH, MEDIUM, or LOW
- `has_approved_alternative` (bool): Whether an APPROVED alternative exists
- `has_proposed_alternative` (bool): Whether a PROPOSED alternative exists
- `need_date` (date): Date when component is needed
- `plan_code` (str): Production plan code

**Error behavior:**
- Unknown plan → HTTP 404
- Missing/invalid auth → HTTP 401

---

## 3. In-Scope Deliverables

### 3.1 Supply Risk Page

- Reuse existing route `/supply-risk` from WP-3.3 (placeholder)
- Active production plan banner (reuse `useActivePlan` hook from WP-3.4)
- Risk list populated from backend response
- Severity badges (CRITICAL/HIGH/MEDIUM/LOW)
- Client-side severity multi-filter
- Client-side component-code text filter
- Fixed severity-descending ordering (CRITICAL → HIGH → MEDIUM → LOW)
- Stable secondary ordering by `risk_id` ascending
- Total and currently-visible risk counts
- Loading skeletons
- No-active-plan state
- Zero-risks state
- Filtered-empty state
- Risk request error with retry button
- Independent plan and risk failure handling

### 3.2 Active Plan Banner

- Reuse `useActivePlan` hook from WP-3.4
- One active plan: show banner with plan code, status, period
- Zero active plans: honest empty state
- Multiple active plans: deterministic selection + non-blocking warning
- No plan selector dropdown
- Do not call production-plan detail endpoint if list response already contains required fields

### 3.3 Risk List Columns

Only display fields that exist in the verified backend contract:

1. **Severity** — badge with semantic color
2. **Risk ID** — ephemeral ID from backend
3. **Component Code** — natural identifier
4. **Component Name** — human-readable name
5. **Shortage** — quantity (4 decimal places)
6. **Available** — quantity (4 decimal places)
7. **Required** — quantity (4 decimal places)

**Excluded:** `affected_wo_code`, `confirmed_early`, `confirmed_late`, `need_date`, `has_approved_alternative`, `has_proposed_alternative` (detail-level fields, belong to WP-3.6+).

**"Risk type" column:** Not present in backend contract. Do not invent.

### 3.4 Filtering Behavior

**Client-side only** (per Phase 3 §5.1):

- Severity filter: multi-select (CRITICAL / HIGH / MEDIUM / LOW)
  - Default: all selected
  - When none selected: show all risks (no filtering)
- Component-code filter: text search (substring match, case-insensitive)
  - Default: empty (no filtering)
- Combined filters: AND logic
- Filter reset: button to clear all filters

### 3.5 Sorting Behavior

**Fixed only** (no clickable headers):

1. Primary: severity descending (CRITICAL → HIGH → MEDIUM → LOW)
2. Secondary: `risk_id` ascending (stable, deterministic)

Unknown severity values: treat as lowest priority (after LOW).

### 3.6 Row Behavior

- **No row navigation**
- **No click handler**
- **No keyboard navigation semantics**
- **No `/supply-risk/:riskId` route**
- **No WP-3.6 placeholder**
- Risk detail begins only in WP-3.6

### 3.7 UX States

- **Loading:** skeleton table rows (shadcn/ui Skeleton)
- **No active plan:** "No active production plan" message
- **Zero risks:** "No risks calculated for this plan"
- **Filtered empty:** "No risks match the selected filters"
- **Risk request error:** Alert with retry button
- **401:** redirect to `/login` (existing ProtectedRoute behavior)
- **403:** "Access denied" screen
- **404:** "Production plan not found" message
- **5xx / network error:** Alert with retry

### 3.8 Authentication and Authorization

- Page is protected by existing ProtectedRoute (WP-3.2)
- Backend authorization remains authoritative (Phase 3 §5.4)
- Frontend visibility is UX-only
- No global auth interceptor added in this WP
- 401/403 handling: verify actual current behavior, document it

---

## 4. Explicit Out-of-Scope

- Risk detail (WP-3.6)
- Row navigation (WP-3.6+)
- Sortable headers
- Pagination
- Plan selector dropdown
- Evidence calculation (WP-3.6)
- Recommendations (Phase 5)
- Approvals (Phase 6)
- What-if simulation (Post-MVP)
- AI-generated content (Phase 5)
- Backend changes
- Hardcoded Golden Scenario identifiers or values in production source
- WP-3.6 or later work

---

## 5. Files Allowed to Change

```
docs/planning/wp_3_5_supply_risk_list_spec.md          (new)
frontend/src/
├── routes/
│   └── supply-risk.tsx                                (replaced — empty placeholder → full page)
├── components/
│   ├── supply-risk/
│   │   ├── RiskList.tsx                               (new)
│   │   ├── RiskList.test.tsx                          (new)
│   │   ├── RiskFilters.tsx                            (new)
│   │   ├── RiskFilters.test.tsx                       (new)
│   │   ├── SeverityBadge.tsx                          (new)
│   │   └── SeverityBadge.test.tsx                     (new)
│   └── ui/
│       └── table.tsx                                  (new — shadcn/ui)
├── hooks/
│   └── useRisks.ts                                    (new)
└── lib/
    └── risks-api.ts                                   (new)
    └── risks-api.test.ts                              (new)
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
- `frontend/src/hooks/useActivePlan.ts` (WP-3.4 boundary)
- `frontend/src/components/dashboard/ActivePlanWidget.tsx` (WP-3.4 boundary)
- Any route file other than `supply-risk.tsx`

---

## 7. Test Requirements

### 7.1 Sorting Tests

- [ ] Exact severity ordering: CRITICAL → HIGH → MEDIUM → LOW
- [ ] Stable secondary ordering by risk_id ascending within same severity
- [ ] Unknown severity treated as lowest priority

### 7.2 Filtering Tests

- [ ] Single severity filter (e.g., only CRITICAL)
- [ ] Multi severity filter (e.g., CRITICAL + HIGH)
- [ ] Component-code text filter (substring, case-insensitive)
- [ ] Combined filters (severity + component-code)
- [ ] Filter reset clears all filters
- [ ] No severity selected → show all risks
- [ ] Filtered-empty state when no risks match

### 7.3 Active Plan Tests

- [ ] Reuse `useActivePlan` hook from WP-3.4
- [ ] One active plan: banner shown
- [ ] Zero active plans: empty state
- [ ] Multiple active plans: warning shown

### 7.4 UX State Tests

- [ ] Loading skeletons during fetch
- [ ] Zero risks: empty state message
- [ ] Filtered empty: distinct message
- [ ] Risk request error: Alert with retry
- [ ] 401/403/404/5xx/network behavior

### 7.5 Regression Tests

- [ ] WP-3.4 dashboard still works
- [ ] WP-3.3 navigation still works
- [ ] No hardcoded PLAN-2026-W31 or RISK-001/002/003 in production source

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
3. Install shadcn/ui Table component
4. Implement `lib/risks-api.ts` (fetch risks for a plan)
5. Implement `hooks/useRisks.ts` (TanStack Query wrapper)
6. Implement `components/supply-risk/SeverityBadge.tsx`
7. Implement `components/supply-risk/RiskFilters.tsx`
8. Implement `components/supply-risk/RiskList.tsx` (with sorting + filtering)
9. Replace `routes/supply-risk.tsx` with full page
10. Write unit tests for API client
11. Write unit tests for sorting logic
12. Write unit tests for filtering logic
13. Write component tests for RiskList
14. Write component tests for RiskFilters
15. Write component tests for SeverityBadge
16. Run all test gates
17. Perform pre-push focused review
18. Stage files explicitly, create single WP-3.5 commit
19. Stop before push

---

## 10. Acceptance Criteria

- [ ] After login, navigating to `/supply-risk` renders the risk list page
- [ ] Active production plan banner displays (reuses WP-3.4 hook)
- [ ] Risk list populated from backend response (no hardcoded values)
- [ ] Severity badges map correctly (CRITICAL/HIGH/MEDIUM/LOW)
- [ ] Fixed severity-descending ordering (CRITICAL first)
- [ ] Stable secondary ordering by risk_id within same severity
- [ ] Client-side severity multi-filter works
- [ ] Client-side component-code text filter works
- [ ] Combined filters work (AND logic)
- [ ] Filter reset clears all filters
- [ ] Total and visible risk counts displayed
- [ ] Loading skeletons shown during fetch
- [ ] No-active-plan state shown when no EXECUTING plan
- [ ] Zero-risks state shown when backend returns empty list
- [ ] Filtered-empty state shown when filters eliminate all risks
- [ ] Risk request error shows Alert with retry button
- [ ] Independent plan and risk failure handling
- [ ] 401/403/404/5xx/network states handled correctly
- [ ] Rows have no navigation semantics (no click, no Link, no keyboard nav)
- [ ] No `/supply-risk/:riskId` route created
- [ ] No hardcoded Golden Scenario values in UI source (AT-005 / §5.6)
- [ ] All test gates pass
- [ ] No unauthorized artifacts in working tree
- [ ] Single intentional WP-3.5 commit
- [ ] No WP-3.6 work

---

## 11. Architecture Decision Records Respected

- DEC-015: State management — TanStack Query + Context only
- DEC-017: shadcn/ui over existing Tailwind theme
- DEC-028: Five canonical demo roles
- Phase 3 §5.1: Risk filtering is client-side
- Phase 3 §5.2: Risk detail is composed (not this WP)
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

WP-3.5 advances the 60–90 second portfolio demonstration:

**Before (WP-3.4):** Dashboard shows risk counts by severity.
**After (WP-3.5):** User navigates to Supply Risk Analysis, sees the actual risks with severity badges, filters to focus on CRITICAL first, understands the scope of the problem.

The next beat (WP-3.6) will open a single risk and show the evidence calculation.

---

**END OF WP-3.5 SPECIFICATION**
