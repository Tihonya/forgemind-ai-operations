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

// Fail-closed URL validation: only accept exact local acceptance boundary
const parsed = new URL(baseURL)

// Protocol must be http (local development only)
if (parsed.protocol !== 'http:') {
  throw new Error(`Acceptance base URL must use http: protocol, got ${parsed.protocol}`)
}

// Hostname must be localhost or 127.0.0.1 (reject all external hosts)
if (parsed.hostname !== 'localhost' && parsed.hostname !== '127.0.0.1') {
  throw new Error(
    `Acceptance base URL must use localhost or 127.0.0.1, got ${parsed.hostname}`,
  )
}

// Port must match expected acceptance frontend port
const expectedPort = process.env.ACCEPTANCE_FRONTEND_PORT || '5174'
if (parsed.port !== expectedPort) {
  throw new Error(
    `Acceptance base URL port must be ${expectedPort}, got ${parsed.port}`,
  )
}

// Path must be root or empty
if (parsed.pathname !== '/' && parsed.pathname !== '') {
  throw new Error(`Acceptance base URL must have root path, got ${parsed.pathname}`)
}

// No query parameters allowed
if (parsed.search) {
  throw new Error(`Acceptance base URL must not have query parameters, got ${parsed.search}`)
}

// No hash/fragment allowed
if (parsed.hash) {
  throw new Error(`Acceptance base URL must not have fragment, got ${parsed.hash}`)
}

// No authentication credentials allowed
if (parsed.username || parsed.password) {
  throw new Error('Acceptance base URL must not contain authentication credentials')
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
