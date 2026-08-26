/**
 * WP-3.9 Golden Scenario E2E Test
 *
 * Validates the complete user flow through the ForgeMind application:
 * 1. Authentication with manager.demo credentials
 * 2. Dashboard displays active plan and risk summary
 * 3. Supply Risk Analysis shows 3 risks in correct order
 * 4. Risk detail displays complete evidence and context
 * 5. Logout and access control verification
 *
 * Acceptance Tests Covered:
 * - AT-002: Demo authentication
 * - AT-003: Golden Dataset integrity (PLAN-2026-W31 active)
 * - AT-004: Deterministic risk calculation (3 risks with exact values)
 * - AT-005: No hidden UI mocks (real backend data displayed)
 */

import { test, expect } from '@playwright/test';

// Console error allowlist - only proven harmless browser warnings
const ALLOWED_CONSOLE_PATTERNS = [
  // React Router v7 migration warning - framework-level deprecation notice
  /React Router will require future\.*/,
  // Vite HMR logs in development
  /\[vite\] connected\./,
  /\[vite\] hot updated/,
];

test('Golden Scenario - Complete user flow with seeded data', async ({ page }) => {
  // Track console errors for final validation
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      // Only record errors not in allowlist
      if (!ALLOWED_CONSOLE_PATTERNS.some((pattern) => pattern.test(text))) {
        consoleErrors.push(text);
      }
    }
  });

  // Track page errors (uncaught exceptions)
  const pageErrors: string[] = [];
  page.on('pageerror', (err) => {
    pageErrors.push(err.message);
  });

  // Track failed API responses (exclude 401/403 — expected auth-denied responses
  // during logout and access-control verification flows)
  const failedResponses: string[] = [];
  page.on('response', (response) => {
    const status = response.status();
    if (status >= 400 && status !== 401 && status !== 403) {
      failedResponses.push(`${status} ${response.url()}`);
    }
  });

  // ────────────────────────────────────────────────────────────
  // Step 1: Verify unauthenticated user sees login page
  // ────────────────────────────────────────────────────────────
  await page.goto('/');
  await expect(page).toHaveTitle(/ForgeMind/);
  await expect(page.getByRole('heading', { name: 'Увійти', level: 2 })).toBeVisible();
  await expect(page.getByText(/Supply Risk Intelligence/i)).toBeVisible();

  // Verify login form elements (data-testid selectors: stable with the
  // demo-account UX; broad label regex collides with the visibility toggle)
  await expect(page.getByTestId('login-username')).toBeVisible();
  await expect(page.getByTestId('login-password')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Увійти' })).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 2: Authenticate as manager.demo
  // ────────────────────────────────────────────────────────────
  await page.getByTestId('login-username').fill('manager.demo');
  await page.getByTestId('login-password').fill('ManagerPass123!');
  await page.getByRole('button', { name: 'Увійти' }).click();

  // Wait for navigation to dashboard
  await expect(page).toHaveURL('/', { timeout: 10000 });
  // WP-UX-UA-01 pilot: Ukrainian heading by default (no saved preference)
  await expect(page.getByRole('heading', { name: /Операційний огляд/i, level: 1 })).toBeVisible();
  await expect(page.getByText('Активний план, ризики постачання та рішення за участю ШІ — в одному місці.')).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 2b: WP-UX-UA-01 locale contract (uk default, en switch, persistence)
  // ────────────────────────────────────────────────────────────

  // Ukrainian default: navigation, sign-out and role labels are localized
  await expect(page.getByTestId('nav-link-dashboard')).toContainText('Огляд');
  await expect(page.getByTestId('nav-link-supply-risk')).toContainText('Ризики постачання');
  await expect(page.getByTestId('header-logout')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'uk');

  // Switch to English: pilot scope must re-render immediately, no reload
  await page.getByTestId('locale-switch-en').click();
  await expect(page.getByRole('heading', { name: /Operations Dashboard/i, level: 1 })).toBeVisible();
  await expect(page.getByTestId('nav-link-dashboard')).toContainText('Dashboard');
  await expect(page.getByTestId('nav-link-supply-risk')).toContainText('Supply Risk Analysis');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  // The selected locale persists across reloads
  await page.reload();
  await expect(page.getByRole('heading', { name: /Operations Dashboard/i, level: 1 })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  // ────────────────────────────────────────────────────────────
  // Step 2b-R1: WP-UX-UA-01-R1 — active locale reaches formatDate at
  // real call sites (F-1 remediation regression). While ENGLISH is
  // active, the Supply Risk banner must render en-US dates — the same
  // dates that render Ukrainian when uk is active.
  // ────────────────────────────────────────────────────────────
  await page.getByTestId('nav-link-supply-risk').click();
  await expect(page).toHaveURL('/supply-risk', { timeout: 5000 });
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  // Active production plan banner: PLAN-2026-W31 period 2026-07-31 →
  // 2026-08-06. English month formatting, no Ukrainian abreviations.
  await expect(page.getByText('Jul 31, 2026 — Aug 6, 2026')).toBeVisible();
  await expect(page.getByText(/лип\. \d{4}/)).not.toBeVisible();
  await expect(page.getByText(/серп\. \d{4}/)).not.toBeVisible();

  // Persisted English survives a reload ON the format screen too.
  await page.reload();
  await expect(page).toHaveURL('/supply-risk', { timeout: 5000 });
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByTestId('locale-switch-en')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Jul 31, 2026 — Aug 6, 2026')).toBeVisible();

  // Switch back to Ukrainian on the same screen (no navigation): the
  // same mounted banner re-renders dates reactively.
  await page.getByTestId('locale-switch-uk').click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'uk');
  await expect(page.getByTestId('locale-switch-uk')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('31 лип. 2026 р. — 6 серп. 2026 р.')).toBeVisible();
  await expect(page.getByText('Jul 31, 2026 — Aug 6, 2026')).not.toBeVisible();

  // Return to the Dashboard (Ukrainian default) for the remainder of the
  // scenario — all subsequent shell assertions use Ukrainian labels
  await page.getByTestId('nav-link-dashboard').click();
  await expect(page).toHaveURL('/', { timeout: 5000 });
  await expect(page.getByRole('heading', { name: /Операційний огляд/i, level: 1 })).toBeVisible();
  await expect(page.getByTestId('nav-link-dashboard')).toContainText('Огляд');
  await expect(page.locator('html')).toHaveAttribute('lang', 'uk');

  // ────────────────────────────────────────────────────────────
  // Step 2c: Verify live WP-UX-01 Dashboard widget contract
  // ────────────────────────────────────────────────────────────
  // The canonical CI seed creates no workflow runs and no approval
  // requests, so the fresh-state Dashboard must show the truthful
  // empty-state text — not loading skeletons, not stale placeholders.
  // These assertions verify the live widget contract without creating
  // any application writes (no workflow runs, no provider calls, no
  // approval requests).

  // Latest AI Analysis widget is visible
  await expect(page.getByTestId('latest-ai-analysis-widget')).toBeVisible();
  await expect(page.getByText('Останній аналіз ШІ', { exact: true })).toBeVisible();

  // Fresh seed: no workflow runs → "No AI analysis yet" + CTA link
  await expect(page.getByTestId('latest-ai-analysis-empty')).toBeVisible();
  await expect(page.getByText('Аналізу ШІ ще немає')).toBeVisible();
  await expect(page.getByTestId('latest-ai-analysis-cta')).toBeVisible();
  await expect(page.getByTestId('latest-ai-analysis-cta')).toContainText('Переглянути ризики постачання');

  // Awaiting Decision widget is visible
  await expect(page.getByTestId('awaiting-decision-widget')).toBeVisible();
  await expect(page.getByText('Очікують рішення')).toBeVisible();

  // Fresh seed: no pending approval requests → "No decisions waiting"
  await expect(page.getByTestId('awaiting-decision-zero')).toBeVisible();
  await expect(page.getByText('Немає очікуваних рішень')).toBeVisible();

  // Stale user-facing text from removed placeholders must be absent
  await expect(page.getByText(/Unavailable/i)).not.toBeVisible();
  await expect(page.getByText(/Latest Agent Runs/i)).not.toBeVisible();
  await expect(page.getByText(/Pending Approvals/i)).not.toBeVisible();
  await expect(page.getByText(/Estimated Time Saved/i)).not.toBeVisible();
  await expect(page.getByText(/Metric available in Phase 5/i)).not.toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 3: Verify Dashboard - Active Plan and Risk Summary
  // ────────────────────────────────────────────────────────────
  // AT-003: Golden Dataset integrity - active plan PLAN-2026-W31
  // (WP-UX-UA-04: plan status is localized; machine code stays on data-code)
  await expect(page.getByTestId('plan-code')).toHaveText('PLAN-2026-W31');
  await expect(page.getByTestId('plan-status')).toHaveText('Виконується');
  await expect(page.getByTestId('plan-status')).toHaveAttribute('data-code', 'EXECUTING');

  // AT-004: Deterministic risk calculation - 3 total risks
  await expect(page.getByTestId('risk-total')).toHaveText('3');

  // Verify severity breakdown
  await expect(page.getByTestId('severity-critical-count')).toHaveText('1');
  await expect(page.getByTestId('severity-high-count')).toHaveText('1');
  await expect(page.getByTestId('severity-medium-count')).toHaveText('1');
  await expect(page.getByTestId('severity-low-count')).toHaveText('0');

  // ────────────────────────────────────────────────────────────
  // Step 4: Navigate to Supply Risk Analysis (Ukrainian nav label)
  // ────────────────────────────────────────────────────────────
  await page.getByTestId('nav-link-supply-risk').click();
  await expect(page).toHaveURL('/supply-risk', { timeout: 5000 });

  // Verify page heading
  await expect(page.getByRole('heading', { name: 'Ризики постачання', level: 1 })).toBeVisible();

  // Verify active plan banner (reuses useActivePlan hook)
  await expect(page.getByText(/PLAN-2026-W31/i)).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 5: Verify Supply Risk List - 3 risks in correct order
  // ────────────────────────────────────────────────────────────
  // AT-004: Verify exact risk data and severity ordering
  await expect(page.getByTestId('risk-list')).toBeVisible();
  await expect(page.getByTestId('risk-count')).toContainText('Показано 3 із 3 ризиків');

  // Verify RISK-001 - CTRL-X4 - CRITICAL - scoped to risk-list container
  const riskList = page.getByTestId('risk-list');
  const risk001Row = riskList.getByRole('row', { name: /RISK-001/i });
  await expect(risk001Row).toBeVisible();
  await expect(risk001Row.getByText('CTRL-X4')).toBeVisible();
  await expect(risk001Row.getByText('Критичний', { exact: true })).toBeVisible();
  await expect(risk001Row.getByRole('cell', { name: '8', exact: true })).toBeVisible(); // shortage
  await expect(risk001Row.getByRole('link', { name: 'Переглянути RISK-001' })).toBeVisible();

  // Verify RISK-002 - MOTOR-M2 - HIGH
  const risk002Row = riskList.getByRole('row', { name: /RISK-002/i });
  await expect(risk002Row).toBeVisible();
  await expect(risk002Row.getByText('MOTOR-M2')).toBeVisible();
  await expect(risk002Row.getByText('Високий', { exact: true })).toBeVisible();
  await expect(risk002Row.getByRole('cell', { name: '6', exact: true })).toBeVisible(); // shortage
  await expect(risk002Row.getByRole('link', { name: 'Переглянути RISK-002' })).toBeVisible();

  // Verify RISK-003 - SENSOR-L9 - MEDIUM
  const risk003Row = riskList.getByRole('row', { name: /RISK-003/i });
  await expect(risk003Row).toBeVisible();
  await expect(risk003Row.getByText('SENSOR-L9')).toBeVisible();
  await expect(risk003Row.getByText('Середній', { exact: true })).toBeVisible();
  await expect(risk003Row.getByRole('cell', { name: '5', exact: true })).toBeVisible(); // shortage
  await expect(risk003Row.getByRole('link', { name: 'Переглянути RISK-003' })).toBeVisible();

  // Verify severity ordering (CRITICAL first, then HIGH, then MEDIUM)
  // Get all rows in order and check their severity badges
  const rows = riskList.getByRole('row');
  const rowCount = await rows.count();
  expect(rowCount).toBe(4); // 1 header + 3 data rows

  const firstDataRow = rows.nth(1);
  const secondDataRow = rows.nth(2);
  const thirdDataRow = rows.nth(3);

  await expect(firstDataRow.getByText('Критичний', { exact: true })).toBeVisible();
  await expect(secondDataRow.getByText('Високий', { exact: true })).toBeVisible();
  await expect(thirdDataRow.getByText('Середній', { exact: true })).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 6: Navigate to RISK-001 detail
  // ────────────────────────────────────────────────────────────
  await risk001Row.getByRole('link', { name: 'Переглянути RISK-001' }).click();
  await expect(page).toHaveURL('/supply-risk/RISK-001', { timeout: 5000 });

  // Verify breadcrumb
  await expect(page.getByRole('navigation', { name: 'breadcrumb' }).getByText('Ризики постачання')).toBeVisible();
  await expect(page.getByRole('link', { name: /RISK-001/i })).toBeVisible();

  // Verify page heading
  await expect(page.getByRole('heading', { name: 'Ризик RISK-001', level: 1 })).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 7: Verify Risk Summary
  // ────────────────────────────────────────────────────────────
  // AT-004: Verify component and work order context (scoped via label→parent container)
  await expect(
    page.getByText(/^Компонент:$/).locator('xpath=..').getByText('CTRL-X4', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Критичний/i)).toBeVisible();
  await expect(
    page.getByText(/^Виробниче замовлення:$/).locator('xpath=..').getByText('WO-2026-0142'),
  ).toBeVisible();
  await expect(page.getByText('8', { exact: true }).first()).toBeVisible(); // shortage in summary

  // ────────────────────────────────────────────────────────────
  // Step 8: Verify Evidence Panel - scoped via text + parent
  // ────────────────────────────────────────────────────────────
  // AT-004: Verify deterministic calculation values.
  // Strategy: assert label visibility (scoped by page-level uniqueness of each label
  // in the Evidence & Calculation card), then navigate from label → parent → value.
  // In EvidencePanel each label/value pair shares a parent <div>, so `..` yields a
  // stable 1-step relationship. No production data-testid added.
  await expect(page.getByText(/^Докази та розрахунок$/i)).toBeVisible();

  // Required: 20  — parent <div> contains label + value as sibling children
  await expect(page.getByText(/^Потрібно$/).locator('xpath=..').getByText(/^20$/)).toBeVisible();

  // Available: 12
  await expect(page.getByText(/^Доступно$/).locator('xpath=..').getByText(/^12$/)).toBeVisible();

  // Confirmed early: 0
  await expect(page.getByText(/^Підтверджено \(достроково\)$/).locator('xpath=..').getByText(/^0$/)).toBeVisible();

  // Confirmed late: 0
  await expect(page.getByText(/^Підтверджено \(пізно\)$/).locator('xpath=..').getByText(/^0$/)).toBeVisible();

  // Shortage: 8  — layout is <span>Shortage</span> + <span>8</span> in a sibling flex row
  await expect(page.getByText(/^Дефіцит$/).locator('xpath=..').getByText(/^8$/)).toBeVisible();

  // Verify formula explanation
  await expect(page.getByText(/Дефіцит.*max.*0.*required.*available.*confirmed_early/i)).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 9: Verify Component Panel
  // ────────────────────────────────────────────────────────────
  await expect(page.getByText(/Деталі компонента/i)).toBeVisible();
  await expect(page.getByText('CTRL-X4').first()).toBeVisible();
  // Component panel should render (exact content depends on seed data)

  // ────────────────────────────────────────────────────────────
  // Step 10: Verify Inventory Panel
  // ────────────────────────────────────────────────────────────
  await expect(page.getByText(/Запаси/i)).toBeVisible();
  // Inventory panel should render (exact content depends on seed data)

  // ────────────────────────────────────────────────────────────
  // Step 11: Verify Incoming Supply Panel
  // ────────────────────────────────────────────────────────────
  // Scoped via exact CardTitle text to avoid matching the empty-state paragraph
  // that also contains "incoming supply".
  await expect(page.getByText('Вхідні постачання', { exact: true })).toBeVisible();
  // Incoming supply may be empty or have data - just verify panel renders

  // ────────────────────────────────────────────────────────────
  // Step 12: Verify Production Order Panel
  // ────────────────────────────────────────────────────────────
  await expect(page.getByText(/Виробниче замовлення/).first()).toBeVisible();
  await expect(page.getByText(/WO-2026-0142/).first()).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 13: Verify Plan Context Panel
  // ────────────────────────────────────────────────────────────
  await expect(page.getByText(/Контекст виробничого плану/).first()).toBeVisible();
  await expect(page.getByText(/PLAN-2026-W31/).first()).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 14: Navigate back to Supply Risk Analysis
  // ────────────────────────────────────────────────────────────
  // Breadcrumb uses clickable <a> tag via BreadcrumbLink
  await page.getByRole('navigation', { name: 'breadcrumb' }).getByRole('link', { name: 'Ризики постачання' }).click();
  await expect(page).toHaveURL('/supply-risk', { timeout: 5000 });

  // Verify we're back on the list page
  await expect(page.getByRole('heading', { name: 'Ризики постачання', level: 1 })).toBeVisible();
  await expect(page.getByTestId('risk-list')).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 15: Logout
  // ────────────────────────────────────────────────────────────
  // Header button has data-testid="header-logout" (aria-label localized:
  // «Вийти» in uk). WP-UX-UA-01 leaves the logout behavior unchanged.
  await page.getByTestId('header-logout').click();

  // Verify redirect to login
  await expect(page).toHaveURL('/login', { timeout: 5000 });
  await expect(page.getByRole('heading', { name: 'Увійти', level: 2 })).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Step 16: Verify access control - protected content inaccessible
  // ────────────────────────────────────────────────────────────
  await page.goto('/supply-risk');
  // Should redirect back to /login
  await expect(page).toHaveURL('/login', { timeout: 5000 });

  // Verify login page is shown
  await expect(page.getByRole('heading', { name: 'Увійти', level: 2 })).toBeVisible();

  // ────────────────────────────────────────────────────────────
  // Final validation: Console, page errors, and failed responses
  // ────────────────────────────────────────────────────────────
  // AT-005: No hidden UI mocks - verify no unexpected errors
  if (consoleErrors.length > 0) {
    console.error('Unexpected console errors:', consoleErrors);
  }
  expect(consoleErrors, 'Unexpected console errors during Golden Scenario').toEqual([]);

  if (pageErrors.length > 0) {
    console.error('Unexpected page errors:', pageErrors);
  }
  expect(pageErrors, 'Unexpected page errors during Golden Scenario').toEqual([]);

  if (failedResponses.length > 0) {
    console.error('Failed API responses:', failedResponses);
  }
  expect(failedResponses, 'Failed API responses during Golden Scenario').toEqual([]);
});

/**
 * Test metadata
 *
 * Test count: 1
 * Assertions: ~50+
 * Coverage:
 * - Authentication flow (AT-002)
 * - Golden Dataset integrity (AT-003)
 * - Deterministic risk calculation (AT-004)
 * - No hidden UI mocks (AT-005)
 *
 * Golden Scenario Data (from backend seed):
 * - RISK-001: CTRL-X4, shortage 8, CRITICAL, WO-2026-0142
 * - RISK-002: MOTOR-M2, shortage 6, HIGH, WO-2026-0150
 * - RISK-003: SENSOR-L9, shortage 5, MEDIUM, WO-2026-0156
 *
 * Evidence values for RISK-001:
 * - Required: 20
 * - Available: 12
 * - Confirmed early: 0
 * - Confirmed late: 0
 * - Shortage: 8 (calculated: max(0, 20 - 12 - 0) = 8)
 */
