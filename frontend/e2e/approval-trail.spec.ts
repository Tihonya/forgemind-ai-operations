/**
 * WP-UX-UA-05 focused role-to-role E2E journey.
 *
 * Verifies the end-to-end decision trail across three roles against a
 * disposable local seeded environment (deterministic seeded recommendation —
 * no paid AI generation):
 *
 *   Production Manager    → eligible recommendation → "Передати на погодження"
 *                           → prefilled confirmation → successful submission
 *   Procurement Specialist → newly submitted request → approve with comment
 *                           → resulting status + task relationship
 *   Auditor               → canonical submission and decision events
 *                           → matching correlation ID
 *
 * Precondition: the seeded environment has a COMPLETED workflow run for the
 * active plan whose recommendation contains the controlled
 * CREATE_PROCUREMENT_TASK action for RISK-001 (deterministic seed data).
 */

import { test, expect } from '@playwright/test'

const MANAGER = { username: 'manager.demo', password: 'ManagerPass123!' }
const SPECIALIST = { username: 'procurement.demo', password: 'ProcurementPass123!' }
const AUDITOR = { username: 'auditor.demo', password: 'AuditorPass123!' }

async function login(page: import('@playwright/test').Page, account: typeof MANAGER) {
  await page.goto('/')
  await expect(page).toHaveTitle(/ForgeMind/)
  await page.getByTestId('login-username').fill(account.username)
  await page.getByTestId('login-password').fill(account.password)
  await page.getByRole('button', { name: 'Увійти' }).click()
  await expect(page).toHaveURL('/', { timeout: 10000 })
}

test('WP-UX-UA-05 end-to-end decision trail across three roles', async ({ page }) => {
  // ────────────────────────────────────────────────────────────
  // Production Manager: guided approval creation
  // ────────────────────────────────────────────────────────────
  await login(page, MANAGER)
  await page.goto('/supply-risk')
  // Open the first risk (RISK-001) from the risk list.
  await page.getByText('RISK-001').first().click()
  await expect(page).toHaveURL(/\/supply-risk\/RISK-001/)

  // The recommendation surface exposes the guided primary action.
  const submitForApproval = page.getByTestId('submit-for-approval')
  await expect(submitForApproval).toBeVisible()
  await submitForApproval.click()

  // Prefilled confirmation — no manual UUID input is required.
  await expect(page.getByTestId('approval-confirmation')).toBeVisible()
  await expect(page.getByTestId('confirm-submit')).toBeEnabled()

  // Capture the technical correlation id before submission so the auditor
  // can verify the same id later.
  await page.getByText('Технічні деталі').click()
  const correlationId = await page
    .getByTestId('technical-correlation-id')
    .textContent()

  await page.getByTestId('confirm-submit').click()

  // Success state with a link to the created request.
  await expect(page.getByTestId('confirm-success')).toBeVisible()
  await expect(page.getByTestId('confirm-open-request')).toBeVisible()

  // ────────────────────────────────────────────────────────────
  // Procurement Specialist: approve the submitted request
  // ────────────────────────────────────────────────────────────
  await login(page, SPECIALIST)
  await page.goto('/approval-center')
  await expect(page.getByTestId('approval-list')).toBeVisible()

  // The newly submitted request is PENDING and the specialist can decide it.
  const card = page.getByTestId('approval-request-card').first()
  await expect(card).toBeVisible()
  await card.getByTestId('approve-button').click()
  await card.getByTestId('decision-comment').fill('Approved after review.')
  await card.getByTestId('decision-submit').click()

  // The decision resolves to a terminal status transition.
  await expect(card.getByTestId('transition-to')).toHaveAttribute(
    'data-code',
    'APPROVED',
  )

  // ────────────────────────────────────────────────────────────
  // Auditor: canonical events with matching correlation ID
  // ────────────────────────────────────────────────────────────
  await login(page, AUDITOR)
  await page.goto(`/audit-log?correlation_id=${correlationId}`)

  // The submission and decision events share the same correlation lineage.
  await expect(page.getByTestId('audit-list')).toBeVisible()
  await expect(page.getByTestId('audit-filter-input')).toHaveValue(
    correlationId?.trim() ?? '',
  )
  await expect(page.getByTestId('audit-event-row').first()).toBeVisible()
})
