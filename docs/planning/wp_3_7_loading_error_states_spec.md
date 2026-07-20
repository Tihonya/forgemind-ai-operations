# WP-3.7 Specification — Loading, Empty, Error States & Frontend Polish

**Status:** APPROVED FOR IMPLEMENTATION
**Work Package:** WP-3.7
**Phase:** 3 (Core UI)
**Base:** main at af14a68c3be958a65d75bcfecdd87ab142954547
**Branch:** feature/phase-3-wp-3-7-loading-error-states
**Depends on:** WP-3.4, WP-3.5, WP-3.6 (all merged)

---

## 1. Objective

Unify loading, empty, and error states across all Phase 3 screens. Introduce
two shared primitives (DataErrorState, DataEmptyState), add retry to dashboard
widgets where canonical refetch exists, fix accessibility issues (role
semantics, heading hierarchy, skip-link), clean up the detail page (remove
redundant back button, meaningful breadcrumb, flatten incoming-supply
conditional), and verify 1024px desktop layout.

No backend changes. No new endpoints. No new routes. No API architecture
changes. No auth interceptor. No hook orchestration changes.

---

## 2. Architectural Decisions (Authoritative)

1. **Authentication**: No global Axios interceptor. No AuthProvider or
   ProtectedRoute changes. No token-expiration redirect. Broader 401/403
   hardening is **deferred architecture work** (reported in findings).
2. **Detail navigation**: Keep breadcrumb. Remove redundant back button.
   Loading breadcrumb leaf is meaningful (not "Loading..."). Resolved leaf
   shows backend risk_id.
3. **Sidebar user summary**: Replace non-functional button with semantic
   non-interactive container (div).
4. **Shared primitives**: DataErrorState, DataEmptyState only. Reuse existing
   Skeleton. No RetryButton or LoadingState abstractions.
5. **Retry**: Add only where canonical refetch exists. HealthWidget and
   DatasetStatusWidget can retry (hooks return full useQuery result).
   ActivePlanWidget and RiskSummaryWidget **cannot retry** — hooks do not
   expose refetch; modifying them is out of scope. **Reported as blocker.**
6. **Detail loading**: Use existing loading flags. Add panel skeletons without
   changing API orchestration. Do not refactor useRiskDetail.

---

## 3. In-Scope Changes

### 3.1 Shared Primitives

- `frontend/src/components/common/DataErrorState.tsx`
- `frontend/src/components/common/DataEmptyState.tsx`
- Tests for both

### 3.2 Dashboard Widgets

- **HealthWidget**: Add retry button on error (uses refetch from useHealth)
- **DatasetStatusWidget**: Add retry button on error (uses refetch from
  useDatasetStatus)
- **ActivePlanWidget**: **BLOCKED** — useActivePlan does not expose refetch.
  Report as deferred item.
- **RiskSummaryWidget**: **BLOCKED** — useRiskSummary does not expose refetch.
  Report as deferred item.

### 3.3 Supply Risk List

- Replace inline error alert with DataErrorState
- Replace inline empty/filtered-empty with DataEmptyState
- Add tabular-nums to numeric cells (Shortage, Available, Required)

### 3.4 Supply Risk Detail

- Remove redundant "Back to Supply Risks" button
- Fix breadcrumb: loading leaf shows "Loading risk..." (not "Loading..."),
  resolved leaf shows risk_id
- Add panel-level skeletons for enrichment panels during loading
- Flatten incoming-supply nested conditional (readability only, behavior
  unchanged)
- Replace inline error blocks with DataErrorState where applicable
- Fix PartialFailurePlaceholder: role="status" → role="alert"
- Add tabular-nums to EvidencePanel numeric values

### 3.5 Shared Shell

- Add skip-link to main content in AuthenticatedLayout
- Replace sidebar user-summary button with div (non-interactive)
- Add main landmark id for skip-link target

### 3.6 Route Heading Hierarchy

- Login: h1 "ForgeMind", h2 "Sign in" (already correct)
- Dashboard: h1 "Executive Dashboard" (already correct)
- Risk List: h1 "Supply Risk Analysis" (already correct)
- Risk Detail: add h1 with risk_id (currently missing h1)

### 3.7 formatDate Utility

- Extract duplicate formatDate from supply-risk.tsx and ActivePlanWidget.tsx
  into `frontend/src/lib/format.ts`
- Small local utility, no contract change

---

## 4. Explicit Out-of-Scope

- Global Axios interceptor
- AuthProvider or ProtectedRoute changes
- useActivePlan, useRisks, useRiskDetail changes
- API client changes
- Backend changes
- New endpoints or routes
- Mobile layout
- Large-screen two-column redesign
- New widgets
- Phase 4/5/6 placeholder changes
- WP-3.8 or WP-3.9 work
- Hardcoded Golden Scenario values

---

## 5. Files Allowed to Change

```
docs/planning/wp_3_7_loading_error_states_spec.md          (new)
frontend/src/
├── components/
│   ├── common/
│   │   ├── DataErrorState.tsx                               (new)
│   │   ├── DataEmptyState.tsx                               (new)
│   │   ├── DataErrorState.test.tsx                          (new)
│   │   └── DataEmptyState.test.tsx                          (new)
│   ├── dashboard/
│   │   ├── ActivePlanWidget.tsx                             (no retry — blocked)
│   │   ├── RiskSummaryWidget.tsx                            (no retry — blocked)
│   │   ├── HealthWidget.tsx                                 (updated — add retry)
│   │   ├── DatasetStatusWidget.tsx                          (updated — add retry)
│   │   └── __tests__/{HealthWidget,DatasetStatusWidget}.test.tsx (updated)
│   ├── layout/
│   │   ├── AuthenticatedLayout.tsx                          (updated — skip-link)
│   │   └── Sidebar.tsx                                      (updated — div)
│   ├── supply-risk/
│   │   ├── RiskList.tsx                                     (updated — primitives, tabular-nums)
│   │   ├── PartialFailurePlaceholder.tsx                    (updated — role="alert")
│   │   ├── EvidencePanel.tsx                                (updated — tabular-nums)
│   │   ├── __tests__/{RiskList,PartialFailurePlaceholder,EvidencePanel}.test.tsx (updated)
│   └── ui/ (no changes)
├── lib/
│   └── format.ts                                            (new — formatDate)
├── routes/
│   ├── supply-risk.tsx                                      (updated — use format.ts)
│   ├── supply-risk-detail.tsx                               (updated — breadcrumb, back button, h1, skeletons)
│   └── __tests__/ (if any)
```

---

## 6. Files That MUST NOT Change

- Every file under `backend/`, `seed/`, `forgemind_project_source_of_truth/`,
  `infra/`, `.github/`
- `docker-compose.yml`, `docker-compose.dev.yml`, `Makefile`, `HERMES.md`
- `docs/planning/phase_3_planning_handoff.md`
- `frontend/src/hooks/useActivePlan.ts`
- `frontend/src/hooks/useRisks.ts`
- `frontend/src/hooks/useRiskDetail.ts`
- `frontend/src/lib/risks-api.ts`
- `frontend/src/lib/risk-detail-api.ts`
- `frontend/src/lib/production-plans-api.ts`
- `frontend/src/contexts/auth.context.tsx`
- `frontend/src/routes/protected.tsx`
- `frontend/src/lib/api.ts`
- Any WP-3.4, WP-3.5, WP-3.6 boundary files

---

## 7. Test Requirements

- [ ] DataErrorState renders message and retry callback
- [ ] DataEmptyState renders primary and secondary text
- [ ] HealthWidget retry invokes refetch
- [ ] DatasetStatusWidget retry invokes refetch
- [ ] Error states expose role="alert"
- [ ] PartialFailurePlaceholder uses role="alert"
- [ ] Skip-link targets main landmark
- [ ] Sidebar summary is not a button
- [ ] Detail breadcrumb loading and resolved labels
- [ ] Duplicate back button absent
- [ ] Exactly one h1 on Login, Dashboard, Risk List, Risk Detail
- [ ] tabular-nums on RiskList and EvidencePanel numeric values
- [ ] WP-3.4 dashboard rendering unchanged
- [ ] WP-3.5 sorting/filtering unchanged
- [ ] WP-3.6 risk-detail and partial-failure behavior unchanged
- [ ] No hardcoded Golden Scenario values in source

---

## 8. Test Gates

All must pass before PR submission:

- [ ] `npm run lint` — zero warnings
- [ ] `npm run type-check` — zero errors
- [ ] `npm test` — Vitest green (new tests included)
- [ ] `npm run build` — zero errors
- [ ] `npm run test:e2e` — Playwright trivial spec green
- [ ] `make lint` — backend lint clean
- [ ] `make test` — backend ≥ 709 tests, zero regressions

---

## 9. Acceptance Criteria

- [ ] HealthWidget and DatasetStatusWidget show retry button on error
- [ ] ActivePlanWidget and RiskSummaryWidget error states documented as
      blocked (hooks do not expose refetch)
- [ ] RiskList uses DataErrorState and DataEmptyState
- [ ] Risk Detail uses DataErrorState for full-page errors
- [ ] Risk Detail breadcrumb shows meaningful labels
- [ ] Risk Detail has no redundant back button
- [ ] Risk Detail has exactly one h1
- [ ] PartialFailurePlaceholder uses role="alert"
- [ ] AuthenticatedLayout has skip-link
- [ ] Sidebar user summary is non-interactive
- [ ] EvidencePanel and RiskList numeric cells use tabular-nums
- [ ] formatDate extracted to lib/format.ts
- [ ] 1024px layout verified (no horizontal clip of primary content)
- [ ] All test gates pass
- [ ] Single WP-3.7 commit
- [ ] No WP-3.8 or WP-3.9 work
- [ ] No hardcoded Golden Scenario values

---

## 10. Known Blockers and Deferred Items

### BLOCKER: ActivePlanWidget and RiskSummaryWidget retry

**Issue**: The hooks `useActivePlan` and `useRiskSummary` do not expose
`refetch` in their return types. Adding retry would require modifying these
hooks, which is explicitly out of scope per architectural decision #5.

**Resolution**: Document as deferred architecture work. Recommend that a
future WP (possibly WP-3.8 or a separate architectural task) expose refetch
on these hooks to enable retry in their widgets.

**Workaround**: None. These widgets will show error text without retry.

### DEFERRED: Global 401/403 interceptor

**Issue**: phase_3_planning_handoff §5.4 and WP-3.6 §2.9 defer "broader
auth hardening" to WP-3.7. A true interceptor touches every authenticated
request and overlaps with ProtectedRoute.

**Resolution**: Explicitly deferred to a later architectural task. WP-3.7
stays pure polish. No interceptor added.

---

## 11. Verification Commands

```bash
npm ci
npm run lint
npm run type-check
npm test
npm run build
npm run test:e2e
make lint
make test
```

---

## 12. Demo Narrative Contribution

WP-3.7 advances the 60–90 second portfolio demonstration:

**Before (WP-3.6):** Dashboard and detail pages show inconsistent error
states; some widgets lack retry; detail page has redundant navigation;
accessibility semantics are inconsistent.

**After (WP-3.7):** Dashboard widgets with retry show professional
resilience; error states are visually and semantically consistent; detail
page breadcrumb reads naturally; skip-link supports keyboard navigation;
numeric columns align cleanly. The difference between "engineer's prototype"
and "product."

---

**END OF WP-3.7 SPECIFICATION**
