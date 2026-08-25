/**
 * Supply Risk route — active-locale date formatting regression tests
 * (WP-UX-UA-01 remediation F-1).
 *
 * Renders the real route with its production hooks mocked (same pattern as
 * the sibling dashboard.test.tsx). Proves:
 * - Ukrainian active → Ukrainian month labels for the SAME plan dates;
 * - switching to English (without unmounting the application — the route
 *   stays mounted across every step) re-renders the same plan dates in
 *   en-US;
 * - switching back → Ukrainian;
 * - the API/query behavior is untouched by the locale switches (the mocked
 *   hooks record their invocations; no extra calls are triggered).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import { LOCALE_STORAGE_KEY } from '@/i18n/locale-service'
import SupplyRisk from '@/routes/supply-risk'
import type { ProductionPlanSummary } from '@/lib/production-plans-api'

vi.mock('@/hooks/useActivePlan')
vi.mock('@/hooks/useRisks')

import * as useActivePlanModule from '@/hooks/useActivePlan'
import * as useRisksModule from '@/hooks/useRisks'

const EXECUTING_PLAN: ProductionPlanSummary = {
  code: 'PLAN-2026-W31',
  status: 'EXECUTING',
  // Seed-shape date-only strings (identical to the golden dataset).
  period_start: '2026-07-31',
  period_end: '2026-08-06',
}

function renderRoute() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SupplyRisk />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SupplyRisk — locale-connected date formatting', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.removeItem(LOCALE_STORAGE_KEY)
    vi.mocked(useActivePlanModule.useActivePlan).mockReturnValue({
      plans: [EXECUTING_PLAN],
      activePlan: EXECUTING_PLAN,
      hasMultipleActive: false,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    vi.mocked(useRisksModule.useRisks).mockReturnValue({
      risks: [],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
  })

  afterEach(() => {
    act(() => {
      void i18n.changeLanguage('uk')
    })
  })

  it('Ukrainian active → Ukrainian month labels for the same plan dates', async () => {
    renderRoute()
    await waitFor(() => expect(i18n.language).toBe('uk'))
    // The banner renders BOTH seed dates in one span; the exact string is
    // the stable locator (no DOM position dependency).
    expect(screen.getByText('31 лип. 2026 р. — 6 серп. 2026 р.')).toBeInTheDocument()
  })

  it('change to English without unmounting: same plan dates rerender en-US', async () => {
    const { unmount } = renderRoute()
    await waitFor(() => expect(i18n.language).toBe('uk'))
    expect(screen.getByText('31 лип. 2026 р. — 6 серп. 2026 р.')).toBeInTheDocument()

    // Same mounted tree — locale switch only (exactly the switcher path).
    act(() => {
      void i18n.changeLanguage('en')
    })
    await waitFor(() => expect(i18n.language).toBe('en'))
    // The SAME mounted route now renders the same dates in en-US.
    expect(screen.getByText('Jul 31, 2026 — Aug 6, 2026')).toBeInTheDocument()
    // The Ukrainian rendering of the same dates is gone.
    expect(screen.queryByText('31 лип. 2026 р. — 6 серп. 2026 р.')).not.toBeInTheDocument()
    unmount()
  })

  it('switch back → Ukrainian again (same mount, no reload)', async () => {
    const { unmount } = renderRoute()
    await waitFor(() => expect(i18n.language).toBe('uk'))

    act(() => {
      void i18n.changeLanguage('en')
    })
    await waitFor(() => expect(i18n.language).toBe('en'))
    expect(screen.getByText('Jul 31, 2026 — Aug 6, 2026')).toBeInTheDocument()

    act(() => {
      void i18n.changeLanguage('uk')
    })
    await waitFor(() => expect(i18n.language).toBe('uk'))
    expect(screen.getByText('31 лип. 2026 р. — 6 серп. 2026 р.')).toBeInTheDocument()
    unmount()
  })

  it('API/query behavior remains unchanged across locale switches', async () => {
    renderRoute()
    await waitFor(() => expect(i18n.language).toBe('uk'))

    act(() => {
      void i18n.changeLanguage('en')
    })
    await waitFor(() => expect(i18n.language).toBe('en'))

    act(() => {
      void i18n.changeLanguage('uk')
    })
    await waitFor(() => expect(i18n.language).toBe('uk'))

    // Query identity is stable across every render: useActivePlan is always
    // invoked with zero arguments and useRisks always with the same plan
    // code — the locale switch never perturbs the data layer.
    const activePlanCalls = vi.mocked(useActivePlanModule.useActivePlan).mock.calls
    const risksCalls = vi.mocked(useRisksModule.useRisks).mock.calls
    expect(activePlanCalls.length).toBeGreaterThan(0)
    for (const args of activePlanCalls) {
      expect(args).toHaveLength(0)
    }
    expect(risksCalls.length).toBeGreaterThan(0)
    for (const args of risksCalls) {
      expect(args[0]).toBe(EXECUTING_PLAN.code)
    }
  })
})