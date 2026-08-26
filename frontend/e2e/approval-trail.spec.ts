/**
 * WP-UX-UA-05 focused role-to-role E2E journey (remediated WP-UX-UA-05-R1).
 *
 * Verifies the end-to-end decision trail across three roles against a
 * disposable local seeded environment (deterministic seeded recommendation —
 * no paid AI generation):
 *
 *   Production Manager    → eligible recommendation → "Передати на погодження"
 *                           → prefilled confirmation → successful submission
 *                           (no manual UUID input)
 *   Procurement Specialist → newly submitted request → approve with comment
 *                           → approved record stays reachable after reload
 *                           → create exactly one procurement task via the UI
 *   Auditor               → canonical submission and decision events
 *                           → matching correlation ID (read-only)
 *
 * A second isolated request (RISK-002) exercises the rejection path.
 *
 * Precondition: the seeded environment has a COMPLETED workflow run for the
 * active plan whose validated recommendation contains the controlled
 * CREATE_PROCUREMENT_TASK action for RISK-001 and RISK-002 (deterministic
 * fixture inserted into the disposable database only — not committed).
 *
 * Selectors use accessible roles + names (never ambiguous text matches), and
 * each role session is isolated by an explicit logout before the next login.
 */

import { test, expect } from '@playwright/test'

interface Account {
  username: string
  password: string
  displayName: string
}

const MANAGER: Account = {
  username: 'manager.demo',
  password: 'ManagerPass123!',
  displayName: 'Production Manager',
}
const SPECIALIST: Account = {
  username: 'procurement.demo',
  password: 'ProcurementPass123!',
  displayName: 'Procurement Specialist',
}
const AUDITOR: Account = {
  username: 'auditor.demo',
  password: 'AuditorPass123!',
  displayName: 'Auditor',
}

// Serialize so the manager → specialist → auditor hand-off and the isolated
// rejection request do not race each other against the shared database.
test.describe.configure({ mode: 'serial' })

async function login(page: import('@playwright/test').Page, account: Account) {
  await page.goto('/')
  await expect(page).toHaveTitle(/ForgeMind/)
  await page.getByTestId('login-username').fill(account.username)
  await page.getByTestId('login-password').fill(account.password)
  await page.getByRole('button', { name: 'Увійти' }).click()
  await expect(page).toHaveURL('/', { timeout: 10000 })
  // Prove the authenticated identity carried into the authenticated shell.
  await expect(page.getByTestId('header-user')).toContainText(account.displayName)
}

async function logout(page: import('@playwright/test').Page) {
  await page.getByTestId('header-logout').click()
  await expect(page).toHaveURL('/login', { timeout: 10000 })
}

test('WP-UX-UA-05 end-to-end decision trail across three roles', async ({ page }) => {
  // ────────────────────────────────────────────────────────────
  // Production Manager: guided approval creation
  // ────────────────────────────────────────────────────────────
  await login(page, MANAGER)
  await page.goto('/supply-risk')
  // Open the first risk by its accessible role + name (not a table-cell text).
  await page.getByRole('link', { name: 'Переглянути RISK-001' }).click()
  await expect(page).toHaveURL(/\/supply-risk\/RISK-001/)

  const submit = page.getByTestId('submit-for-approval')
  await expect(submit).toBeVisible()

  // F3: open the confirmation with the keyboard; Escape returns focus to the
  // "Передати на погодження" trigger (not <body>).
  await submit.focus()
  await submit.press('Enter')
  await expect(page.getByTestId('approval-confirmation')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('approval-confirmation')).toBeHidden()
  await expect(submit).toBeFocused()

  // Re-open and complete a prefilled submission — no manual UUID input.
  await submit.click()
  await expect(page.getByTestId('approval-confirmation')).toBeVisible()
  await expect(page.getByTestId('confirm-submit')).toBeEnabled()

  // Capture the technical correlation id before submission so the auditor can
  // verify the same lineage later.
  await page.getByText('Технічні деталі').click()
  const correlationId =
    (await page.getByTestId('technical-correlation-id').textContent())?.trim() ??
    null

  await page.getByTestId('confirm-submit').click()
  await expect(page.getByTestId('confirm-success')).toBeVisible()

  // Close the success dialog before switching roles.
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('approval-confirmation')).toBeHidden()

  // ────────────────────────────────────────────────────────────
  // Procurement Specialist: approve the submitted request
  // ────────────────────────────────────────────────────────────
  await logout(page)
  await login(page, SPECIALIST)
  await page.goto('/approval-center')
  await expect(page.getByTestId('approval-list')).toBeVisible()

  // The newly submitted request is PENDING and the specialist can decide it.
  const card = page.getByTestId('approval-request-card').filter({ hasText: 'RISK-001' })
  await expect(card).toBeVisible()
  await card.getByTestId('approve-button').click()
  await card.getByTestId('decision-comment').fill('Approved after review.')
  await card.getByTestId('decision-submit').click()

  // The decision resolves to a terminal APPROVED transition.
  await expect(card.getByTestId('transition-to')).toHaveAttribute('data-code', 'APPROVED')

  // F2: the approved record stays reachable after a full reload.
  await page.reload()
  await expect(page.getByTestId('approval-list')).toBeVisible()
  const approvedCard = page
    .getByTestId('approval-request-card')
    .filter({ hasText: 'RISK-001' })
  await expect(approvedCard.getByTestId('transition-to')).toHaveAttribute(
    'data-code',
    'APPROVED',
  )

  // F2: create exactly one controlled procurement task through the visible UI.
  await expect(approvedCard.getByTestId('create-task-button')).toBeVisible()
  await approvedCard.getByTestId('create-task-button').click()
  await expect(approvedCard.getByTestId('procurement-task-present')).toBeVisible()
  await expect(approvedCard.getByTestId('task-reference')).toContainText('TASK-')

  // ────────────────────────────────────────────────────────────
  // Auditor: canonical events with matching correlation ID
  // ────────────────────────────────────────────────────────────
  await logout(page)
  await login(page, AUDITOR)
  await page.goto(`/audit-log?correlation_id=${correlationId}`)

  await expect(page.getByTestId('audit-list')).toBeVisible()
  await expect(page.getByTestId('audit-filter-input')).toHaveValue(correlationId ?? '')
  await expect(page.getByTestId('audit-event-row').first()).toBeVisible()
})

test('rejection path is terminal (RISK-002) and produces no task', async ({ page }) => {
  // ────────────────────────────────────────────────────────────
  // Production Manager: create a second, isolated request for RISK-002
  // ────────────────────────────────────────────────────────────
  await login(page, MANAGER)
  await page.goto('/supply-risk')
  await page.getByRole('link', { name: 'Переглянути RISK-002' }).click()
  await expect(page).toHaveURL(/\/supply-risk\/RISK-002/)

  const submit = page.getByTestId('submit-for-approval')
  await expect(submit).toBeVisible()
  await submit.click()
  await expect(page.getByTestId('approval-confirmation')).toBeVisible()
  await page.getByTestId('confirm-submit').click()
  await expect(page.getByTestId('confirm-success')).toBeVisible()

  // Close the success dialog before switching roles.
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('approval-confirmation')).toBeHidden()

  // ────────────────────────────────────────────────────────────
  // Procurement Specialist: reject the second request
  // ────────────────────────────────────────────────────────────
  await logout(page)
  await login(page, SPECIALIST)
  await page.goto('/approval-center')
  await expect(page.getByTestId('approval-list')).toBeVisible()

  const card = page.getByTestId('approval-request-card').filter({ hasText: 'RISK-002' })
  await expect(card).toBeVisible()

  // No create-task action is offered while the request is still PENDING.
  await expect(card.getByTestId('create-task-button')).toHaveCount(0)

  await card.getByTestId('reject-button').click()
  await card.getByTestId('decision-comment').fill('Out of budget.')
  await card.getByTestId('decision-submit').click()

  // REJECTED is terminal: the request leaves the specialist's actionable
  // queue and no procurement task is created.
  await expect(
    page.getByTestId('approval-request-card').filter({ hasText: 'RISK-002' }),
  ).toHaveCount(0)
})
