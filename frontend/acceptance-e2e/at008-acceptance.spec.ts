import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * AT-008: Structured Output Validation Failure
 *
 * This spec exercises the production UI and writes a structured BrowserResult
 * artifact to the exact task-owned path provided by the harness.
 *
 * The harness loads this artifact and uses product_workflow_run_id as the
 * authoritative evidence key for all DB/API queries.
 */

const HARNESS_EXECUTION_ID = process.env.HARNESS_EXECUTION_ID || 'unknown-harness';
const SCENARIO = process.env.ACCEPTANCE_SCENARIO || 'AT008_INVALID_OUTPUT';
const BROWSER_RESULT_PATH = process.env.BROWSER_RESULT_PATH || '';

interface BrowserResult {
  schema_version: string;
  scenario: string;
  harness_execution_id: string;
  product_workflow_run_id: string;
  correlation_id: string | null;
  plan_id: string;
  browser_test_start: string;
  browser_test_end: string;
  final_state: string;
  screenshots: Array<{
    name: string;
    path: string;
    dom_snapshot_path?: string;
  }>;
}

test.describe('AT-008: Structured Output Validation Failure', () => {
  test('workflow reaches FAILED_VALIDATION with correct trace', async ({ page }) => {
    const browserStart = new Date().toISOString();

    // Login as manager.demo (PRODUCTION_MANAGER)
    await page.goto('/login');
    await page.getByLabel(/username/i).fill('manager.demo');
    await page.getByLabel(/password/i).fill('ManagerPass123!');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL('/', { timeout: 10000 });

    // Navigate to supply risk list
    await page.goto('/supply-risk');
    await expect(page.getByTestId('risk-list')).toBeVisible({ timeout: 10000 });

    // Click into RISK-001 detail page
    await page.getByRole('link', { name: /View RISK-001/i }).click();
    await expect(page).toHaveURL('/supply-risk/RISK-001', { timeout: 5000 });

    // Start workflow and capture the run_id from the API response
    const startResponse = page.waitForResponse(
      (resp) => resp.url().includes('/api/v1/workflow-runs') && resp.request().method() === 'POST',
    );
    const startButton = page.getByTestId('start-workflow-button');
    await expect(startButton).toBeVisible({ timeout: 5000 });
    await startButton.click();
    const response = await startResponse;
    const responseBody = await response.json();
    const runId = responseBody.run_id;
    expect(runId).toBeTruthy();

    // Capture correlation_id from the workflow run detail API
    let correlationId: string | null = null;
    try {
      const detailResponse = await page.request.get(
        `/api/v1/workflow-runs/${runId}`,
      );
      if (detailResponse.ok()) {
        const detail = await detailResponse.json();
        correlationId = detail.correlation_id || null;
      }
    } catch {
      // correlation_id may not be available at this point
    }

    // Wait for workflow to reach FAILED_VALIDATION (polling happens automatically)
    const stateBadge = page.getByTestId('workflow-state');
    await expect(stateBadge).toHaveAttribute('data-state', 'FAILED_VALIDATION', {
      timeout: 30000,
    });

    // Navigate to workflow run detail page to verify step trace
    await page.goto(`/workflow-runs/${runId}`);
    await expect(page.getByTestId('run-detail')).toBeVisible({ timeout: 10000 });

    // Verify step trace shows provider_call succeeded and validation failed
    const steps = page.locator('[data-testid^="step-"]');
    const stepCount = await steps.count();
    expect(stepCount).toBeGreaterThan(0);

    let providerCallFound = false;
    let validationFailedFound = false;

    for (let i = 0; i < stepCount; i++) {
      const step = steps.nth(i);
      const stepText = await step.textContent();

      if (stepText?.includes('provider_call')) {
        const statusBadge = step.getByTestId('step-status-badge');
        await expect(statusBadge).toHaveAttribute('data-status', 'completed');
        providerCallFound = true;
      }

      if (stepText?.includes('validation')) {
        const statusBadge = step.getByTestId('step-status-badge');
        await expect(statusBadge).toHaveAttribute('data-status', 'failed');

        const errorCode = step.getByTestId('step-error-code');
        await expect(errorCode).toContainText('VALIDATION_FAILED');

        validationFailedFound = true;
      }
    }

    expect(providerCallFound).toBe(true);
    expect(validationFailedFound).toBe(true);

    // Verify NO recommendation is rendered
    await expect(page.getByTestId('no-recommendation')).toBeVisible({ timeout: 5000 });

    // Capture final state from the DOM
    const finalState = await stateBadge.getAttribute('data-state') || 'FAILED_VALIDATION';

    const browserEnd = new Date().toISOString();

    // Write structured BrowserResult artifact to the exact task-owned path
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
      screenshots: [],
    };

    if (BROWSER_RESULT_PATH) {
      const dir = path.dirname(BROWSER_RESULT_PATH);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(BROWSER_RESULT_PATH, JSON.stringify(result, null, 2));
    }

    // Verify deterministic risks remain available by navigating back to supply-risk
    await page.goto('/supply-risk');
    await expect(page.getByTestId('risk-list')).toBeVisible();
    await expect(page.getByTestId('risk-count')).toBeVisible();
  });
});
