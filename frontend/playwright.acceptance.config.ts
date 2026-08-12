/**
 * Playwright configuration for WP-REC-03H acceptance harness (Phase B/C).
 *
 * Isolated from the ordinary ``playwright.config.ts``:
 * - testDir: ``./acceptance-e2e`` (not ``./e2e``).
 * - No ``webServer`` — the orchestration script manages frontend startup.
 * - ``baseURL`` read from ``PLAYWRIGHT_ACCEPTANCE_BASE_URL`` (fail-closed).
 *
 * This config is invoked by the orchestration script:
 *   npx playwright test --config=playwright.acceptance.config.ts
 */

import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_ACCEPTANCE_BASE_URL
if (!baseURL) {
  throw new Error(
    'PLAYWRIGHT_ACCEPTANCE_BASE_URL must be set for acceptance tests. ' +
    'The orchestration script sets this automatically.',
  )
}

// Fail-closed: reject unsafe URLs.
try {
  const parsed = new URL(baseURL)
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(`Acceptance base URL must use http or https, got ${parsed.protocol}`)
  }
  if (parsed.hostname === '' || parsed.hostname === 'localhost' && parsed.port === '') {
    throw new Error('Acceptance base URL must specify a port')
  }
} catch (e) {
  if (e instanceof TypeError) {
    throw new Error(`Invalid PLAYWRIGHT_ACCEPTANCE_BASE_URL: ${baseURL}`)
  }
  throw e
}

export default defineConfig({
  testDir: './acceptance-e2e',
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: 'html',
  outputDir: 'test-results/acceptance',
  use: {
    baseURL,
    trace: 'on-first-retry',
    ignoreHTTPSErrors: true,
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'acceptance',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // No webServer — orchestration script manages frontend startup.
})
