import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AuditEventTypeBadge } from './audit-event-type-badge'

describe('AuditEventTypeBadge', () => {
  it('renders a human label for every known event type', () => {
    const cases: Array<[string, string]> = [
      ['APPROVAL_REQUEST_CREATED', 'Approval request created'],
      ['APPROVAL_APPROVED', 'Approval approved'],
      ['APPROVAL_REJECTED', 'Approval rejected'],
      ['PROCUREMENT_TASK_CREATION_ATTEMPTED', 'Procurement task creation attempted'],
      ['PROCUREMENT_TASK_CREATED', 'Procurement task created'],
      ['PROCUREMENT_TASK_CREATION_FAILED', 'Procurement task creation failed'],
    ]
    for (const [type, label] of cases) {
      const { unmount } = render(<AuditEventTypeBadge eventType={type} />)
      expect(screen.getByText(label)).toBeInTheDocument()
      expect(screen.getByTestId('audit-event-type-badge')).toHaveAttribute(
        'data-event-type',
        type,
      )
      unmount()
    }
  })

  it('degrades safely for an unknown event type (raw value shown, no crash)', () => {
    render(<AuditEventTypeBadge eventType="SOME_FUTURE_EVENT" />)
    expect(screen.getByText('SOME_FUTURE_EVENT')).toBeInTheDocument()
    expect(screen.getByTestId('audit-event-type-badge')).toHaveAttribute(
      'data-event-type',
      'SOME_FUTURE_EVENT',
    )
  })

  it('uses an icon alongside the text label (color is not the only signal)', () => {
    const { container } = render(<AuditEventTypeBadge eventType="APPROVAL_APPROVED" />)
    // The badge renders a lucide icon element plus a text label.
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(screen.getByText('Approval approved')).toBeInTheDocument()
  })
})
