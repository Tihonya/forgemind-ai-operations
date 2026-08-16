import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuditEventDetail } from './audit-event-detail'
import { useAuditEvent } from '@/hooks/use-audit-events'
import { createAuditEvent } from '@/test/fixtures/audit-contract'

vi.mock('@/hooks/use-audit-events', () => ({
  useAuditEvent: vi.fn(),
}))

const mockUseAuditEvent = vi.mocked(useAuditEvent)

function baseDetail() {
  return {
    event: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuditEvent.mockReturnValue(baseDetail())
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  })
})

describe('AuditEventDetail', () => {
  it('renders nothing when no event is selected', () => {
    const { container } = render(<AuditEventDetail eventId={null} onClose={vi.fn()} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows a loading state while the detail is loading', () => {
    mockUseAuditEvent.mockReturnValue({ ...baseDetail(), isLoading: true })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    expect(screen.getByTestId('audit-detail-loading')).toBeInTheDocument()
  })

  it('shows a safe error state with a reload action (not a mutation retry)', () => {
    mockUseAuditEvent.mockReturnValue({
      ...baseDetail(),
      isError: true,
      error: new Error('boom'),
    })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    expect(screen.getByTestId('audit-detail-error')).toBeInTheDocument()
    expect(screen.getByTestId('audit-detail-reload')).toBeInTheDocument()
  })

  it('presents the safe event fields and System actor when actor is null', () => {
    mockUseAuditEvent.mockReturnValue({
      ...baseDetail(),
      event: createAuditEvent({
        actor_username: null,
        before_summary: { status: 'PENDING' },
        after_summary: { status: 'APPROVED' },
        event_metadata: { reason: 'sufficient' },
      }),
    })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    expect(screen.getByTestId('detail-actor')).toHaveTextContent('System')
    expect(screen.getByTestId('detail-entity-type')).toHaveTextContent(
      'Approval request',
    )
    expect(screen.getByTestId('detail-entity-id')).toHaveTextContent(
      '33333333-4444-5555-6666-777777777777',
    )
    expect(screen.getByTestId('detail-correlation-id')).toHaveTextContent(
      '11111111-2222-3333-4444-555555555555',
    )
    expect(screen.getByTestId('detail-risk-id')).toHaveTextContent('RISK-001')
    expect(screen.getByText('PENDING')).toBeInTheDocument()
    expect(screen.getByText('APPROVED')).toBeInTheDocument()
    expect(screen.getByText('sufficient')).toBeInTheDocument()
  })

  it('preserves the [REDACTED] sentinel in structured fields', () => {
    mockUseAuditEvent.mockReturnValue({
      ...baseDetail(),
      event: createAuditEvent({
        event_metadata: { api_key: '[REDACTED]' },
      }),
    })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    expect(screen.getByText('[REDACTED]')).toBeInTheDocument()
  })

  it('exposes no mutation controls', () => {
    mockUseAuditEvent.mockReturnValue({
      ...baseDetail(),
      event: createAuditEvent(),
    })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    expect(screen.queryByText(/approve/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/reject/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/delete/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/edit/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/execute/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^retry$/i)).not.toBeInTheDocument()
  })

  it('never renders a binding hash, prompt, or raw secret label', () => {
    mockUseAuditEvent.mockReturnValue({
      ...baseDetail(),
      event: createAuditEvent({
        event_metadata: { note: 'safe' },
      }),
    })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    expect(screen.queryByText(/binding[_ ]hash/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/access[_ ]token/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/authorization/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/password/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/api[_ ]key/i)).not.toBeInTheDocument()
  })

  it('copies the correlation ID via a labeled control', () => {
    mockUseAuditEvent.mockReturnValue({
      ...baseDetail(),
      event: createAuditEvent(),
    })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    const button = screen.getByTestId('copy-correlation-ID')
    expect(button).toHaveAccessibleName('Copy correlation ID')
    fireEvent.click(button)
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      '11111111-2222-3333-4444-555555555555',
    )
  })
})
