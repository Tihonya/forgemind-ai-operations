import { fireEvent, render, screen, within } from '@testing-library/react'
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

  it('suppresses binding_hash keys and values across approval and procurement metadata', () => {
    const hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    mockUseAuditEvent.mockReturnValue({
      ...baseDetail(),
      event: createAuditEvent({
        event_type: 'PROCUREMENT_TASK_CREATED',
        before_summary: { status: 'PENDING', binding_hash: hash },
        after_summary: {
          task_state: 'READY',
          component_code: 'CTRL-X4',
          quantity: '250',
          binding_hash: hash,
        },
        event_metadata: {
          action_type: 'CREATE_PROCUREMENT_TASK',
          binding_hash: hash,
          approval_request_id: 'req-1',
          nested: { bindingHash: hash, reason: 'sufficient' },
          items: [{ 'binding-hash': hash, component_code: 'CTRL-X9' }],
        },
      }),
    })
    const { container } = render(
      <AuditEventDetail eventId="evt-1" onClose={vi.fn()} />,
    )
    const text = container.textContent ?? ''
    expect(text).not.toContain('binding_hash')
    expect(text).not.toContain('bindingHash')
    expect(text).not.toContain('binding-hash')
    expect(text).not.toContain(hash)
    // Safe neighbouring metadata still renders.
    expect(screen.getByText('task_state:')).toBeInTheDocument()
    expect(screen.getByText('READY')).toBeInTheDocument()
    expect(screen.getAllByText('component_code:')).toHaveLength(2)
    expect(screen.getByText('CTRL-X4')).toBeInTheDocument()
    expect(screen.getByText('CTRL-X9')).toBeInTheDocument()
    expect(screen.getByText('quantity:')).toBeInTheDocument()
    expect(screen.getByText('250')).toBeInTheDocument()
    expect(screen.getByText('approval_request_id:')).toBeInTheDocument()
    expect(screen.getByText('req-1')).toBeInTheDocument()
    expect(screen.getByText('reason:')).toBeInTheDocument()
    expect(screen.getByText('sufficient')).toBeInTheDocument()
    expect(screen.getByText('PENDING')).toBeInTheDocument()
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

  it('moves focus into the dialog on open', () => {
    mockUseAuditEvent.mockReturnValue({ ...baseDetail(), event: createAuditEvent() })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    expect(document.activeElement).toBe(screen.getByTestId('audit-detail-panel'))
  })

  it('traps forward Tab at the last focusable element back to the first', () => {
    mockUseAuditEvent.mockReturnValue({ ...baseDetail(), event: createAuditEvent() })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    const panel = screen.getByTestId('audit-detail-panel')
    const buttons = within(panel).getAllByRole('button')
    const first = buttons[0]
    const last = buttons[buttons.length - 1]
    last.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(first)
  })

  it('traps reverse Tab (Shift+Tab) at the first focusable element back to the last', () => {
    mockUseAuditEvent.mockReturnValue({ ...baseDetail(), event: createAuditEvent() })
    render(<AuditEventDetail eventId="evt-1" onClose={vi.fn()} />)
    const panel = screen.getByTestId('audit-detail-panel')
    const buttons = within(panel).getAllByRole('button')
    const first = buttons[0]
    const last = buttons[buttons.length - 1]
    first.focus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)
  })

  it('closes on Escape', () => {
    mockUseAuditEvent.mockReturnValue({ ...baseDetail(), event: createAuditEvent() })
    const onClose = vi.fn()
    render(<AuditEventDetail eventId="evt-1" onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('restores focus to the opener on close', () => {
    mockUseAuditEvent.mockReturnValue({ ...baseDetail(), event: createAuditEvent() })
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()

    const { rerender } = render(
      <AuditEventDetail eventId="evt-1" onClose={vi.fn()} />,
    )
    expect(document.activeElement).toBe(screen.getByTestId('audit-detail-panel'))

    rerender(<AuditEventDetail eventId={null} onClose={vi.fn()} />)
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })

  it('keeps keyboard focus inside the dialog (background exclusion)', () => {
    mockUseAuditEvent.mockReturnValue({ ...baseDetail(), event: createAuditEvent() })
    render(
      <div>
        <button data-testid="background-button">Background</button>
        <AuditEventDetail eventId="evt-1" onClose={vi.fn()} />
      </div>,
    )
    const panel = screen.getByTestId('audit-detail-panel')
    const buttons = within(panel).getAllByRole('button')
    const last = buttons[buttons.length - 1]
    last.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(buttons[0])
    expect(document.activeElement).not.toBe(
      screen.getByTestId('background-button'),
    )
  })
})
