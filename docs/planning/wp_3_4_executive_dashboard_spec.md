# WP-3.4 Specification — Executive Dashboard

**Status:** APPROVED FOR IMPLEMENTATION
**Work Package:** WP-3.4
**Phase:** 3 (Core UI)
**Base:** main at f4054bd966b73a5aa1f76eb53612c8aa1bf27f46
**Branch:** feature/phase-3-wp-3-4-dashboard
**Depends on:** WP-3.1, WP-3.2, WP-3.3 (all merged)

---

## 1. Objective

Deliver the Executive Dashboard displaying real backend data: active production plan, risk severity summary, system health, and dataset status. Render honest placeholders for widgets without backend support (agent runs, approvals, time saved). No mock metrics. No hardcoded Golden Scenario values.

---

## 2. Canonical Backend Contracts

### 2.1 Health Endpoint

- **Route:** `GET /health` (root path, NOT under `/api/v1`)
- **Authentication:** None (public)
- **Response shape:**
  ```typescript
  {
    status: "healthy" | "degraded" | "unhealthy";
    timestamp: string; // ISO 8601
    correlation_id: string;
    checks: {
      backend: "ok";
      postgresql: "ok" | "error: ...";
      redis: "ok" | "error: ..." | "unavailable";
      alembic_revision: string;
      worker: "ok" | "unavailable";
    }
  }
  ```
- **Frontend consumption:** Must NOT use the existing Axios instance with baseURL `/api/v1`. Must use a separate client or absolute path `/health`.

### 2.2 Dataset Status Endpoint

- **Route:** `GET /api/v1/system/dataset/status`
- **Authentication:** Required (Bearer token)
- **Response shape:**
  ```typescript
  {
    status: "valid" | "invalid" | "not_loaded";
    dataset_version: string;
    checksum_algorithm: string;
    expected_checksum: string;
    actual_checksum: string | null;
  }
  ```
- **Status semantics:**
  - `valid`: all collections match approved fixture
  - `invalid`: dataset exists but differs
  - `not_loaded`: all business tables empty
- **Failure:** HTTP 500 with `{error, message}` on infrastructure failure

### 2.3 Production Plans Endpoint

- **Route:** `GET /api/v1/production-plans`
- **Authentication:** Required (Bearer token)
- **Response shape:** Paginated list
  ```typescript
  {
    items: ProductionPlanSummary[];
    limit: number;
    offset: number;
    total: number;
  }
  ```
- **ProductionPlanSummary:**
  ```typescript
  {
    code: string;
    status: "DRAFT" | "APPROVED" | "EXECUTING" | "COMPLETED" | "CLOSED";
    period_start: string; // ISO date
    period_end: string; // ISO date
  }
  ```
- **Active plan selection:** Filter `status === "EXECUTING"`
- **Empty state:** `items === []` or `total === 0`
- **Multiple active plans:** Deterministic selection:
  1. Latest `period_start`
  2. Then latest `created_at` (if available, else skip)
  3. Then lexical `code` (ascending)
  4. Show non-blocking data-consistency warning

### 2.4 Production Plan Risks Endpoint

- **Route:** `GET /api/v1/production-plans/{plan_code}/risks`
- **Authentication:** Required (Bearer token)
- **Path parameter:** `plan_code` (string, e.g., "PLAN-2026-W31")
- **Response shape:** Plain array (not paginated)
  ```typescript
  RiskRecordWithId[] = [
    {
      risk_id: string; // e.g., "RISK-001"
      component_code: string;
      component_name: string;
      affected_wo_code: string;
      required: string; // Decimal as string, 4 decimal places
      available: string;
      confirmed_early: string;
      confirmed_late: string;
      shortage: string;
      severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
      has_approved_alternative: boolean;
      has_proposed_alternative: boolean;
      need_date: string; // ISO date
      plan_code: string;
    }
  ]
  ```
- **Severity aggregation:** Frontend counts by severity (allowed per Phase 3 plan §5.1)
- **Zero risks:** `[]` (empty array)
- **Unknown plan:** HTTP 404 with `detail: "Production plan '<code>' not found"`
- **401/403:** Standard auth errors
- **5xx:** Backend error

---

## 3. Dashboard Information Hierarchy

### 3.1 Primary (Top Tier)

- **Active Production Plan Widget**
  - Plan code
  - Status badge (EXECUTING)
  - Period (start → end)
  - Empty state: "No active production plan"
  - Multiple active: show warning

- **Risk Severity Summary Widget**
  - Total risk count
  - Breakdown by severity: CRITICAL, HIGH, MEDIUM, LOW
  - Zero risks: "No active risks"
  - Failure state: "Unable to load risk data"

### 3.2 Operational (Second Tier)

- **API Health Widget**
  - Overall status: healthy / degraded / unhealthy
  - Dependency checks: postgresql, redis, alembic, worker
  - Failure state: "Health check unavailable"

- **Dataset Status Widget**
  - Status: valid / invalid / not_loaded
  - Dataset version
  - Checksum match indicator
  - Failure state: "Dataset status unavailable"

### 3.3 Future Capability Placeholders (Third Tier)

- **Latest Agent Runs** — "Unavailable — Phase 5"
- **Pending Approvals** — "Unavailable — Phase 6"
- **Estimated Time Saved** — "Metric available in Phase 5"

Placeholders:
- Visually distinct (muted styling, dashed border or reduced opacity)
- No network calls
- Explanatory copy

---

## 4. Active-Plan Selection Rule

1. Filter `items` where `status === "EXECUTING"`
2. Zero active → empty state ("No active production plan")
3. One active → select it
4. Multiple active → deterministic selection:
   - Sort by `period_start` DESC
   - Tie-break by `code` ASC (lexical)
   - Select first
   - Show non-blocking warning: "Multiple active plans detected. Showing the most recent."

---

## 5. Severity Aggregation Rule

- Count risks by `severity` field
- Known values: CRITICAL, HIGH, MEDIUM, LOW
- Unknown values: count as "OTHER" or ignore (do not crash)
- Compute total: sum of all known severities
- Render as badges or counters with semantic colors:
  - CRITICAL: red
  - HIGH: amber/orange
  - MEDIUM: yellow
  - LOW: blue

---

## 6. Independent UX States

Each widget renders independently. Failures do not collapse into a global error state.

### 6.1 Page-Level States

- **Loading:** Skeleton placeholders for all widgets
- **Ready:** Real data rendered

### 6.2 Production Plan Widget States

- Loading: skeleton
- Success: plan details rendered
- Empty (no plans): "No production plans found"
- Empty (no active plan): "No active production plan"
- Failure: "Unable to load production plans" with retry guidance
- Multiple active: warning banner

### 6.3 Risk Summary Widget States

- Loading: skeleton
- Success: severity counts rendered
- Zero risks: "No active risks for this plan"
- Failure: "Unable to load risk data" (plan remains visible)
- 404 (unknown plan): "Production plan not found"

### 6.4 Health Widget States

- Loading: skeleton
- Success: status + dependency checks
- Degraded: yellow/amber indicator
- Unhealthy: red indicator
- Failure: "Health check unavailable"

### 6.5 Dataset Status Widget States

- Loading: skeleton
- Success: status + version
- Invalid: warning indicator
- Not loaded: informational indicator
- Failure: "Dataset status unavailable"

### 6.6 Placeholder Widget States

- Static: always rendered with explanatory copy
- No loading, no failure, no network call

### 6.7 Auth States

- 401: handled by ProtectedRoute (redirect to /login)
- 403: render error state "Access denied"
- Network failure: render error state per widget

---

## 7. Visual Design Direction

**Industrial operations workspace aesthetic:**
- Dark steel background (bg-steel-950 for page, bg-steel-900/800 for cards)
- Subtle borders (border-steel-700)
- Functional spacing (p-6 for cards, gap-6 for grid)
- Professional B2B appearance
- Restrained, functional, industrial workspace — not decoration
- No cyberpunk, no gradients, no excessive animation
- Usable at viewport width 1024px and above

**Typography:**
- White/off-white for primary text (text-white, text-steel-100)
- Muted steel for secondary text (text-steel-400, text-steel-500)
- Semantic colors only for status:
  - CRITICAL: red-500
  - HIGH: amber-500
  - MEDIUM: yellow-500
  - LOW: blue-500
  - healthy: green-500
  - degraded: yellow-500
  - unhealthy: red-500

**Card styling:**
- Rounded corners (rounded-xl)
- Subtle border (border border-steel-700)
- Background: bg-steel-900/40 or bg-steel-800/40
- Padding: p-6
- Shadow: shadow-sm or none (restrained)

**Layout:**
- Grid-based (grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3)
- Primary widgets span full width or 2 columns
- Operational widgets span 1 column
- Placeholders span 1 column, visually distinct (opacity-60, border-dashed)

**Motion:**
- Subtle fade-in on data load (transition-opacity)
- No bounce, no scale, no excessive animation
- Skeleton pulse during loading (already in shadcn/ui)

---

## 8. Health URL Configuration

- Introduce `VITE_HEALTH_URL` environment variable
- Default: `/health`
- Do NOT derive by stripping `/api/v1` from `VITE_API_BASE_URL`
- Do NOT use the existing Axios instance with baseURL `/api/v1`
- Create a separate health client or use `fetch` directly

---

## 9. Implementation Sequence

1. Create spec document (this file)
2. Create and checkout branch
3. Install dependencies (if any)
4. Implement API clients:
   - `frontend/src/lib/health-api.ts` — health endpoint
   - `frontend/src/lib/dataset-api.ts` — dataset status
   - `frontend/src/lib/production-plans-api.ts` — production plans
   - `frontend/src/lib/risks-api.ts` — risks
5. Implement dashboard hooks:
   - `useHealth()` — health data
   - `useDatasetStatus()` — dataset status
   - `useActivePlan()` — active plan selection
   - `useRiskSummary()` — severity aggregation
6. Implement dashboard components:
   - `ActivePlanWidget.tsx`
   - `RiskSummaryWidget.tsx`
   - `HealthWidget.tsx`
   - `DatasetStatusWidget.tsx`
   - `PlaceholderWidget.tsx`
   - `Dashboard.tsx` (main page)
7. Write unit tests for:
   - Active plan selection logic
   - Severity aggregation logic
   - API client error handling
   - Widget rendering states
8. Run all test gates
9. Perform pre-push focused review
10. Stage files explicitly, create single WP-3.4 commit
11. Stop before push

---

## 10. Test Requirements

### 10.1 Active Plan Selection

- [ ] Zero plans → empty state
- [ ] Zero active plans → "No active production plan"
- [ ] One active plan → select it
- [ ] Multiple active plans → deterministic selection (latest period_start, then code)
- [ ] Multiple active plans → warning displayed

### 10.2 Severity Aggregation

- [ ] Zero risks → total = 0, all counts = 0
- [ ] Mixed severities → correct counts
- [ ] Unknown severity → ignored or counted as OTHER
- [ ] Total = sum of known severities

### 10.3 Widget Rendering

- [ ] Loading state renders skeleton
- [ ] Success state renders real data
- [ ] Empty state renders appropriate message
- [ ] Failure state renders error message
- [ ] 401/403/404/5xx/network errors mapped correctly

### 10.4 Independent Failures

- [ ] Plan failure does not affect health widget
- [ ] Risk failure does not affect plan widget
- [ ] Health failure does not affect dataset widget

### 10.5 Placeholders

- [ ] No network calls made
- [ ] Explanatory copy rendered
- [ ] Visually distinct from live widgets

### 10.6 Role Access

- [ ] All authenticated roles can access Dashboard
- [ ] No role-specific filtering

### 10.7 No Hardcoded Values

- [ ] No PLAN-2026-W31 in source
- [ ] No RISK-001/002/003 in source
- [ ] No severity counts hardcoded

---

## 11. Test Gates

All must pass before PR submission:

- [ ] `npm run lint` — zero warnings
- [ ] `npm run type-check` — zero errors
- [ ] `npm test` — Vitest green (new tests included)
- [ ] `npm run build` — zero errors
- [ ] `npm run test:e2e` — Playwright trivial spec still green
- [ ] `make test` — backend ≥ 709 tests, zero regressions
- [ ] `make lint` — backend lint still clean

---

## 12. Files Allowed to Change

```
docs/planning/wp_3_4_executive_dashboard_spec.md          (new)
frontend/
├── src/
│   ├── lib/
│   │   ├── health-api.ts                                 (new)
│   │   ├── dataset-api.ts                                (new)
│   │   ├── production-plans-api.ts                       (new)
│   │   └── risks-api.ts                                  (new)
│   ├── hooks/
│   │   ├── useHealth.ts                                  (new)
│   │   ├── useDatasetStatus.ts                           (new)
│   │   ├── useActivePlan.ts                              (new)
│   │   └── useRiskSummary.ts                             (new)
│   ├── components/
│   │   └── dashboard/
│   │       ├── ActivePlanWidget.tsx                      (new)
│   │       ├── RiskSummaryWidget.tsx                     (new)
│   │       ├── HealthWidget.tsx                          (new)
│   │       ├── DatasetStatusWidget.tsx                   (new)
│   │       ├── PlaceholderWidget.tsx                     (new)
│   │       └── __tests__/
│   │           ├── ActivePlanWidget.test.tsx             (new)
│   │           ├── RiskSummaryWidget.test.tsx            (new)
│   │           ├── HealthWidget.test.tsx                 (new)
│   │           ├── DatasetStatusWidget.test.tsx          (new)
│   │           └── PlaceholderWidget.test.tsx            (new)
│   └── routes/
│       └── dashboard.tsx                                 (replaced)
└── .env.example                                          (updated — VITE_HEALTH_URL)
```

---

## 13. Files That MUST NOT Change

- Every file under `backend/`
- Every file under `seed/`
- Every file under `forgemind_project_source_of_truth/`
- Every file under `infra/`
- `docker-compose.yml`, `docker-compose.dev.yml`
- `Makefile`
- `.github/`
- `docs/planning/phase_3_planning_handoff.md`
- `HERMES.md`
- `frontend/src/contexts/auth.context.tsx` (WP-3.2 boundary)
- `frontend/src/routes/protected.tsx` (WP-3.2 boundary)
- `frontend/src/routes/login.tsx` (WP-3.2 boundary)
- `frontend/src/lib/auth-api.ts` (WP-3.2 boundary)
- `frontend/src/lib/storage.ts` (WP-3.2 boundary)
- `frontend/src/components/layout/**` (WP-3.3 boundary)

---

## 14. Explicit Out-of-Scope

- Risk list or risk detail (WP-3.5, WP-3.6)
- Clickable drill-down to risk detail
- What-if simulation
- Supplier disruption controls
- Recommendations or AI-generated text
- Mock business metrics
- Hardcoded Golden Scenario values
- Backend endpoint creation or modification
- WP-3.5 or later functionality
- Mobile responsive mode (Post-MVP)

---

## 15. Acceptance Criteria

- [ ] Dashboard renders active plan from backend response
- [ ] Risk severity counts aggregated from backend response
- [ ] System health reflects /health response
- [ ] Dataset status reflects /system/dataset/status response
- [ ] Placeholders render static explanatory copy, no network calls
- [ ] No PLAN-2026-W31 or RISK-001/002/003 values hardcoded in source
- [ ] Loading/success/empty/degraded states tested
- [ ] All authenticated roles can access Dashboard
- [ ] Independent widget failures do not collapse into global error
- [ ] Multiple active plans show warning
- [ ] All test gates pass
- [ ] No unauthorized artifacts in working tree
- [ ] Single intentional WP-3.4 commit
- [ ] No WP-3.5+ work

---

## 16. Verification Commands

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

**END OF WP-3.4 SPECIFICATION**
