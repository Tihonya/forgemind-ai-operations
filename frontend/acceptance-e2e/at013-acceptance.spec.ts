/**
 * AT-013 acceptance harness — Playwright scenario (WP-REC-03H Phase B).
 *
 * Exercises the real browser → frontend → backend → worker path with the
 * AT013_OUTAGE_UNTIL_RETRY acceptance scenario active.  Verifies:
 *
 * 1. Provider outage renders FAILED_PROVIDER in the trace.
 * 2. Retry button is visible and triggers a dispatch-generation increment.
 * 3. Post-retry success renders the recommendation section.
 * 4. Prior trace steps are preserved (append-only).
 *
 * This is an implementation-verification spec.  It does NOT declare
 * AT-013 PASS.
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

test.describe('AT-013 Acceptance: Provider Outage → Retry → Success', () => {
  test('provider outage and user retry lifecycle', async ({ page }) => {
    // 1. Authenticate.
    await page.goto('/login')
    await page.fill('[data-testid="email-input"]', 'production_manager@demo.com')
    await page.fill('[data-testid="password-input"]', 'demo')
    await page.click('[data-testid="login-button"]')
    await page.waitForURL('**/dashboard')

    // 2. Navigate to supply-risk detail.
    await page.goto('/supply-risk/PLAN-2026-W31')
    await expect(page.locator('[data-testid="risk-list"]')).toBeVisible({ timeout: 15_000 })

    // 3. Start AI analysis.
    const startBtn = page.locator('[data-testid="start-workflow-button"]')
    if (await startBtn.isVisible()) {
      await startBtn.click()
    }

    // 4. Get run_id.
    await page.waitForTimeout(1000)
    const runsResp = await page.request.get(
      '/api/v1/workflow-runs?plan_code=PLAN-2026-W31&limit=1',
    )
    expect(runsResp.ok()).toBeTruthy()
    const runs = await runsResp.json()
    expect(runs.length).toBeGreaterThan(0)
    const runId = runs[0].id

    // 5. Wait for FAILED_PROVIDER (generation 0 outage).
    const failed = await waitForTerminalState(page, runId)
    expect(failed.state).toBe('FAILED_PROVIDER')
    expect(failed.dispatch_generation).toBe(0)

    // 6. Navigate to workflow detail.
    await page.goto(`/workflow-runs/${runId}`)
    await expect(page.locator('[data-testid="workflow-trace"]')).toBeVisible({
      timeout: 10_000,
    })

    // 7. Verify provider failure step is visible.
    const providerStep = page.locator(
      '[data-testid="workflow-step-provider_call"]',
    )
    await expect(providerStep).toBeVisible()

    // 8. Screenshot of failed state.
    await page.screenshot({
      path: `test-results/at013-failed-provider.png`,
      fullPage: true,
    })

    // 9. Click Retry button.
    const retryBtn = page.locator('[data-testid="retry-workflow-button"]')
    await expect(retryBtn).toBeVisible()
    await retryBtn.click()

    // 10. Wait for COMPLETED (generation 1 success).
    const completed = await waitForTerminalState(page, runId)
    expect(completed.state).toBe('COMPLETED')
    expect(completed.dispatch_generation).toBe(1)

    // 11. Verify recommendation section is now rendered.
    await page.goto(`/workflow-runs/${runId}`)
    const recSection = page.locator('[data-testid="recommendation-section"]')
    await expect(recSection).toBeVisible({ timeout: 10_000 })

    // 12. Verify trace has both failed and completed provider steps (append-only).
    const allProviderSteps = page.locator(
      '[data-testid="workflow-step-provider_call"]',
    )
    const count = await allProviderSteps.count()
    expect(count).toBeGreaterThanOrEqual(2)

    // 13. Screenshot of success state.
    await page.screenshot({
      path: `test-results/at013-completed.png`,
      fullPage: true,
    })
  })
})
