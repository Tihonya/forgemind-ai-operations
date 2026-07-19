# Phase 3 Planning Handoff

**Status:** **APPROVED BY PRODUCT OWNER**
**Purpose:** Authoritative contract for Phase 3 (Core UI).
**Planning complete.** Ready to execute WP-3.1.
**No implementation started.** No branching. No installation. No backend changes.

---

## 1. Repository state verification

| Item | Expected | Actual | Status |
|------|----------|--------|--------|
| Branch | main | main | ✓ |
| HEAD | a31224a402bb37509bedff25e13c7225b16c77c4 | a31224a402bb37509bedff25e13c7225b16c77c4 | ✓ |
| origin/main | a31224a402bb37509bedff25e13c7225b16c77c4 | a31224a402bb37509bedff25e13c7225b16c77c4 | ✓ |
| Working tree | clean | clean | ✓ |
| Recent commit | a31224d (Merge PR #15) | a31224d | ✓ |

Repository state matches. Phase 2 exit criteria verified
(WP-2.9 merged; 709 tests passed; 0 skipped; 92% backend coverage;
HERMES.md execution-safety policy merged).

---

## 2. Phase 3 objective (authoritative source)

Source: `forgemind_project_source_of_truth/07_ROADMAP.md` — Phase 3.

**Deliverables:**
- Dashboard
- Risk list
- Risk details
- Evidence calculation view
- Responsive desktop layout

**Exit criteria:**
- UI works with real backend data
- No hardcoded Golden Scenario results
- Frontend tests pass

**Phase 3 boundary:** Core UI built on Phase 2 backend.
Phases 4 (RAG), 5 (AI workflow), 6 (Approval/Audit), 7 (Deployment) are OUT.

---

## 3. Frontend baseline

The frontend directory exists but contains **only a Phase 0/1 placeholder**:

| File | State |
|------|-------|
| `frontend/src/App.tsx` | 24 lines, static "Phase 0 Bootstrap Complete" screen |
| `frontend/src/main.tsx` | standard React bootstrap, no router |
| `frontend/src/index.css` | tailwind directives + dark theme tokens (steel/primary) |
| `frontend/tailwind.config.ts` | industrial colour tokens already defined |
| `frontend/vite.config.ts` | dev-server proxy `/api` → `http://localhost:8000` |
| `frontend/package.json` | React 18, react-router-dom 6, TanStack Query 5, axios, recharts, date-fns, Vitest. Playwright **not yet installed**. |
| `frontend/src/components/*` | does not exist yet |
| `frontend/src/routes/*` | does not exist yet |
| `frontend/src/hooks/*` | does not exist yet |
| `frontend/src/lib/*` | does not exist yet |
| `frontend/components.json` | does not exist yet (shadcn/ui not installed) |
| `frontend/e2e/` | does not exist yet |

Phase 3 starts from a scaffold point, not a working application.

---

## 4. Final approved Product Owner decisions

### A-1 — Dashboard unavailable widgets

Dashboard widgets without a backend source must render an honest
"Unavailable — Phase N" placeholder.

No fake metrics. No decorative numbers.

Consistent with HERMES.md UI rule: "avoid fake charts and decorative metrics".

### A-2 — Sources and AI Recommendation panels

Both panels render the single state:

> Unavailable in current release

No deterministic rule-based hint may be placed inside the panel labelled
"AI Recommendation".

A separately labelled non-AI UI element may be considered later, but is
not required in WP-3.1 and is not part of the Phase 3 scope.

### A-3 — State management

TanStack Query plus React Context only.

No Zustand. No other global state library.

Consistent with DEC-015.

### A-4 — "Estimated time saved" widget

Option A. Rendered text:

> Metric available in Phase 5

No backend endpoint. No synthetic calculation. No proxy formula.

### A-5 — Responsive scope

Desktop-first UI.

- Minimum supported viewport: **1024px**
- Tablet: must remain usable
- Mobile phone: **out of scope** for Phase 3 (Post-MVP per SoT §5)

### A-6 — Navigation structure

Left sidebar with icon + label.

Role-aware navigation visibility is **front-end UX only**.
It must **never** be described, documented, or enforced as an
authorization boundary. Backend authorization remains authoritative
per DEC-028 / FR-02 / HERMES.md.

### A-7 — shadcn/ui scaffolding

Use shadcn/ui over the existing Tailwind theme.

Install **only** the components required by the current work package.

Do **not** scaffold the entire shadcn/ui catalogue in WP-3.1.

### A-8 — E2E testing framework

Playwright.

WP-3.1 creates only the minimal framework skeleton (config + one trivial
passing spec). The Golden Scenario E2E belongs to WP-3.9.

---

## 5. Mandatory architectural clarifications for Phase 3

These facts are **canonical for Phase 3** and must be respected in
every work package:

### 5.1 Risk filtering is client-side

Risk filtering (by severity, by component code, by plan) is performed
entirely in the front-end against the single response of
`GET /api/v1/production-plans/{plan_code}/risks`.

Phase 3 does **not** introduce new backend query parameters for risk
filtering. No backend filter changes are required.

### 5.2 Risk detail is composed, not a distinct resource

Risk detail is composed by the front-end from existing Phase 2 read
endpoints:

- `GET /api/v1/production-plans/{code}` — plan metadata
- `GET /api/v1/production-orders/{code}` — affected work order
- `GET /api/v1/components/{code}` — component detail
- `GET /api/v1/inventory/{component_code}` — balances + reservations
- `GET /api/v1/inventory-reservations` — reservation detail
- `GET /api/v1/purchase-orders` — incoming supply dates

Phase 3 **does not** introduce:
- a persisted `/risks/{risk_id}` endpoint,
- a new resource for risk detail,
- any change to the WP-2.9 risk response shape,
- any backend endpoint addition or mutation.

### 5.3 Placeholders do not make network requests

Placeholder panels (A-1, A-2, A-4) must **not** issue network requests
to nonexistent or out-of-scope endpoints. They are static UI elements
with explanatory copy.

### 5.4 Navigation hiding is UX only, not security

Role-aware menu-item visibility is a UX convenience.

- The front-end must **never** omit backend authorization checks.
- Backend authorization remains authoritative per `get_current_user` +
  `require_role` on every request.
- If a user reaches a hidden screen via direct URL, the backend's
  401/403 response must surface cleanly. The front-end must not
  present a privileged view.

### 5.5 No new backend endpoints in Phase 3

Phase 3 is a pure front-end phase. No new backend endpoints will be
introduced. Future endpoints (document index, workflow runs, approvals,
audit, model status, reset, time-saved metric) belong to later phases.

### 5.6 Golden Scenario values must never be hardcoded in UI source

Per SoT `02_SYSTEM_BEHAVIOR_AND_DATA.md` §4 and AT-005:

RISK-001 / RISK-002 / RISK-003 values must never appear as constants,
fixtures, default props, or seed values inside any front-end source file.
They must be read from the backend response at runtime.

---

## 6. Phase 3 screens

Phase 3 delivers four primary UI surfaces:

1. Login
2. Executive Dashboard
3. Supply Risk Analysis — list
4. Supply Risk Analysis — detail and evidence

The authenticated layout shell (sidebar + header) is a shared
cross-screen foundation, not a fifth standalone screen.

### 6.1 In scope

| # | Screen | SoT § | Backend status |
|---|--------|-------|----------------|
| 1 | Login | 3.1 | ✓ full |
| 2 | Executive Dashboard | 3.2 | ✓ partial; placeholders per A-1 / A-4 |
| 3 | Supply Risk Analysis — list | 3.3 | ✓ full |
| 4 | Supply Risk Analysis — detail and evidence | 3.3 | ✓ full (composed) |

Cross-screen foundation (shared, not a standalone screen):

- Authenticated layout shell (sidebar + header): provides the chrome
  for the four screens above. No backend API required. Pure front-end.

### 6.2 Out of scope

| # | Screen | Phase | Reason |
|---|--------|-------|--------|
| — | Approval Center | 6 | No approval_requests backend |
| — | Knowledge Sources | 4 | No documents/RAG backend |
| — | Workflow Run Details | 5 | No workflow_runs backend |
| — | Audit Log | 6 | No audit_events backend |
| — | Admin / Model Status | 7 | Deployment-time feature |

---

## 7. Full explicit out-of-scope list

Phase 3 must **NOT** implement:

- Approval Center (Phase 6)
- Knowledge Sources screen (Phase 4)
- Workflow Run Details screen (Phase 5)
- Audit Log screen (Phase 6)
- Admin / Model Status console (Phase 7)
- Public deployment, HTTPS, VPS, Caddy (Phase 7)
- Demo reset admin UI (AT-015 / Phase 7)
- Mobile phone responsive mode (Post-MVP)
- Multi-language interface (Post-MVP)
- Report/PDF export (Post-MVP)
- Any new backend endpoint
- RAG source rendering with real content (Phase 4)
- AI recommendation text rendering (Phase 5)
- WebSocket / SSE (DEC-012 + §5.5)
- Any additional demo accounts beyond DEC-028 five
- Zustand or any other global state library (A-3)
- Hard-coded Golden Scenario values in UI source
- Any rule-based hint inside the panel labelled "AI Recommendation" (A-2)
- Full shadcn/ui catalogue scaffold (A-7)
- Golden Scenario Playwright spec in WP-3.1 (A-8)

---

## 8. Backend-readiness matrix

### 8.1 Screen 1 — Login

| Required API | Available | Missing | Severity | Resolution |
|--------------|-----------|---------|----------|------------|
| POST /api/v1/auth/login | ✓ | — | — | — |
| GET /api/v1/auth/me | ✓ | — | — | — |
| Frontend token storage | front-end only | WP-3.2 | — | — |

**Phase 3 blockers: NONE.**

### 8.2 Screen 2 — Executive Dashboard

| Required widget | Available | Missing | Severity | Resolution |
|-----------------|-----------|---------|----------|------------|
| Active production plan | ✓ | — | — | GET /production-plans |
| Risk count by severity | ✓ | — | — | aggregate risks response |
| System status | ✓ | — | — | /health + /system/dataset/status |
| Latest agent runs | ✗ | workflow_runs (Phase 5) | SOFT | placeholder "Unavailable — Phase 5" |
| Pending approvals | ✗ | approval_requests (Phase 6) | SOFT | placeholder "Unavailable — Phase 6" |
| Estimated time saved | ✗ | none by design (A-4) | SOFT | "Metric available in Phase 5" |

**Phase 3 blockers: NONE.** All gaps handled by honest placeholders per §5.3.

### 8.3 Screen 3 — Supply Risk Analysis (list + detail + evidence)

| Required API | Available | Missing | Severity | Resolution |
|--------------|-----------|---------|----------|------------|
| GET /api/v1/production-plans | ✓ | — | — | plan selector |
| GET /api/v1/production-plans/{code} | ✓ | — | — | plan header |
| GET /api/v1/production-plans/{code}/risks | ✓ | — | — | risk list + client-side filters |
| GET /api/v1/components/{code} | ✓ | — | — | component side-panel |
| GET /api/v1/inventory/{component_code} | ✓ | — | — | evidence balances + reservations |
| GET /api/v1/inventory-reservations | ✓ | — | — | reservation detail |
| GET /api/v1/purchase-orders | ✓ | — | — | incoming supply dates |
| GET /api/v1/production-orders/{code} | ✓ | — | — | affected work order |
| RAG source documents | ✗ | Phase 4 | SOFT | "Unavailable in current release" (A-2) |
| AI Recommendation panel | ✗ | Phase 5 | SOFT | "Unavailable in current release" (A-2) |

**Phase 3 blockers: NONE.**
Client-side filtering per §5.1. Detail composition per §5.2.

### 8.4 Cross-screen foundation — Authenticated layout shell

No backend API required. Pure front-end.
Backend authorization remains authoritative per §5.4.
The layout shell is not a primary screen; it provides the chrome
for the four primary screens listed in §6.

---

## 9. Branching strategy

### 9.1 Approved model

**One isolated branch and PR per work package.**

The monolithic `feature/phase-3-core-ui` branch from the initial
draft was **rejected** by the Product Owner. Each WP is implemented
on its own short-lived feature branch and merged individually to
`main` via a dedicated PR.

### 9.2 Branch naming convention

`feature/phase-3-wp-<N>-<slug>`

| WP | Branch |
|----|--------|
| WP-3.1 | `feature/phase-3-wp-3-1-frontend-scaffold` |
| WP-3.2 | `feature/phase-3-wp-3-2-auth-flow` |
| WP-3.3 | `feature/phase-3-wp-3-3-app-shell` |
| WP-3.4 | `feature/phase-3-wp-3-4-dashboard` |
| WP-3.5 | `feature/phase-3-wp-3-5-risk-list` |
| WP-3.6 | `feature/phase-3-wp-3-6-risk-detail` |
| WP-3.7 | `feature/phase-3-wp-3-7-loading-error-states` |
| WP-3.8 | `feature/phase-3-wp-3-8-at005-frontend-test` |
| WP-3.9 | `feature/phase-3-wp-3-9-e2e-golden-scenario` |

### 9.3 Branching rules (per HERMES.md)

- Never push directly to `main`
- Never force-push (categorical prohibition)
- Never rebase a shared branch without PO approval
- Never self-merge
- Never combine multiple WPs in one PR
- Conventional commit messages
- Each branch created from the **latest** `main` HEAD at branch-creation time
- Each PR verified independently (`make test`, `make lint`, frontend gates)

---

## 10. Work packages (overview after approval)

Execution order:
WP-3.1 → WP-3.2 → WP-3.3 → WP-3.4 → WP-3.5 → WP-3.6 → WP-3.7 → WP-3.8 → WP-3.9.

| WP | Name | Depends on | Branch |
|----|------|------------|--------|
| WP-3.1 | Frontend design-system scaffold | — | feature/phase-3-wp-3-1-frontend-scaffold |
| WP-3.2 | Auth flow + route guards | WP-3.1 | feature/phase-3-wp-3-2-auth-flow |
| WP-3.3 | App shell + navigation + role-aware sidebar | WP-3.2 | feature/phase-3-wp-3-3-app-shell |
| WP-3.4 | Executive Dashboard | WP-3.3 | feature/phase-3-wp-3-4-dashboard |
| WP-3.5 | Supply Risk list page | WP-3.3 | feature/phase-3-wp-3-5-risk-list |
| WP-3.6 | Supply Risk detail + evidence panel | WP-3.5 | feature/phase-3-wp-3-6-risk-detail |
| WP-3.7 | Loading / empty / error states | WP-3.4, WP-3.6 | feature/phase-3-wp-3-7-loading-error-states |
| WP-3.8 | AT-005 frontend contract test | WP-3.6 | feature/phase-3-wp-3-8-at005-frontend-test |
| WP-3.9 | Playwright E2E Golden Scenario | WP-3.7 | feature/phase-3-wp-3-9-e2e-golden-scenario |

---

## 11. WP-3.1 — boundaries (exact)

**Branch:** `feature/phase-3-wp-3-1-frontend-scaffold`
**Base:** `main` at merge commit following this handoff review
**Files allowed:** all files under `frontend/`; no other directories

### 11.1 Included scope

- shadcn/ui initialisation against the existing Tailwind theme
- `frontend/components.json`
- Installation of **only** the shadcn/ui components required by WP-3.1:
  - `Button`
  - `Card`
  - `Skeleton`
  - `Alert`
  - (any additional component introduced must be justified in the PR)
- Replace placeholder `App.tsx` with a minimal `react-router-dom` v6
  setup (`BrowserRouter`, root route with `Outlet`, catch-all 404)
- React provider tree: `QueryClientProvider` + `AuthProvider` (stub, WP-3.2 fills)
- `frontend/src/lib/api.ts` — minimal axios instance (proxy already in place)
- `frontend/src/lib/utils.ts` — shadcn/ui `cn` helper
- `frontend/src/index.css` — extend with shadcn/ui CSS variables
- Minimal Playwright skeleton:
  - `frontend/e2e/playwright.config.ts`
  - `frontend/e2e/example.spec.ts` — one trivial passing assertion
  - `@playwright/test` added to `devDependencies`
- Smoke test `frontend/src/App.test.tsx` asserting router renders without error
- Update `frontend/package.json` scripts: `test:e2e`, `test:e2e:ui`

### 11.2 Excluded from WP-3.1

- Login screen (WP-3.2)
- Auth route guards (WP-3.2)
- Sidebar / App shell (WP-3.3)
- Dashboard (WP-3.4)
- Risk list / detail (WP-3.5 / WP-3.6)
- Zustand or any additional state library (A-3)
- Any backend changes
- Full shadcn/ui catalogue (A-7)
- AT-005 contract test (WP-3.8)
- Golden Scenario Playwright test (WP-3.9)
- New npm dependencies outside: shadcn/ui component files, `@playwright/test`,
  and Tailwind plugins strictly required by the chosen components

### 11.3 WP-3.1 gates

All must pass before PR merge:

- `npm run lint` — zero warnings
- `npm run type-check` — zero errors
- `npm test` — Vitest smoke tests green
- `npm run build` — production build succeeds
- `npm run test:e2e` — Playwright trivial spec passes

Backend gates still apply (unchanged):

- `make test` — 709+ backend tests still pass (no regressions; WP-3.1
  makes no backend changes but a regression in tooling must be caught)
- `make lint` — backend lint still clean

### 11.4 WP-3.1 expected files (sketch; exact names finalised at implementation)

```
frontend/
├── components.json                                  (new)
├── e2e/
│   ├── playwright.config.ts                         (new)
│   └── example.spec.ts                              (new)
├── package.json                                     (updated)
├── package-lock.json                                (updated)
├── src/
│   ├── App.tsx                                      (replaced — router)
│   ├── App.test.tsx                                 (new — smoke)
│   ├── main.tsx                                     (updated — providers)
│   ├── index.css                                    (updated — shadcn CSS vars)
│   ├── components/ui/
│   │   ├── button.tsx                               (shadcn/ui)
│   │   ├── card.tsx                                 (shadcn/ui)
│   │   ├── skeleton.tsx                             (shadcn/ui)
│   │   └── alert.tsx                                (shadcn/ui)
│   ├── contexts/
│   │   └── auth.context.tsx                         (new — stub)
│   ├── lib/
│   │   ├── api.ts                                   (new)
│   │   └── utils.ts                                 (new — cn)
│   └── routes/
│       ├── root.tsx                                  (new)
│       └── not-found.tsx                             (new)
```

### 11.5 Files that MUST NOT change in WP-3.1

- Every file under `backend/`
- Every file under `seed/`
- Every file under `forgemind_project_source_of_truth/`
- Every file under `infra/`
- `docker-compose.yml`, `docker-compose.dev.yml`
- `Makefile`
- `.github/`
- `docs/planning/phase_3_planning_handoff.md`
- `HERMES.md`

---

## 12. Definition of Done for Phase 3 (final)

Phase 3 is complete when all of the following hold:

- [ ] Login works with all 5 DEC-028 demo accounts (AT-002 UI evidence)
- [ ] Invalid credentials show controlled error state
- [ ] Post-login, role-aware sidebar (UX only, §5.4) renders correctly
- [ ] Dashboard renders real backend data: active plan, risk counts, system status
- [ ] Dashboard placeholders ("Unavailable — Phase N") render honestly (A-1 / A-4)
- [ ] "Estimated time saved" reads "Metric available in Phase 5" (A-4)
- [ ] Sources and AI Recommendation panels read "Unavailable in current release" (A-2)
- [ ] Supply Risk list shows RISK-001/002/003 from backend response
- [ ] No hard-coded Golden Scenario values in any UI source (AT-005 / §5.6)
- [ ] Client-side filters work: severity, component code (§5.1)
- [ ] Risk detail composed from existing read endpoints (§5.2)
- [ ] No persisted `/risks/{risk_id}` resource introduced
- [ ] Placeholder panels make no network calls (§5.3)
- [ ] Front-end nav hiding documented only as UX, never as security (§5.4)
- [ ] Loading, empty, error states present on every data view (WP-3.7)
- [ ] All frontend unit + component tests pass
- [ ] E2E Golden Scenario Playwright test passes (WP-3.9)
- [ ] `npm run lint` — zero warnings
- [ ] `npm run type-check` — zero errors
- [ ] `npm test` — Vitest green
- [ ] `npm run build` — zero errors
- [ ] `npm run test:e2e` — Playwright green
- [ ] `make test` — backend tests still ≥ 709; 0 regressions
- [ ] `make lint` — backend lint still clean
- [ ] No secrets in frontend source
- [ ] Minimum supported viewport 1024px; tablet usable (A-5)
- [ ] 9 individual PRs merged to main, one per WP (§9.2)

Phase 3 is **NOT** complete when:

- any dashboard widget displays mock numbers
- any risk detail value is hard-coded
- a rule-based hint is rendered inside the panel labelled "AI Recommendation"
- RAG sources panel is rendered with real content
- approval/audit/workflow/model-status screens exist
- front-end nav hiding is documented or enforced as authorization
- any placeholder issues a network call to a nonexistent endpoint
- any single combined `feature/phase-3-core-ui` branch holds multiple WPs

---

## 13. Consistency check against authoritative sources

- ✓ HERMES.md execution-safety policy — respected
- ✓ `01_PRODUCT_AND_MVP_SCOPE.md` — 4 of 8 SoT screens in Phase 3;
  the other 4 deferred correctly to their phases
- ✓ `02_SYSTEM_BEHAVIOR_AND_DATA.md` — no LLM in Phase 3;
  deterministic values never hard-coded; AT-005 preserved
- ✓ `03_DEFINITION_OF_DONE.md` — Gate A (product completeness: no empty
  main buttons, real data, no hard-coded values), Gate B (engineering
  quality: tests, lint, types, no secrets), Gate F (portfolio: deferred
  to Phase 8)
- ✓ `04_ACCEPTANCE_TESTS.md` — AT-002 (login UI), AT-004 (risk engine
  visible in UI), AT-005 (seed change → UI change) all exercised in Phase 3
- ✓ `05_DEPLOYMENT_AND_DEMO.md` — public deployment is Phase 7, not Phase 3
- ✓ `07_ROADMAP.md` — Phase 3 deliverables + exit criteria satisfied
- ✓ `08_DECISION_LOG.md` — DEC-009 (roles), DEC-015 (state), DEC-017 (shadcn/ui),
  DEC-024 (correlation ID), DEC-028 (demo accounts), DEC-029 (Phase 1 auth deferral →
  now fulfilled in Phase 3 via AT-002 full UI evidence) all respected
- ✓ `docs/planning/phase_2_work_package_plan.md` — Phase 2 exit evidence stable;
  no Phase 3 change to Phase 2 APIs or seed data
- ✓ `docs/planning/requirements_traceability_matrix.md` — FR-01 (login),
  FR-04 (deterministic), FR-10 (Dashboard real data) all verifiable via Phase 3 UI

---

## 14. Remaining ambiguities

**None.** All eight ambiguities have been resolved by Product Owner decisions.
No further clarification requests are required to execute WP-3.1.

---

## 15. Next single Product Owner action

The planning document has been updated with the approved decisions.

Once the review diff has been inspected by the Product Owner, the next
single action is to approve creation of the first feature branch:

```
feature/phase-3-wp-3-1-frontend-scaffold
```

branching from `main` at the HEAD existing at that moment.

After branch creation, WP-3.1 will be implemented, verified, and
submitted as an individual PR for Product Owner review before merge.

---

## 16. Verdict

**READY TO COMMIT PLANNING**

The planning document is self-consistent, conforms to all 8 approved
Product Owner decisions, conforms to HERMES.md and Source of Truth,
and contains no remaining ambiguities blocking WP-3.1.

---

**END OF PHASE 3 PLANNING HANDOFF**
