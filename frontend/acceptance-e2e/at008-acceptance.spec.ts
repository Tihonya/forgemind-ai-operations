import { test, expect, request } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'

/**
 * AT-008: Structured Output Validation Failure
 *
 * This spec exercises the production UI and writes a structured BrowserResult
 * artifact to the exact task-owned path provided by the harness.
 *
 * The harness loads this artifact and uses product_workflow_run_id as the
 * authoritative evidence key for all DB/API queries.
 *
 * Third-remediation corrections:
 * - Final state is read from the workflow-run-detail page's ``run-state-badge``
 *   (NOT the supply-risk-detail ``workflow-state`` test id) after navigation,
 *   and a missing/malformed/mismatched ``data-state`` fails the scenario.
 * - Evidence enrichment uses a dedicated, fail-closed absolute acceptance API
 *   base (``ACCEPTANCE_API_BASE_URL``), never a relative ``page.request`` call
 *   that resolves through the Vite dev proxy.
 * - correlation_id and dispatch_generation are read from real API responses;
 *   no null/fallback values are accepted.
 * - Screenshot and paired DOM snapshot are captured and referenced.
 * - BrowserResult is written atomically (temp sibling + rename).
 */

const HARNESS_EXECUTION_ID = process.env.HARNESS_EXECUTION_ID || ''
const SCENARIO = process.env.ACCEPTANCE_SCENARIO || ''
const BROWSER_RESULT_PATH = process.env.BROWSER_RESULT_PATH || ''

// Fail-closed identity requirements: the harness owns these values.
if (!HARNESS_EXECUTION_ID) {
  throw new Error('HARNESS_EXECUTION_ID must be set for acceptance tests')
}
if (!SCENARIO) {
  throw new Error('ACCEPTANCE_SCENARIO must be set for acceptance tests')
}
if (!BROWSER_RESULT_PATH) {
  throw new Error('BROWSER_RESULT_PATH must be set for acceptance tests')
}

const BROWSER_RESULT_PATH_ABS = path.resolve(BROWSER_RESULT_PATH)

interface ScreenshotArtifact {
  name: string
  path: string
  dom_snapshot_path?: string
}

interface BrowserResult {
  schema_version: string
  scenario: string
  harness_execution_id: string
  product_workflow_run_id: string
  correlation_id: string
  plan_id: string
  browser_test_start: string
  browser_test_end: string
  final_state: string
  dispatch_generation: number
  screenshots: ScreenshotArtifact[]
}

interface WorkflowRunDetail {
  id: string
  correlation_id: string
  state: string
  dispatch_generation: number
}

function resolveAcceptanceApiBase(): string {
  const raw = process.env.ACCEPTANCE_API_BASE_URL || ''
  if (!raw) {
    throw new Error('ACCEPTANCE_API_BASE_URL must be set for acceptance tests')
  }
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    throw new Error(`ACCEPTANCE_API_BASE_URL is not a valid absolute URL: ${raw}`)
  }
  if (parsed.protocol !== 'http:') {
    throw new Error(
      `ACCEPTANCE_API_BASE_URL must use http: protocol, got ${parsed.protocol}`,
    )
  }
  if (parsed.hostname !== 'localhost' && parsed.hostname !== '127.0.0.1') {
    throw new Error(
      `ACCEPTANCE_API_BASE_URL host must be localhost/127.0.0.1, got ${parsed.hostname}`,
    )
  }
  const expectedPort = process.env.ACCEPTANCE_BACKEND_PORT || '8001'
  if (parsed.port !== expectedPort) {
    throw new Error(
      `ACCEPTANCE_API_BASE_URL port must be ${expectedPort}, got ${parsed.port}`,
    )
  }
  if (!parsed.pathname.endsWith('/api/v1')) {
    throw new Error(
      `ACCEPTANCE_API_BASE_URL must include the /api/v1 prefix, got ${parsed.pathname}`,
    )
  }
  // Normalize to a trailing slash so relative request paths resolve against
  // /api/v1/ (not against a parent directory), matching Playwright's
  // `new URL(path, baseURL)` semantics.
  return raw.endsWith('/') ? raw : `${raw}/`
}

const ACCEPTANCE_API_BASE_URL = resolveAcceptanceApiBase()

async function fetchWorkflowRun(
  api: Awaited<ReturnType<typeof request.newContext>>,
  runId: string,
): Promise<WorkflowRunDetail> {
  const resp = await api.get(`workflow-runs/${runId}`)
  if (!resp.ok()) {
    throw new Error(
      `workflow-run API request failed: ${resp.status()} ${resp.statusText()}`,
    )
  }
  let data: unknown
  try {
    data = await resp.json()
  } catch (err) {
    throw new Error(`workflow-run API returned invalid JSON: ${String(err)}`)
  }
  if (typeof data !== 'object' || data === null) {
    throw new Error('workflow-run API response is not an object')
  }
  const detail = data as Record<string, unknown>

  const id = detail.id
  if (typeof id !== 'string' || id.length === 0) {
    throw new Error('workflow-run API response is missing a string id')
  }
  if (id !== runId) {
    throw new Error(
      `workflow-run API returned the wrong run ID: ${id} != ${runId}`,
    )
  }

  const correlationId = detail.correlation_id
  if (typeof correlationId !== 'string' || correlationId.length === 0) {
    throw new Error(
      `workflow-run API returned a null/empty correlation_id: ${String(correlationId)}`,
    )
  }

  const state = detail.state
  if (typeof state !== 'string' || state.length === 0) {
    throw new Error('workflow-run API returned a null/empty state')
  }

  const generation = detail.dispatch_generation
  if (typeof generation !== 'number' || !Number.isInteger(generation)) {
    throw new Error(
      `workflow-run API returned a non-integer dispatch_generation: ${String(generation)}`,
    )
  }

  return {
    id,
    correlation_id: correlationId,
    state,
    dispatch_generation: generation,
  }
}

function writeBrowserResultAtomic(finalPath: string, data: unknown): void {
  const dir = path.dirname(finalPath)
  fs.mkdirSync(dir, { recursive: true })
  const serialized = JSON.stringify(data, null, 2)
  const tmpPath = `${finalPath}.${process.pid}.${Date.now()}.tmp`
  try {
    const fd = fs.openSync(tmpPath, 'wx')
    try {
      fs.writeFileSync(fd, serialized, 'utf8')
      fs.fsyncSync(fd)
    } finally {
      fs.closeSync(fd)
    }
    fs.renameSync(tmpPath, finalPath)
  } catch (err) {
    try {
      fs.unlinkSync(tmpPath)
    } catch {
      // Temp file may not exist; ignore cleanup failure.
    }
    throw err
  }
}

test.describe('AT-008: Structured Output Validation Failure', () => {
  test('workflow reaches FAILED_VALIDATION with correct trace', async ({ page }) => {
    const browserStart = new Date().toISOString()

    // Login as manager.demo (PRODUCTION_MANAGER)
    await page.goto('/login')
    await page.getByLabel(/username/i).fill('manager.demo')
    await page.getByLabel(/password/i).fill('ManagerPass123!')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).toHaveURL('/', { timeout: 10000 })

    // Navigate to supply risk list
    await page.goto('/supply-risk')
    await expect(page.getByTestId('risk-list')).toBeVisible({ timeout: 10000 })

    // Click into RISK-001 detail page
    await page.getByRole('link', { name: /View RISK-001/i }).click()
    await expect(page).toHaveURL('/supply-risk/RISK-001', { timeout: 5000 })

    // Start workflow and capture the run_id from the API response
    const startResponse = page.waitForResponse(
      (resp) =>
        resp.url().includes('/api/v1/workflow-runs') &&
        resp.request().method() === 'POST',
    )
    const startButton = page.getByTestId('start-workflow-button')
    await expect(startButton).toBeVisible({ timeout: 5000 })
    await startButton.click()
    const response = await startResponse
    const responseBody = (await response.json()) as Record<string, unknown>
    const runId = responseBody.run_id
    if (typeof runId !== 'string' || runId.length === 0) {
      throw new Error('workflow start response is missing a run_id')
    }

    // Wait for workflow to reach FAILED_VALIDATION (polling happens automatically)
    const supplyRiskStateBadge = page.getByTestId('workflow-state')
    await expect(supplyRiskStateBadge).toHaveAttribute(
      'data-state',
      'FAILED_VALIDATION',
      { timeout: 30000 },
    )

    // Enrich from the real acceptance API (direct base, never the Vite proxy).
    // The endpoint requires Bearer auth — read the same session token the
    // frontend axios interceptor uses, and attach it to the API context.
    const accessToken = await page.evaluate(() =>
      sessionStorage.getItem('forgemind_access_token'),
    )
    if (!accessToken) {
      throw new Error('access token not found in sessionStorage after login')
    }
    const api = await request.newContext({
      baseURL: ACCEPTANCE_API_BASE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${accessToken}` },
    })
    const detail = await fetchWorkflowRun(api, runId)
    if (detail.state !== 'FAILED_VALIDATION') {
      throw new Error(
        `workflow-run API state ${detail.state} != FAILED_VALIDATION`,
      )
    }
    const correlationId = detail.correlation_id
    const dispatchGeneration = detail.dispatch_generation

    // Navigate to workflow run detail page to verify step trace
    await page.goto(`/workflow-runs/${runId}`)
    await expect(page.getByTestId('run-detail')).toBeVisible({ timeout: 10000 })

    // Read the actual final state from the run-detail page's own test id.
    // Do NOT reuse the supply-risk-detail locator, and do NOT default a
    // missing attribute to FAILED_VALIDATION.
    const runStateBadge = page.getByTestId('run-state-badge')
    await expect(runStateBadge).toBeVisible({ timeout: 10000 })
    const finalState = await runStateBadge.getAttribute('data-state')
    if (finalState === null || finalState.length === 0) {
      throw new Error('run-state-badge is missing the data-state attribute')
    }
    if (finalState !== 'FAILED_VALIDATION') {
      throw new Error(
        `run-state-badge state ${finalState} != FAILED_VALIDATION`,
      )
    }
    // Cross-check: production UI state must match the acceptance API state.
    if (finalState !== detail.state) {
      throw new Error(
        `UI/API state mismatch: UI=${finalState}, API=${detail.state}`,
      )
    }

    // Verify step trace shows provider_call succeeded and validation failed
    const steps = page.locator('[data-testid^="step-"]')
    const stepCount = await steps.count()
    expect(stepCount).toBeGreaterThan(0)

    let providerCallFound = false
    let validationFailedFound = false

    for (let i = 0; i < stepCount; i++) {
      const step = steps.nth(i)
      const stepText = await step.textContent()

      if (stepText?.includes('provider_call')) {
        const statusBadge = step.getByTestId('step-status-badge')
        await expect(statusBadge).toHaveAttribute('data-status', 'completed')
        providerCallFound = true
      }

      if (stepText?.includes('validation')) {
        const statusBadge = step.getByTestId('step-status-badge')
        await expect(statusBadge).toHaveAttribute('data-status', 'failed')

        const errorCode = step.getByTestId('step-error-code')
        await expect(errorCode).toContainText('VALIDATION_FAILED')

        validationFailedFound = true
      }
    }

    expect(providerCallFound).toBe(true)
    expect(validationFailedFound).toBe(true)

    // Verify NO recommendation is rendered
    await expect(page.getByTestId('no-recommendation')).toBeVisible({
      timeout: 5000,
    })

    const browserEnd = new Date().toISOString()

    // Capture screenshot + paired DOM snapshot from the run-detail page
    const resultDir = path.dirname(BROWSER_RESULT_PATH_ABS)
    const screenshotPath = path.join(resultDir, `${SCENARIO}-final-state.png`)
    const domSnapshotPath = path.join(
      resultDir,
      `${SCENARIO}-final-state.dom.txt`,
    )
    await page.screenshot({ path: screenshotPath, fullPage: false })
    const domSnapshot = await page.evaluate(() => document.body?.innerText ?? '')
    fs.writeFileSync(domSnapshotPath, domSnapshot, 'utf8')

    // Verify the artifacts exist before publishing the result
    if (!fs.existsSync(screenshotPath)) {
      throw new Error(`Screenshot was not written: ${screenshotPath}`)
    }
    if (!fs.existsSync(domSnapshotPath)) {
      throw new Error(`DOM snapshot was not written: ${domSnapshotPath}`)
    }

    const result: BrowserResult = {
      schema_version: '1.0',
      scenario: SCENARIO,
      harness_execution_id: HARNESS_EXECUTION_ID,
      product_workflow_run_id: runId,
      correlation_id: correlationId,
      plan_id: 'PLAN-2026-W31',
      browser_test_start: browserStart,
      browser_test_end: browserEnd,
      final_state: finalState,
      dispatch_generation: dispatchGeneration,
      screenshots: [
        {
          name: 'final-state',
          path: screenshotPath,
          dom_snapshot_path: domSnapshotPath,
        },
      ],
    }

    writeBrowserResultAtomic(BROWSER_RESULT_PATH_ABS, result)

    // Verify deterministic risks remain available by navigating back to supply-risk
    await page.goto('/supply-risk')
    await expect(page.getByTestId('risk-list')).toBeVisible()
    await expect(page.getByTestId('risk-count')).toBeVisible()
  })
})
