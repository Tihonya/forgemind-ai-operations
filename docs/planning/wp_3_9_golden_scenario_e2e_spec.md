# WP-3.9 Specification — Golden Scenario E2E

**Status:** APPROVED FOR IMPLEMENTATION
**Work Package:** WP-3.9
**Phase:** 3 (Core UI)
**Base:** main at bfcb8d26cf0b68fa04ea1721c85638dfe4f1023d
**Branch:** feature/phase-3-wp-3-9-golden-scenario-e2e
**Depends on:** WP-3.3, WP-3.4, WP-3.5, WP-3.6, WP-3.7, WP-3.8 (all merged)

---

## 1. Objective

Implement one deterministic Playwright Golden Scenario that proves the real browser → frontend → backend → PostgreSQL vertical slice using the seeded Golden Dataset.

This WP delivers **end-to-end browser automation** covering the complete user flow: authentication, dashboard verification, supply risk navigation, risk detail inspection, and logout.

---

## 2. Acceptance Test Coverage (Verified from Source of Truth)

| Acceptance Test | Phase | Evidence Mechanism |
|----------------|-------|-------------------|
| **AT-001** | Phase 1 + Phase 7 | Docker services healthy, migrations run, seed available |
| **AT-002** | Phase 1 | Login as manager.demo, navigate to Dashboard |
| **AT-003** | Phase 2 | Golden Dataset seeded, PLAN-2026-W31 active |
| **AT-004** | Phase 2 | Risk engine returns exact 3 risks with quantities |
| **AT-005** | Phase 2 + Phase 3 | UI displays real backend data (no mocks) |

**Not covered:**
- AT-014 (public HTTPS) — requires live deployment, not localhost
- AT-006, AT-007, AT-008, AT-009, AT-010, AT-011, AT-012, AT-013, AT-015 — Phase 4/5/6/7

---

## 3. Architecture (Real Vertical Slice)

**Required components:**
- Real React frontend (no mocks)
- Real FastAPI backend (no mocks)
- Real PostgreSQL with Golden Dataset seeded
- Real browser (Chromium via Playwright)

**Prohibited:**
- Playwright route mocks
- API mocks
- Hidden test-only production behavior
- test.skip or conditional success when infrastructure unavailable
- Graceful degradation for missing services

**Failure semantics:**
- Backend unavailable → FAIL
- Frontend unavailable → FAIL
- Authentication failure → FAIL
- Seed failure → FAIL
- Golden Dataset mismatch → FAIL
- Browser console error → FAIL (except proven harmless noise)
- Unexpected failed API response → FAIL

---

## 4. Demo Credentials (Canonical)

**Username:** manager.demo
**Password:** ManagerPass123!
**Role:** PRODUCTION_MANAGER

**Source:** backend/app/seed/generator/auth_dataset.py

---

## 5. Golden Dataset (Canonical from 02_SYSTEM_BEHAVIOR_AND_DATA.md)

**Production Plan:** PLAN-2026-W31

**Expected Risks:**

| Risk ID | Component | Required | Available | Confirmed Early | Confirmed Late | Shortage | Severity | Work Order |
|---------|-----------|----------|-----------|-----------------|----------------|----------|----------|------------|
| RISK-001 | CTRL-X4 | 20 | 12 | 0 | 0 | 8 | CRITICAL | WO-2026-0142 |
| RISK-002 | MOTOR-M2 | 16 | 10 | 0 | 0 | 6 | HIGH | WO-2026-0150 |
| RISK-003 | SENSOR-L9 | 12 | 7 | 0 | 0 | 5 | MEDIUM | WO-2026-0156 |

**Order:** CRITICAL → HIGH → MEDIUM (severity descending)

---

## 6. Service Orchestration

### 6.1 URL Configuration

**Environment variables:**
```bash
PLAYWRIGHT_BASE_URL=http://127.0.0.1:4173   # Frontend (Vite preview)
API_BASE_URL=http://127.0.0.1:8000          # Backend (FastAPI)
```

**Do not overload one BASE_URL for both services.**

### 6.2 Service Startup

**Docker Compose owns:**
- Backend (FastAPI)
- PostgreSQL
- Redis (if required)
- Worker (if required)

**Playwright webServer owns:**
- Frontend (vite preview on port 4173)

**Local development workflow:**
1. Start Docker services: `docker compose up -d`
2. Wait for backend health: `curl -f http://127.0.0.1:8000/health`
3. Seed database: `docker compose exec -T backend bash -c "cd /app/backend && python -m app.seed.generator.main"`
4. Build frontend: `cd frontend && npm run build`
5. Run Playwright: `cd frontend && npm run test:e2e`

**CI workflow:**
1. Start Docker services
2. Wait for health with timeout
3. Seed database
4. Verify active plan exists via API
5. Build frontend
6. Run Playwright
7. Failure at any step → FAIL (no skip)

### 6.3 Seed Safety

**Canonical seed command:**
```bash
docker compose exec -T backend bash -c \
  "cd /app/backend && python -m app.seed.generator.main"
```

**Safety guarantees:**
- Seed creates Golden Dataset on clean database
- Seed is idempotent (safe to run multiple times)
- Seed does NOT destroy existing data
- Seed does NOT require docker compose down -v
- Seed does NOT modify production credentials
- Clear documentation: "Seed replaces canonical demo/business data"

**Do not:**
- Fix make seed in this WP
- Destroy volumes
- Use docker compose down -v
- Reset unknown shared environments

---

## 7. Golden Scenario Browser Flow

### 7.1 Step 1: Open Frontend
- Navigate to PLAYWRIGHT_BASE_URL
- Verify unauthenticated user sees login page
- Verify page title contains "ForgeMind"

### 7.2 Step 2: Authentication
- Fill username: manager.demo
- Fill password: ManagerPass123!
- Submit login form
- Verify successful navigation to Dashboard (/)
- Verify Dashboard heading "Executive Dashboard" visible

### 7.3 Step 3: Dashboard Verification
- Verify active plan banner shows "PLAN-2026-W31"
- Verify risk summary widget shows:
  - Total risks: 3
  - CRITICAL count: 1
  - HIGH count: 1
  - MEDIUM count: 1
- Verify no console errors
- Verify no failed API responses

### 7.4 Step 4: Navigate to Supply Risk Analysis
- Click "Supply Risk Analysis" navigation item in sidebar
- Verify route changes to /supply-risk
- Verify page heading "Supply Risk Analysis"
- Verify risk list displays 3 rows

### 7.5 Step 5: Supply Risk List Verification
- Verify exact risk order (severity descending):
  1. RISK-001 / CTRL-X4 / shortage 8 / CRITICAL
  2. RISK-002 / MOTOR-M2 / shortage 6 / HIGH
  3. RISK-003 / SENSOR-L9 / shortage 5 / MEDIUM
- Verify severity badges render correctly
- Verify numeric values displayed (format: integer or 2 decimals, not necessarily 4)
- Verify "View" link visible for each risk

### 7.6 Step 6: Risk Detail Navigation
- Click "View" link for RISK-001
- Verify route changes to /supply-risk/RISK-001
- Verify breadcrumb renders: "Supply Risk Analysis > RISK-001"
- Verify heading shows RISK-001

### 7.7 Step 7: Risk Detail Verification
- Verify CTRL-X4 context visible (component code, name)
- Verify evidence panel shows exact quantities:
  - Required: 20 (or 20.00)
  - Available: 12 (or 12.00)
  - Confirmed early: 0 (or 0.00)
  - Confirmed late: 0 (or 0.00)
  - Shortage: 8 (or 8.00)
- Verify work order context: WO-2026-0142
- Verify plan context: PLAN-2026-W31
- Verify inventory panel renders (not necessarily content)
- Verify incoming supply panel renders (not necessarily content)
- Verify no console errors
- Verify no failed API responses

### 7.8 Step 8: Navigate Back
- Click breadcrumb link "Supply Risk Analysis"
- Verify route returns to /supply-risk
- Verify 3 risk rows still visible

### 7.9 Step 9: Logout
- Click logout button/link in sidebar or header
- Verify navigation to /login
- Verify protected content no longer accessible
- Attempt to navigate to /supply-risk directly
- Verify redirect back to /login

### 7.10 Step 10: Console and Network Validation
- Collect all console errors from entire scenario
- Collect all page errors
- Collect all failed API responses (4xx, 5xx)
- Fail if:
  - Any console error not on allowlist
  - Any page error
  - Any unexpected failed API response

---

## 8. Test Design Principles

### 8.1 File Structure
```
frontend/e2e/
├── golden-scenario.spec.ts       # Main E2E test (single spec)
├── example.spec.ts               # Existing trivial smoke (preserve)
└── (no premature abstractions)
```

### 8.2 Locator Strategy
**Prefer accessible locators:**
- `getByRole('heading', { name: /Executive Dashboard/i })`
- `getByRole('link', { name: /Supply Risk Analysis/i })`
- `getByRole('button', { name: /Sign in/i })`
- `getByLabel('Username')`
- `getByLabel('Password')`
- `getByText('PLAN-2026-W31')`
- `getByText('RISK-001')`

**Avoid:**
- Brittle CSS selectors (.class-name)
- Arbitrary timeouts (waitForTimeout)
- Unnecessary waits for selectors

### 8.3 Wait Strategy
**Use deterministic waits:**
- `waitForURL()` for navigation
- `waitForResponse()` for API completion
- `expect().toBeVisible()` for UI state
- `page.waitForLoadState('networkidle')` for stability

**Do not use:**
- `waitForTimeout()` as synchronization
- Hard-coded delays

---

## 9. Console and Network Monitoring

### 9.1 Console Error Collection
```typescript
const consoleErrors: string[] = [];
page.on('console', msg => {
  if (msg.type() === 'error') {
    consoleErrors.push(msg.text());
  }
});
```

### 9.2 Page Error Collection
```typescript
const pageErrors: Error[] = [];
page.on('pageerror', err => {
  pageErrors.push(err);
});
```

### 9.3 Failed Response Collection
```typescript
const failedResponses: string[] = [];
page.on('response', response => {
  if (response.status() >= 400) {
    failedResponses.push(`${response.status()} ${response.url()}`);
  }
});
```

### 9.4 Allowlist (Proven Harmless Browser Noise)

**Allow only if explicitly documented with rationale:**
```typescript
const ALLOWED_CONSOLE_ERRORS = [
  // React Router v7 migration warning — does not affect functionality
  // Will be addressed in future React Router upgrade
  'React Router v7 will require use of future flags',
];
```

**Validate each allowlist entry:**
- Must be a known browser/framework warning
- Must not affect functionality
- Must have rationale in comments
- Must be reviewed before adding

---

## 10. CI Integration

### 10.1 Workflow Trigger
**Existing workflow:** .github/workflows/ci-e2e.yml
**Current issue:** expects tests/e2e directory (placeholder from Phase 0)
**Required change:** update to use frontend/e2e

**Minimal justified changes:**
- Change working-directory from `./tests/e2e` to `./frontend`
- Change BASE_URL to `http://localhost:80` (Caddy proxy) or configure separately
- Add seed step before Playwright
- Add API verification step after seed

### 10.2 Path Filtering
**Existing logic:** run if `tests/e2e` changes
**Required logic:** run if:
- `frontend/e2e/**` changes
- `frontend/src/**` changes
- `backend/**` changes
- `seed/**` changes

### 10.3 Service Startup in CI
```yaml
- name: Start services
  run: docker compose up -d

- name: Wait for backend health
  run: |
    timeout 60 bash -c 'until curl -f http://localhost:8000/health; do sleep 2; done'

- name: Seed database
  run: |
    docker compose exec -T backend bash -c \
      "cd /app/backend && python -m app.seed.generator.main"

- name: Verify Golden Dataset
  run: |
    curl -f http://localhost:8000/api/v1/production-plans/PLAN-2026-W31/risks \
      -H "Authorization: Bearer $(curl -s -X POST http://localhost:8000/auth/login \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        -d 'username=manager.demo&password=ManagerPass123!' | jq -r .access_token)" \
      | jq -e '.[] | select(.risk_id == "RISK-001")' > /dev/null
```

---

## 11. Production Changes

### 11.1 Explicitly Prohibited
- UI redesign
- Backend endpoint changes
- Business logic changes
- Authentication architecture changes
- Deferred-finding fixes (horizontal scrollbar, widget retry, make seed, etc.)

### 11.2 Genuine Defect Discovery
**If E2E exposes a real production defect:**
1. Stop implementation
2. Document the defect with:
   - Exact reproduction steps
   - Expected behavior
   - Actual behavior
   - Minimal fix required
3. Report defect to Product Owner
4. Obtain explicit approval before any production code edit
5. Do not silently fix

---

## 12. Test Gates

All must pass under Node 22.18.0:

```bash
npm run lint
npm run type-check
npm test
npm run build
npm run test:e2e          # Real seeded Golden Scenario
make lint
```

**Additional verification:**
- Docker services used (list)
- Seed command result (success/failure)
- Playwright test count (1 test, multiple assertions)
- Browser console findings (errors, warnings)
- Network findings (failed responses)

---

## 13. Explicit Out-of-Scope

- AT-014 public HTTPS coverage (requires live deployment)
- Phase 4/5/6/7 acceptance tests
- UI redesign or visual polish
- Backend endpoint changes
- Business logic changes
- Deferred-finding fixes:
  - Horizontal scrollbar ergonomics at 1024px
  - View may require horizontal scrolling
  - Widget retry architecture
  - Broken make seed target
  - Global 401/403 hardening
  - React Router v7 warnings
  - Query data cannot be undefined test warning
- Hidden E2E mocks
- Weakening AT-005 tests
- Commit, push, PR, merge

---

## 14. Files Allowed to Change

```
docs/planning/wp_3_9_golden_scenario_e2e_spec.md           (new)
frontend/e2e/golden-scenario.spec.ts                       (new)
.github/workflows/ci-e2e.yml                               (updated — fix paths + add seed)
frontend/playwright.config.ts                              (updated — env var support)
```

**Files that MUST NOT change:**
- All production `frontend/src/**/*.ts(x)` (unless genuine defect discovered and approved)
- All production `backend/**/*.py`
- All files under `seed/`
- All files under `forgemind_project_source_of_truth/`
- `docker-compose.yml`, `docker-compose.dev.yml`
- `Makefile`
- `HERMES.md`
- `docs/planning/phase_3_planning_handoff.md`

---

## 15. Formatting Rule

**Assert the value as displayed by the UI.**

- If UI shows "8" → assert "8"
- If UI shows "8.00" → assert "8.00"
- If UI shows "8.0000" → assert "8.0000"
- Do not require four decimal places if production UI intentionally formats to fewer
- Do not modify production formatting to match API DecimalStr4

**Current production behavior:** Verify from WP-3.5/3.6 implementation. Likely 2 decimal places or integer display.

---

## 16. Implementation Sequence

1. Create spec document (this file)
2. Create and checkout branch
3. Inspect existing Playwright and CI behavior
4. Implement golden-scenario.spec.ts
5. Update playwright.config.ts for env var support
6. Update .github/workflows/ci-e2e.yml
7. Start Docker services locally
8. Seed database
9. Verify active plan and risks via API
10. Build frontend
11. Run Playwright locally
12. Confirm no mocks used
13. Run canonical gates (Node 22.18.0)
14. Perform focused pre-commit review
15. Stage files explicitly
16. Create single commit: `test(e2e): add Golden Scenario browser flow`
17. Stop before push

---

## 17. Acceptance Criteria

- [ ] Branch created from approved base
- [ ] Specification document created
- [ ] Golden Scenario E2E test implemented
- [ ] Test covers AT-001, AT-002, AT-003, AT-004, AT-005 evidence
- [ ] No Playwright route mocks
- [ ] No API mocks
- [ ] Real browser → frontend → backend → PostgreSQL flow
- [ ] Credentials: manager.demo / ManagerPass123!
- [ ] Golden Scenario asserts exact 3 risks in correct order
- [ ] Risk detail page asserts exact quantities
- [ ] Console and network monitoring implemented
- [ ] No test.skip or conditional success
- [ ] CI workflow updated with seed step
- [ ] All gates pass under Node 22.18.0
- [ ] No production code changes (unless genuine defect discovered and approved)
- [ ] Single commit with conventional message
- [ ] Clean working tree after
- [ ] No push, no PR, no merge

---

## 18. Verification Commands

```bash
# Service startup
docker compose up -d
sleep 5
curl -f http://127.0.0.1:8000/health

# Seed
docker compose exec -T backend bash -c \
  "cd /app/backend && python -m app.seed.generator.main"

# Verify seed
API_TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=manager.demo&password=ManagerPass123!' | jq -r .access_token)

curl -s http://127.0.0.1:8000/api/v1/production-plans/PLAN-2026-W31/risks \
  -H "Authorization: Bearer $API_TOKEN" | jq '.[].risk_id'

# Frontend build
. "$NVM_DIR/nvm.sh" && nvm use 22
cd frontend
npm ci
npm run build

# Playwright
npm run test:e2e

# Gates
npm run lint
npm run type-check
npm test
make lint
```

---

## 19. Expected Deliverables

**Files:**
- `frontend/e2e/golden-scenario.spec.ts` — single Playwright test
- Updated `frontend/playwright.config.ts` — env var support
- Updated `.github/workflows/ci-e2e.yml` — seed step, path fixes

**Evidence:**
- Local Playwright run: 1 passed, 0 failed
- Console errors: 0 (or only allowlisted)
- Failed API responses: 0
- All gates: green

---

## 20. Risks

**Risk 1: Seed command fails in container**
- Known issue: make seed has broken working directory
- Resolution: use explicit `cd /app/backend` workaround
- Do not fix make seed in this WP

**Risk 2: Console errors from React/DOM**
- Potential for harmless browser warnings
- Resolution: carefully review each error, add to allowlist only if proven harmless
- Document rationale for each allowlist entry

**Risk 3: Numeric formatting mismatch**
- API returns DecimalStr4, UI may format differently
- Resolution: assert as displayed, do not require 4 decimals
- Verify from WP-3.5/3.6 implementation

**Risk 4: CI environment differences**
- Local vs CI may have timing differences
- Resolution: use deterministic waits, not timeouts
- Add retry logic in CI workflow if needed (but not in test itself)

---

**END OF WP-3.9 SPECIFICATION**
