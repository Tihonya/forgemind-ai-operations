import i18n from '@/i18n'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuditTraceDialog } from './audit-trace-dialog'
import { useAuditTrace } from '@/hooks/use-audit-events'
import type { AuditTraceItem, AuditTraceResponse } from '@/lib/audit-api'

// WP-UX-UA-03: pin the active locale to English so behavior assertions
// against English copy stay stable after the Ukrainian-first migration.
beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})


vi.mock('@/hooks/use-audit-events', () => ({
  useAuditTrace: vi.fn(),
}))

const mockUseAuditTrace = vi.mocked(useAuditTrace)

const CATEGORY_ORDER = [
  'user_action',
  'deterministic_calculation',
  'retrieval',
  'model_call',
  'structured_validation',
  'recommendation',
  'approval_request',
  'human_decision',
  'write_action',
]

let sourceCounter = 0

function createTraceItem(
  overrides: Partial<AuditTraceItem> = {},
): AuditTraceItem {
  sourceCounter += 1
  return {
    category: 'user_action',
    category_order: 1,
    occurred_at: '2026-08-16T08:00:00Z',
    source: 'workflow_step',
    source_id: `aaaaaaaa-0000-0000-0000-${String(sourceCounter).padStart(12, '0')}`,
    actor: 'manager.demo',
    entity_type: null,
    entity_id: null,
    risk_id: null,
    summary: { capture_action: 'start', username: 'manager.demo' },
    ...overrides,
  }
}

function createCompleteTrace(): AuditTraceResponse {
  return {
    correlation_id: '11111111-2222-3333-4444-555555555555',
    workflow_run_id: '22222222-3333-4444-5555-666666666666',
    triggered_by: 'manager.demo',
    final_state: 'COMPLETED',
    complete: true,
    is_legacy: false,
    missing_categories: [],
    items: CATEGORY_ORDER.map((category, index) =>
      createTraceItem({ category, category_order: index + 1 }),
    ),
  }
}

function baseResult() {
  return {
    trace: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }
}

function renderDialog(correlationId: string | null) {
  return render(
    <AuditTraceDialog correlationId={correlationId} onClose={vi.fn()} />,
  )
}

beforeEach(() => {
  sourceCounter = 0
  vi.clearAllMocks()
  mockUseAuditTrace.mockReturnValue(baseResult())
})

describe('AuditTraceDialog', () => {
  it('renders nothing for a null correlation ID', () => {
    renderDialog(null)
    expect(screen.queryByTestId('audit-trace-panel')).not.toBeInTheDocument()
  })

  it('shows a loading state while the trace is loading', () => {
    mockUseAuditTrace.mockReturnValue({
      ...baseResult(),
      isLoading: true,
    })
    renderDialog('11111111-2222-3333-4444-555555555555')
    expect(screen.getByTestId('audit-trace-loading')).toBeInTheDocument()
  })

  it('shows a safe error state with a reload action', () => {
    mockUseAuditTrace.mockReturnValue({
      ...baseResult(),
      isError: true,
      error: new Error('boom'),
    })
    renderDialog('11111111-2222-3333-4444-555555555555')
    expect(screen.getByTestId('audit-trace-error')).toBeInTheDocument()
    expect(screen.getByTestId('audit-trace-reload')).toHaveTextContent(
      'Reload trace',
    )
  })

  it('renders all nine categories in stable order for a complete trace', () => {
    mockUseAuditTrace.mockReturnValue({
      ...baseResult(),
      trace: createCompleteTrace(),
    })
    renderDialog('11111111-2222-3333-4444-555555555555')

    expect(screen.getByTestId('trace-complete-label')).toHaveTextContent(
      'Complete trace — all nine categories captured.',
    )
    expect(screen.queryByTestId('trace-incomplete-label')).not.toBeInTheDocument()
    expect(screen.queryByTestId('trace-missing-categories')).not.toBeInTheDocument()

    const items = screen.getAllByTestId('trace-item')
    expect(items).toHaveLength(9)
    const categories = items.map((item) => item.getAttribute('data-category'))
    expect(categories).toEqual(CATEGORY_ORDER)
  })

  it('labels a legacy-incomplete trace explicitly and does not invent rows', () => {
    const legacyItems = CATEGORY_ORDER.slice(2, 5).map((category, index) =>
      createTraceItem({
        category,
        category_order: index + 3,
        source: 'workflow_step',
      }),
    )
    mockUseAuditTrace.mockReturnValue({
      ...baseResult(),
      trace: {
        correlation_id: '11111111-2222-3333-4444-555555555555',
        workflow_run_id: '22222222-3333-4444-5555-666666666666',
        triggered_by: 'manager.demo',
        final_state: 'COMPLETED',
        complete: false,
        is_legacy: true,
        missing_categories: [
          'user_action',
          'deterministic_calculation',
          'recommendation',
          'approval_request',
          'human_decision',
          'write_action',
        ],
        items: legacyItems,
      },
    })
    renderDialog('11111111-2222-3333-4444-555555555555')

    expect(screen.getByTestId('trace-incomplete-label')).toHaveTextContent(
      'Legacy incomplete trace — created before complete trace capture was introduced.',
    )
    expect(screen.queryByTestId('trace-complete-label')).not.toBeInTheDocument()

    // Missing categories are listed (never fabricated into trace items).
    const missing = screen.getAllByTestId('trace-missing-category')
    expect(missing.map((el) => el.getAttribute('data-category'))).toEqual([
      'user_action',
      'deterministic_calculation',
      'recommendation',
      'approval_request',
      'human_decision',
      'write_action',
    ])

    // Only the three legacy items are rendered — never fabricated to nine.
    const items = screen.getAllByTestId('trace-item')
    expect(items).toHaveLength(3)
  })

  it('uses neutral wording for a current incomplete trace (is_legacy=false)', () => {
    const currentItems = CATEGORY_ORDER.slice(0, 4).map((category, index) =>
      createTraceItem({
        category,
        category_order: index + 1,
        source: 'workflow_step',
      }),
    )
    mockUseAuditTrace.mockReturnValue({
      ...baseResult(),
      trace: {
        correlation_id: '11111111-2222-3333-4444-555555555555',
        workflow_run_id: '22222222-3333-4444-5555-666666666666',
        triggered_by: 'manager.demo',
        final_state: 'FAILED_PROVIDER',
        complete: false,
        is_legacy: false,
        missing_categories: CATEGORY_ORDER.slice(4),
        items: currentItems,
      },
    })
    renderDialog('11111111-2222-3333-4444-555555555555')

    const label = screen.getByTestId('trace-incomplete-label')
    expect(label).toHaveTextContent('Incomplete trace — 4 of 9 categories captured.')
    expect(label).not.toHaveTextContent('created before')
    expect(screen.queryByTestId('trace-complete-label')).not.toBeInTheDocument()

    // No placeholder items fabricated — only the four present categories.
    expect(screen.getAllByTestId('trace-item')).toHaveLength(4)
  })

  it('displays missing categories with human-readable labels in canonical order', () => {
    const currentItems = [
      createTraceItem({ category: 'user_action', category_order: 1 }),
    ]
    mockUseAuditTrace.mockReturnValue({
      ...baseResult(),
      trace: {
        correlation_id: '11111111-2222-3333-4444-555555555555',
        workflow_run_id: '22222222-3333-4444-5555-666666666666',
        triggered_by: 'manager.demo',
        final_state: 'FAILED_PROVIDER',
        complete: false,
        is_legacy: false,
        missing_categories: [
          'deterministic_calculation',
          'retrieval',
          'model_call',
          'structured_validation',
          'recommendation',
          'approval_request',
          'human_decision',
          'write_action',
        ],
        items: currentItems,
      },
    })
    renderDialog('11111111-2222-3333-4444-555555555555')

    const section = screen.getByTestId('trace-missing-categories')
    expect(section).toBeInTheDocument()

    const missing = screen.getAllByTestId('trace-missing-category')
    expect(missing.map((el) => el.getAttribute('data-category'))).toEqual([
      'deterministic_calculation',
      'retrieval',
      'model_call',
      'structured_validation',
      'recommendation',
      'approval_request',
      'human_decision',
      'write_action',
    ])

    // Human-readable labels, not raw keys.
    expect(screen.getByText('Deterministic calculation')).toBeInTheDocument()
    expect(screen.getByText('Model call')).toBeInTheDocument()
    expect(screen.getByText('Structured validation')).toBeInTheDocument()
    expect(screen.getByText('Write action')).toBeInTheDocument()
  })

  it('suppresses binding hashes at every nesting depth in summaries', () => {
    const item = createTraceItem({
      category: 'write_action',
      category_order: 9,
      source: 'audit_event',
      summary: {
        quantity: '8',
        binding_hash: 'top-level-hash',
        nested: {
          bindingHash: 'nested-camel-hash',
          deeper: { 'binding-hash': 'nested-kebab-hash' },
          safe_adjacent: 'keep-me',
        },
        client_secret: '[REDACTED]',
      },
    })
    mockUseAuditTrace.mockReturnValue({
      ...baseResult(),
      trace: {
        correlation_id: '11111111-2222-3333-4444-555555555555',
        workflow_run_id: '22222222-3333-4444-5555-666666666666',
        triggered_by: 'manager.demo',
        final_state: 'COMPLETED',
        complete: false,
        is_legacy: false,
        missing_categories: [],
        items: [item],
      },
    })
    renderDialog('11111111-2222-3333-4444-555555555555')

    expect(screen.queryByText('binding_hash')).not.toBeInTheDocument()
    expect(screen.queryByText('bindingHash')).not.toBeInTheDocument()
    expect(screen.queryByText('binding-hash')).not.toBeInTheDocument()
    expect(screen.queryByText('top-level-hash')).not.toBeInTheDocument()
    expect(screen.queryByText('nested-camel-hash')).not.toBeInTheDocument()
    expect(screen.queryByText('nested-kebab-hash')).not.toBeInTheDocument()

    // Safe adjacent values and the backend [REDACTED] sentinel are preserved.
    expect(screen.getByText(/safe_adjacent/)).toBeInTheDocument()
    expect(screen.getByText('keep-me')).toBeInTheDocument()
    expect(screen.getByText('[REDACTED]')).toBeInTheDocument()
  })

  it('exposes no mutation controls', () => {
    mockUseAuditTrace.mockReturnValue({
      ...baseResult(),
      trace: createCompleteTrace(),
    })
    renderDialog('11111111-2222-3333-4444-555555555555')

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
})
