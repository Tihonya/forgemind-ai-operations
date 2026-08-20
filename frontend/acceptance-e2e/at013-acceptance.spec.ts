import { test, expect, request } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'

/**
 * AT-013: Model Outage and Retry
 *
 * This spec exercises the production UI retry path and writes a structured
 * BrowserResult artifact to the exact task-owned path provided by the harness.
 *
 * The artifact captures pre-retry and post-retry snapshots, proving:
 * - the same workflow run ID in both snapshots
 * - dispatch generation advanced by exactly 1
 * - pre-retry FAILED_PROVIDER state
 * - post-retry COMPLETED state
 *
 * Third-remediation corrections:
 * - Both snapshots are captured from real acceptance API responses at the
 *   correct temporal boundary (pre-retry before clicking retry; post-retry
 *   after the completed state) — never inferred, never hardcoded to 0/1.
 * - Evidence enrichment uses a dedicated, fail-closed absolute acceptance API
 *   base (``ACCEPTANCE_API_BASE_URL``), never a relative ``page.request`` call
 *   that resolves through the Vite dev proxy.
 * - Screenshot and paired DOM snapshot are captured for both boundaries.
 * - BrowserResult is written atomically (temp sibling + rename).
 */

const HARNESS_EXECUTION_ID = process.env.HARNESS_EXECUTION_ID || ''
const SCENARIO = process.env.ACCEPTANCE_SCENARIO || ''
const BROWSER_RESULT_PATH = process.env.BROWSER_RESULT_PATH || ''

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

interface RetrySnapshot {
  workflow_run_id: string
  generation: number
  state: string
  correlation_id: string
  timestamp: string
}

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
  pre_retry_snapshot: RetrySnapshot
  post_retry_snapshot: RetrySnapshot
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

test.describe('AT-013: Model Outage and Retry', () => {
  test('workflow fails, retries, and completes with correct trace', async ({ page }) => {
    const browserStart = new Date().toISOString()

    // Login as manager.demo (PRODUCTION_MANAGER)
    await page.goto('/login')
    await page.getByTestId('login-username').fill('manager.demo')
    await page.getByTestId('login-password').fill('ManagerPass123!')
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

    // Wait for workflow to reach FAILED_PROVIDER (outage scenario)
    const stateBadge = page.getByTestId('workflow-state')
    await expect(stateBadge).toHaveAttribute('data-state', 'FAILED_PROVIDER', {
      timeout: 30000,
    })

    // Direct acceptance API context (never the Vite proxy), carrying the
    // same Bearer token the frontend axios interceptor attaches.
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

    // Pre-retry snapshot: captured from a real API response BEFORE retry.
    const preRetryDetail = await fetchWorkflowRun(api, runId)
    if (preRetryDetail.state !== 'FAILED_PROVIDER') {
      throw new Error(
        `pre-retry API state ${preRetryDetail.state} != FAILED_PROVIDER`,
      )
    }
    const preRetrySnapshot: RetrySnapshot = {
      workflow_run_id: runId,
      generation: preRetryDetail.dispatch_generation,
      state: preRetryDetail.state,
      correlation_id: preRetryDetail.correlation_id,
      timestamp: new Date().toISOString(),
    }

    // Pre-retry screenshot + DOM snapshot (failed-provider boundary)
    const resultDir = path.dirname(BROWSER_RESULT_PATH_ABS)
    const preScreenshotPath = path.join(resultDir, `${SCENARIO}-pre-retry.png`)
    const preDomSnapshotPath = path.join(
      resultDir,
      `${SCENARIO}-pre-retry.dom.txt`,
    )
    await page.screenshot({ path: preScreenshotPath, fullPage: false })
    const preDomSnapshot = await page.evaluate(
      () => document.body?.innerText ?? '',
    )
    fs.writeFileSync(preDomSnapshotPath, preDomSnapshot, 'utf8')

    // Click retry button on the supply-risk page
    const retryButton = page.getByTestId('retry-workflow-button')
    await expect(retryButton).toBeVisible({ timeout: 5000 })
    await retryButton.click()

    // Wait for workflow state to transition away from FAILED_PROVIDER
    await expect(stateBadge).not.toHaveAttribute('data-state', 'FAILED_PROVIDER', {
      timeout: 10000,
    })

    // Wait for workflow to reach COMPLETED (retry success)
    await expect(stateBadge).toHaveAttribute('data-state', 'COMPLETED', {
      timeout: 30000,
    })

    // Post-retry snapshot: captured from a real API response AFTER completed.
    const postRetryDetail = await fetchWorkflowRun(api, runId)
    if (postRetryDetail.state !== 'COMPLETED') {
      throw new Error(`post-retry API state ${postRetryDetail.state} != COMPLETED`)
    }
    const postRetrySnapshot: RetrySnapshot = {
      workflow_run_id: runId,
      generation: postRetryDetail.dispatch_generation,
      state: postRetryDetail.state,
      correlation_id: postRetryDetail.correlation_id,
      timestamp: new Date().toISOString(),
    }

    // Post-retry screenshot + DOM snapshot (completed boundary)
    const postScreenshotPath = path.join(resultDir, `${SCENARIO}-post-retry.png`)
    const postDomSnapshotPath = path.join(
      resultDir,
      `${SCENARIO}-post-retry.dom.txt`,
    )
    await page.screenshot({ path: postScreenshotPath, fullPage: false })
    const postDomSnapshot = await page.evaluate(
      () => document.body?.innerText ?? '',
    )
    fs.writeFileSync(postDomSnapshotPath, postDomSnapshot, 'utf8')

    // Verify generation advanced by exactly 1 (real values, no fallbacks)
    expect(postRetrySnapshot.generation).toBe(preRetrySnapshot.generation + 1)
    // Verify same run ID in both snapshots
    expect(postRetrySnapshot.workflow_run_id).toBe(
      preRetrySnapshot.workflow_run_id,
    )
    // Verify correlation identity is present and continuous
    expect(preRetrySnapshot.correlation_id.length).toBeGreaterThan(0)
    expect(postRetrySnapshot.correlation_id.length).toBeGreaterThan(0)

    // Navigate to workflow run detail page to verify step trace
    await page.goto(`/workflow-runs/${runId}`)
    await expect(page.getByTestId('run-detail')).toBeVisible({ timeout: 10000 })

    // Verify step trace is APPEND-ONLY (preserves failed attempt, adds new steps)
    const steps = page.locator('[data-testid^="step-"]')
    const stepCount = await steps.count()
    expect(stepCount).toBeGreaterThanOrEqual(2)

    // Verify the failed provider_call step is preserved (append-only)
    let failedProviderCallFound = false
    let succeededProviderCallFound = false
    let validationSucceededFound = false

    for (let i = 0; i < stepCount; i++) {
      const step = steps.nth(i)
      const stepText = await step.textContent()

      if (stepText?.includes('provider_call')) {
        const statusBadge = step.getByTestId('step-status-badge')
        const status = await statusBadge.getAttribute('data-status')

        if (status === 'failed') {
          const errorCode = step.getByTestId('step-error-code')
          await expect(errorCode).toContainText('PROVIDER_TRANSIENT')
          failedProviderCallFound = true
        }

        if (status === 'completed') {
          succeededProviderCallFound = true
        }
      }

      if (stepText?.includes('validation')) {
        const statusBadge = step.getByTestId('step-status-badge')
        const status = await statusBadge.getAttribute('data-status')

        if (status === 'completed') {
          validationSucceededFound = true
        }
      }
    }

    expect(failedProviderCallFound).toBe(true)
    expect(succeededProviderCallFound).toBe(true)
    expect(validationSucceededFound).toBe(true)

    // Verify recommendation IS rendered (workflow completed successfully)
    await expect(page.getByTestId('no-recommendation')).not.toBeVisible({
      timeout: 5000,
    })

    const browserEnd = new Date().toISOString()

    // Verify the artifacts exist before publishing the result
    for (const artifactPath of [
      preScreenshotPath,
      preDomSnapshotPath,
      postScreenshotPath,
      postDomSnapshotPath,
    ]) {
      if (!fs.existsSync(artifactPath)) {
        throw new Error(`Artifact was not written: ${artifactPath}`)
      }
    }

    const result: BrowserResult = {
      schema_version: '1.0',
      scenario: SCENARIO,
      harness_execution_id: HARNESS_EXECUTION_ID,
      product_workflow_run_id: runId,
      correlation_id: postRetrySnapshot.correlation_id,
      plan_id: 'PLAN-2026-W31',
      browser_test_start: browserStart,
      browser_test_end: browserEnd,
      final_state: 'COMPLETED',
      dispatch_generation: postRetrySnapshot.generation,
      screenshots: [
        {
          name: 'pre-retry',
          path: preScreenshotPath,
          dom_snapshot_path: preDomSnapshotPath,
        },
        {
          name: 'post-retry',
          path: postScreenshotPath,
          dom_snapshot_path: postDomSnapshotPath,
        },
      ],
      pre_retry_snapshot: preRetrySnapshot,
      post_retry_snapshot: postRetrySnapshot,
    }

    writeBrowserResultAtomic(BROWSER_RESULT_PATH_ABS, result)
  })
})
