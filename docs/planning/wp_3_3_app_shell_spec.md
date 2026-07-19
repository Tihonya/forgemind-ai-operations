# WP-3.3 Specification — App Shell and Role-Aware Navigation

**Status:** APPROVED FOR IMPLEMENTATION
**Work Package:** WP-3.3
**Phase:** 3 (Core UI)
**Base:** main at a3c7e1e6ce3fe6cdbbc8aa9961d87ddd0670515b
**Branch:** feature/phase-3-wp-3-3-app-shell
**Depends on:** WP-3.1, WP-3.2 (both merged)

---

## 1. Objective

Deliver the authenticated application shell with role-aware navigation sidebar, header, breadcrumbs, user identity display, and logout functionality. Establish the persistent layout foundation for all subsequent Phase 3 screens.

---

## 2. Canonical Role-Navigation Matrix

| Module | Phase | Visible to Roles |
|--------|-------|------------------|
| Dashboard | 3 | ALL authenticated roles |
| Supply Risk Analysis | 3 | production_manager, procurement_specialist, platform_admin |
| Knowledge Sources | 4 | ai_administrator, platform_admin |
| Workflow Runs | 5 | production_manager, procurement_specialist, ai_administrator, platform_admin |
| Approval Center | 6 | production_manager, procurement_specialist, platform_admin |
| Audit Log | 6 | auditor, platform_admin |
| Admin / Model Status | 7 | ai_administrator, platform_admin |

### Matrix Rules

- Unknown or missing role: Dashboard only
- Multiple roles: deduplicated union
- Role-aware visibility is UX-only, NOT an authorization boundary
- Backend authorization remains authoritative
- No frontend 401/403 handling in this WP

---

## 3. In-Scope Deliverables

### 3.1 Application Shell Components

- **AuthenticatedLayout**: wraps protected routes with persistent chrome
- **Sidebar**: role-aware navigation with active state indication
- **Header**: breadcrumb/current page, user identity, logout control
- **Navigation logic**: role-matrix-driven item visibility
- **Route integration**: active-routes render inside persistent shell

### 3.2 Active Routes

- `/` — Dashboard foundation (empty placeholder, WP-3.4 work)
- `/supply-risk` — Supply Risk Analysis foundation (empty placeholder, WP-3.5 work)

### 3.3 Future Module Navigation

- Visible only per role matrix
- Disabled state (visually distinct, no hover/active styling)
- Labeled with "(Phase N)" suffix
- No route transition on click
- No API calls

### 3.4 Visual Design Direction

**Industrial operations workspace aesthetic:**
- Dark steel background (bg-steel-900 for sidebar/header)
- Subtle borders (border-steel-700)
- Functional spacing
- Professional B2B appearance
- Restrained, functional, industrial workspace — not decoration
- No cyberpunk, no gradients, no excessive animation
- Usable at viewport width 1024px and above

**Typography:**
- White/off-white for primary text (text-white, text-steel-100)
- Muted steel for secondary text (text-steel-400, text-steel-500)
- Semantic colors only for status (severity badge red/amber/blue)

**Active navigation:**
- Background shift (bg-steel-800 for active item)
- Left border accent (border-l-2 border-primary)
- White text (text-white)

**Inactive navigation:**
- Muted text (text-steel-400)
- Hover state: subtle background shift (hover:bg-steel-800/50)

### 3.5 shadcn/ui Component Installation

- `separator` (for layout sectioning)
- `tooltip` (for disabled navigation items with phase info)

No additional shadcn/ui components.

---

## 4. Explicit Out-of-Scope

- Dashboard widgets or metrics (WP-3.4)
- Supply Risk list/detail content (WP-3.5, WP-3.6)
- Any backend endpoints or API calls (§5.5)
- Role-protected business routes (backend authorization only)
- Golden Scenario data or hardcoded values (§5.6)
- WP-3.4+ work
- Mobile drawer navigation (Post-MVP)
- Global state libraries beyond TanStack Query + Context (A-3)
- Placeholder panels issuing network calls (§5.3)
- Full shadcn/ui catalogue (A-7)

---

## 5. Files Allowed to Change

```
docs/planning/wp_3_3_app_shell_spec.md          (new)
frontend/package.json                            (updated — dependency additions if any)
frontend/package-lock.json                       (updated)
frontend/components.json                         (no change — shadcn config)
frontend/src/
├── components/
│   ├── layout/
│   │   ├── AuthenticatedLayout.tsx              (new)
│   │   ├── Sidebar.tsx                          (new)
│   │   ├── Header.tsx                           (new)
│   │   └── navigation/
│   │       ├── navigation-config.ts             (new — role matrix)
│   │       ├── NavigationItem.tsx               (new)
│   │       └── useNavigationPermissions.ts      (new — hook)
│   └── ui/
│       ├── separator.tsx                        (new — shadcn)
│       └── tooltip.tsx                          (new — shadcn)
├── routes/
│   ├── dashboard.tsx                            (new — empty foundation)
│   └── supply-risk.tsx                          (new — empty foundation)
└── App.tsx                                      (updated — route structure)

frontend/src/components/layout/__tests__/        (new)
├── AuthenticatedLayout.test.tsx
├── Sidebar.test.tsx
├── Header.test.tsx
└── navigation/
    ├── NavigationItem.test.tsx
    └── useNavigationPermissions.test.tsx
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
- `frontend/src/contexts/auth.context.tsx` (WP-3.2 boundary)
- `frontend/src/routes/protected.tsx` (WP-3.2 boundary)
- `frontend/src/routes/login.tsx` (WP-3.2 boundary)
- `frontend/src/lib/auth-api.ts` (WP-3.2 boundary)
- `frontend/src/lib/storage.ts` (WP-3.2 boundary)

---

## 7. Test Requirements

### 7.1 Navigation Permission Tests

- [ ] Exact navigation item set for every canonical role
- [ ] platform_admin sees full navigation
- [ ] Unknown/missing role falls back to Dashboard only
- [ ] Multi-role union without duplicates
- [ ] Disabled future-module behavior (no route transition, no API call)

### 7.2 UI Integration Tests

- [ ] Active navigation state (current route highlighted)
- [ ] User identity display (correct name/role from auth context)
- [ ] Logout integration (calls auth.logout, clears state)
- [ ] Route rendering inside persistent shell (sidebar/header persist across navigation)

### 7.3 Regression Coverage

- [ ] WP-3.2 auth routing regression: protected routes still redirect to /login when unauthenticated
- [ ] WP-3.2 auth routing regression: /login not accessible when authenticated

---

## 8. Test Gates

All must pass before PR submission:

- [ ] `npm run lint` — zero warnings
- [ ] `npm run type-check` — zero errors
- [ ] `npm test` — Vitest green (new tests included)
- [ ] `npm run build` — zero errors
- [ ] `npm run test:e2e` — Playwright trivial spec still green
- [ ] `make test` — backend ≥ 709 tests, zero regressions
- [ ] `make lint` — backend lint still clean

---

## 9. Implementation Sequence

1. Create spec document (this file)
2. Create and checkout branch
3. Install shadcn/ui separator and tooltip
4. Implement navigation config and role-matrix hook
5. Implement Sidebar, Header, AuthenticatedLayout
6. Update App.tsx route structure
7. Create empty dashboard.tsx and supply-risk.tsx placeholders
8. Write unit tests for navigation logic
9. Write integration tests for layout components
10. Run all test gates
11. Perform pre-push focused review
12. Stage files explicitly, create single WP-3.3 commit
13. Stop before push

---

## 10. Acceptance Criteria

- [ ] After login, authenticated layout shell renders
- [ ] Sidebar shows exactly the items allowed for signed-in role
- [ ] Future modules visible per role matrix, disabled, labeled "(Phase N)"
- [ ] Dashboard and Supply Risk routes render inside persistent shell
- [ ] Header shows current page (breadcrumb), user identity, logout
- [ ] Logout clears auth state and redirects to /login
- [ ] Navigation hiding is UX-only; backend remains authoritative (§5.4)
- [ ] Minimum viewport 1024px usable (A-5)
- [ ] All test gates pass
- [ ] No unauthorized artifacts in working tree
- [ ] Single intentional WP-3.3 commit
- [ ] No WP-3.4+ work

---

## 11. Architecture Decision Records Respected

- DEC-015: State management — TanStack Query + Context only
- DEC-017: shadcn/ui over existing Tailwind theme
- DEC-028: Five canonical demo roles
- DEC-009: RBAC (four roles + platform_admin)

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

**END OF WP-3.3 SPECIFICATION**
