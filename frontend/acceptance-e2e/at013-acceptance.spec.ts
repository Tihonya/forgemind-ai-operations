import { test, expect } from '@playwright/test';

test.describe('AT-013: Model Outage and Retry', () => {
  test('workflow fails, retries, and completes with correct trace', async ({ page }) => {
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

    // Wait for workflow to reach FAILED_PROVIDER (outage scenario)
    // Stay on supply-risk page so polling continues
    const stateBadge = page.getByTestId('workflow-state');
    await expect(stateBadge).toHaveAttribute('data-state', 'FAILED_PROVIDER', {
      timeout: 30000,
    });

    // Verify deterministic risks are STILL available on the supply-risk page
    // The RiskSummary card renders the risk data (severity, component, etc.)
    await expect(page.getByText(`Risk ${'RISK-001'}`)).toBeVisible({ timeout: 5000 });

    // Click retry button on the supply-risk page
    const retryButton = page.getByTestId('retry-workflow-button');
    await expect(retryButton).toBeVisible({ timeout: 5000 });
    await retryButton.click();

    // Wait for workflow state to transition away from FAILED_PROVIDER
    await expect(stateBadge).not.toHaveAttribute('data-state', 'FAILED_PROVIDER', {
      timeout: 10000,
    });

    // Wait for workflow to reach COMPLETED (retry success)
    await expect(stateBadge).toHaveAttribute('data-state', 'COMPLETED', {
      timeout: 30000,
    });

    // Navigate to workflow run detail page to verify step trace
    await page.goto(`/workflow-runs/${runId}`);
    await expect(page.getByTestId('run-detail')).toBeVisible({ timeout: 10000 });

    // Verify step trace is APPEND-ONLY (preserves failed attempt, adds new steps)
    const steps = page.locator('[data-testid^="step-"]');
    const stepCount = await steps.count();
    expect(stepCount).toBeGreaterThanOrEqual(2);

    // Verify the failed provider_call step is preserved (append-only)
    let failedProviderCallFound = false;
    let succeededProviderCallFound = false;
    let validationSucceededFound = false;

    for (let i = 0; i < stepCount; i++) {
      const step = steps.nth(i);
      const stepText = await step.textContent();

      if (stepText?.includes('provider_call')) {
        const statusBadge = step.getByTestId('step-status-badge');
        const status = await statusBadge.getAttribute('data-status');

        if (status === 'failed') {
          const errorCode = step.getByTestId('step-error-code');
          await expect(errorCode).toContainText('PROVIDER_TRANSIENT');
          failedProviderCallFound = true;
        }

        if (status === 'completed') {
          succeededProviderCallFound = true;
        }
      }

      if (stepText?.includes('validation')) {
        const statusBadge = step.getByTestId('step-status-badge');
        const status = await statusBadge.getAttribute('data-status');

        if (status === 'completed') {
          validationSucceededFound = true;
        }
      }
    }

    expect(failedProviderCallFound).toBe(true);
    expect(succeededProviderCallFound).toBe(true);
    expect(validationSucceededFound).toBe(true);

    // Verify recommendation IS rendered (workflow completed successfully)
    await expect(page.getByTestId('no-recommendation')).not.toBeVisible({ timeout: 5000 });

    // Verify at least one risk item is rendered in recommendation
    const recommendationRisks = page.locator('[data-testid^="risk-"]');
    const recommendationRiskCount = await recommendationRisks.count();
    expect(recommendationRiskCount).toBeGreaterThan(0);
  });
});
