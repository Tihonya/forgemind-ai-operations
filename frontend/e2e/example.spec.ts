import { expect, test } from '@playwright/test'

test.describe('smoke', () => {
  test('application loads', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/ForgeMind/)
  })
})
