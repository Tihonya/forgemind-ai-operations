/**
 * AT-008 acceptance harness — Playwright scenario (WP-REC-03H Phase B).
 *
 * Exercises the real browser → frontend → backend → worker path with the
 * AT008_INVALID_OUTPUT acceptance scenario active.  Verifies that the
 * workflow trace renders the validation failure and that no recommendation
 * is displayed.
 *
 * This is an implementation-verification spec.  It does NOT declare
 * AT-008 PASS.
 */

import { test, expect } from '@playwright/test'

const WORKFLOW_POLL_INTERVAL_MS = 2000
const WORKFLOW_POLL_TIMEOUT_MS = 60_000

async function waitForTerminalState(
  page: import('@playwright/test').Page,
  runId: string,
): Promise<{ state: string; dispatch_generation: number }> {
  const terminalStates = new Set([
    'COMPLETED',
    'FAILED_VALIDATION',
    'FAILED_PROVIDER',
    'FAILED_INTERNAL',
  ])
  const deadline = Date.now() + WORKFLOW_POLL_TIMEOUT_MS
  while (Date.now() < deadline) {
    const resp = await page.request.get(`/api/v1/workflow-runs/${runId}`)
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    if (terminalStates.has(body.state)) {
      return { state: body.state, dispatch_generation: body.dispatch_generation }
    }
    await page.waitForTimeout(WORKFLOW_POLL_INTERVAL_MS)
  }
  throw new Error(`Workflow ${runId} did not reach terminal state within timeout`)
}

test.describe('AT-008 Acceptance: Invalid Output → FAILED_VALIDATION', () => {
  test('validation failure visible in workflow trace', async ({ page }) => {
    // 1. Authenticate.
    await page.goto('/login')
    await page.fill('[data-testid="email-input"]', 'production_manager@demo.com')
    await page.fill('[data-testid="password-input"]', 'demo')
    await page.click('[data-testid="login-button"]')
    await page.waitForURL('**/dashboard')

    // 2. Navigate to supply-risk detail for PLAN-2026-W31.
    await page.goto('/supply-risk/PLAN-2026-W31')

    // 3. Verify deterministic risks are visible.
    await expect(page.locator('[data-testid="risk-list"]')).toBeVisible({ timeout: 15_000 })

    // 4. Start AI analysis.
    const startBtn = page.locator('[data-testid="start-workflow-button"]')
    if (await startBtn.isVisible()) {
      await startBtn.click()
    }

    // 5. Extract run_id from the page or API.
    //    The frontend navigates to the run detail or exposes the ID.
    //    Poll the latest run for this plan.
    await page.waitForTimeout(1000)
    const runsResp = await page.request.get(
      '/api/v1/workflow-runs?plan_code=PLAN-2026-W31&limit=1',
    )
    expect(runsResp.ok()).toBeTruthy()
    const runs = await runsResp.json()
    expect(runs.length).toBeGreaterThan(0)
    const runId = runs[0].id

    // 6. Wait for terminal state.
    const result = await waitForTerminalState(page, runId)
    expect(result.state).toBe('FAILED_VALIDATION')

    // 7. Navigate to the workflow detail and verify trace.
    await page.goto(`/workflow-runs/${runId}`)
    await expect(page.locator('[data-testid="workflow-trace"]')).toBeVisible({
      timeout: 10_000,
    })

    // 8. Verify validation failure step is visible.
    const validationStep = page.locator(
      '[data-testid="workflow-step-validation"]',
    )
    await expect(validationStep).toBeVisible()

    // 9. Verify no recommendation section is rendered.
    const recSection = page.locator('[data-testid="recommendation-section"]')
    await expect(recSection).toHaveCount(0)

    // 10. Screenshot for evidence.
    await page.screenshot({
      path: `test-results/at008-failed-validation.png`,
      fullPage: true,
    })
  })
})
