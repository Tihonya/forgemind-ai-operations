import i18n from '@/i18n'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AuditLog from '../audit-log'
import { filterAuditEvents } from '@/components/audit/audit-filter'
import { useAuditEvents } from '@/hooks/use-audit-events'
import { createAuditEvent } from '@/test/fixtures/audit-contract'

// WP-UX-UA-03: pin the active locale to English so behavior assertions
// against English copy stay stable after the Ukrainian-first migration.
beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})


vi.mock('@/hooks/use-audit-events', () => ({
  useAuditEvents: vi.fn(),
  useAuditEvent: vi.fn(),
}))

vi.mock('@/components/audit/audit-event-detail', () => ({
  AuditEventDetail: ({
    eventId,
    onClose,
  }: {
    eventId: string | null
    onClose: () => void
  }) =>
    eventId === null ? null : (
      <div data-testid="audit-detail-panel">
        <button type="button" data-testid="audit-detail-close" onClick={onClose}>
          Close
        </button>
      </div>
    ),
}))

vi.mock('@/components/audit/audit-trace-dialog', () => ({
  AuditTraceDialog: ({
    correlationId,
    onClose,
  }: {
    correlationId: string | null
    onClose: () => void
  }) =>
    correlationId === null ? null : (
      <div data-testid="audit-trace-panel">
        <button type="button" data-testid="audit-trace-close" onClick={onClose}>
          Close
        </button>
      </div>
    ),
}))

const mockUseAuditEvents = vi.mocked(useAuditEvents)

function baseList() {
  return {
    events: [],
    total: 0,
    limit: 50,
    offset: 0,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }
}

function renderRoute() {
  return render(
    <MemoryRouter>
      <AuditLog />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuditEvents.mockReturnValue(baseList())
})

describe('filterAuditEvents (pure client-side page filter)', () => {
  const events = [
    createAuditEvent({
      id: 'evt-1',
      event_type: 'APPROVAL_APPROVED',
      correlation_id: 'aaaa1111-0000-0000-0000-000000000000',
      actor_username: 'specialist.demo',
    }),
    createAuditEvent({
      id: 'evt-2',
      event_type: 'PROCUREMENT_TASK_CREATED',
      correlation_id: 'bbbb2222-0000-0000-0000-000000000000',
      actor_username: 'system',
    }),
  ]

  it('returns all events for an empty query', () => {
    expect(filterAuditEvents(events, '')).toHaveLength(2)
    expect(filterAuditEvents(events, '   ')).toHaveLength(2)
  })

  it('matches by human event-type label', () => {
    const result = filterAuditEvents(events, 'Approval approved')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('evt-1')
  })

  it('matches by correlation ID substring', () => {
    const result = filterAuditEvents(events, 'bbbb2222')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('evt-2')
  })

  it('is case-insensitive', () => {
    expect(filterAuditEvents(events, 'SPECIALIST')).toHaveLength(1)
  })

  it('returns no events when nothing matches', () => {
    expect(filterAuditEvents(events, 'definitely-no-match')).toHaveLength(0)
  })
})

describe('AuditLog route', () => {
  it('shows a loading state while the initial page is loading', () => {
    mockUseAuditEvents.mockReturnValue({ ...baseList(), isLoading: true })
    renderRoute()
    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
  })

  it('shows an empty state when there are no events', () => {
    renderRoute()
    expect(screen.getByText('No audit events')).toBeInTheDocument()
  })

  it('renders a populated chronological list with safe fields', () => {
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [
        createAuditEvent({
          id: 'evt-1',
          event_type: 'APPROVAL_APPROVED',
          actor_username: 'specialist.demo',
          risk_id: 'RISK-001',
        }),
      ],
      total: 1,
      limit: 50,
    })
    renderRoute()
    expect(screen.getByTestId('audit-list')).toBeInTheDocument()
    expect(screen.getByTestId('audit-event-row')).toBeInTheDocument()
    expect(screen.getByText('Approval approved')).toBeInTheDocument()
    expect(screen.getByText('specialist.demo')).toBeInTheDocument()
    expect(screen.getByText('RISK-001')).toBeInTheDocument()
  })

  it('shows a filtered-empty state with a clear-filter action', async () => {
    const user = userEvent.setup()
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [createAuditEvent()],
      total: 1,
    })
    renderRoute()
    await user.type(screen.getByTestId('audit-filter-input'), 'nomatch')
    expect(screen.getByTestId('filtered-empty-state')).toBeInTheDocument()
    await user.click(screen.getByTestId('clear-filter-button'))
    expect(screen.queryByTestId('filtered-empty-state')).not.toBeInTheDocument()
    expect(screen.getByTestId('audit-list')).toBeInTheDocument()
  })

  it('labels the client-side filter scope accurately', async () => {
    const user = userEvent.setup()
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [
        createAuditEvent({ id: 'evt-1' }),
        createAuditEvent({ id: 'evt-2' }),
      ],
      total: 2,
    })
    renderRoute()
    await user.type(screen.getByTestId('audit-filter-input'), 'approval')
    expect(screen.getByTestId('audit-filter-note')).toHaveTextContent(
      'does not search the full audit history',
    )
  })

  it('shows an error state with a reload action (no mutation retry)', () => {
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      isError: true,
      error: new Error('boom'),
    })
    renderRoute()
    expect(screen.getByTestId('error-state')).toBeInTheDocument()
    expect(screen.getByTestId('reload-button')).toHaveTextContent(
      'Reload audit log',
    )
  })

  it('traces a correlation ID by populating the page filter', async () => {
    const user = userEvent.setup()
    const correlation = 'aaaa1111-0000-0000-0000-000000000000'
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [createAuditEvent({ id: 'evt-1', correlation_id: correlation })],
      total: 1,
    })
    renderRoute()
    await user.click(screen.getByTestId('trace-correlation-evt-1'))
    expect(screen.getByTestId('audit-filter-input')).toHaveValue(correlation)
  })

  it('opens the read-only detail panel when a row is inspected', async () => {
    const user = userEvent.setup()
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [createAuditEvent({ id: 'evt-1' })],
      total: 1,
    })
    renderRoute()
    await user.click(screen.getByTestId('view-event-evt-1'))
    expect(screen.getByTestId('audit-detail-panel')).toBeInTheDocument()
  })

  it('opens the read-only trace dialog when a row trace is requested', async () => {
    const user = userEvent.setup()
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [createAuditEvent({ id: 'evt-1' })],
      total: 1,
    })
    renderRoute()
    await user.click(screen.getByTestId('trace-event-evt-1'))
    expect(screen.getByTestId('audit-trace-panel')).toBeInTheDocument()
  })

  // WP-DPR1-05 regression: the row-action label formerly used t('trace'),
  // which collided with the nested `trace` dialog object in both audit
  // catalogs — JSON parsing kept the object, i18next returned an
  // object-instead-of-string diagnostic, and the button rendered garbage
  // instead of the human-readable label. The row action now resolves the
  // dedicated `viewTrace` string leaf.
  it('renders the human-readable trace label instead of the key or an object', async () => {
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [createAuditEvent({ id: 'evt-1' })],
      total: 1,
    })
    renderRoute()
    const button = screen.getByTestId('trace-event-evt-1')
    // The visible label is the localized viewTrace string…
    expect(button).toHaveTextContent('Trace')
    // …and never the raw key, an object render, or an i18next diagnostic.
    expect(button.textContent).not.toBe('trace')
    expect(button.textContent).not.toContain('[object Object]')
    expect(button.textContent).not.toContain(
      'returned an object instead of string',
    )
  })

  it('resolves the audit row-action leaf key in every catalog locale', () => {
    for (const locale of ['uk', 'en'] as const) {
      const t = i18n.getFixedT(locale, 'audit')
      expect(t('viewTrace')).toBe(locale === 'uk' ? 'Слід' : 'Trace')
    }
  })

  it('exposes no mutation controls', () => {
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [createAuditEvent()],
      total: 1,
    })
    renderRoute()
    for (const name of [
      'Approve',
      'Reject',
      'Delete',
      'Edit',
      'Execute',
      'Retry',
      'Create',
    ]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
  })

  it('provides accessible filter label and table caption', () => {
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [createAuditEvent()],
      total: 1,
    })
    renderRoute()
    expect(screen.getByLabelText('Filter current page')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('Audit events (newest first)')).toBeInTheDocument()
  })

  it('disables previous on the first page and enables next when more pages exist', () => {
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [createAuditEvent()],
      total: 120,
      limit: 50,
      offset: 0,
    })
    renderRoute()
    expect(screen.getByTestId('prev-page')).toBeDisabled()
    expect(screen.getByTestId('next-page')).toBeEnabled()
    expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 1 of 3')
  })

  it('resets offset when the page size changes', async () => {
    const user = userEvent.setup()
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [createAuditEvent()],
      total: 120,
      limit: 50,
      offset: 50,
    })
    renderRoute()
    await user.selectOptions(screen.getByTestId('audit-page-size'), '25')
    // The hook must be re-invoked with the new limit and a reset offset.
    const lastCall = mockUseAuditEvents.mock.calls[
      mockUseAuditEvents.mock.calls.length - 1
    ]
    expect(lastCall[0]).toBe(25)
    expect(lastCall[1]).toBe(0)
  })

  it('shows a page-out-of-range state instead of "No audit events" when total > 0', () => {
    mockUseAuditEvents.mockReturnValue({
      ...baseList(),
      events: [],
      total: 10,
      limit: 50,
      offset: 0,
    })
    renderRoute()
    expect(screen.queryByText('No audit events')).not.toBeInTheDocument()
    expect(screen.getByTestId('out-of-range-state')).toBeInTheDocument()
    expect(screen.getByTestId('reset-page-button')).toBeInTheDocument()
  })

  it('normalizes an out-of-range offset back to the first page without a request loop', async () => {
    const user = userEvent.setup()
    mockUseAuditEvents.mockImplementation((_limit: number, offset: number) => {
      const total = offset >= 50 ? 20 : 120
      const items = offset < total ? [createAuditEvent({ id: `evt-${offset}` })] : []
      return { ...baseList(), events: items, total, limit: 50, offset }
    })
    renderRoute()
    expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 1 of 3')
    // Page 2 (offset 50): the result set has shrunk so the offset is now out
    // of range. The component must normalize back to offset 0.
    await user.click(screen.getByTestId('next-page'))
    await waitFor(() => {
      expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 1 of 3')
    })
    expect(screen.queryByText('No audit events')).not.toBeInTheDocument()
    const lastCall =
      mockUseAuditEvents.mock.calls[mockUseAuditEvents.mock.calls.length - 1]
    expect(lastCall[1]).toBe(0)
  })
})
