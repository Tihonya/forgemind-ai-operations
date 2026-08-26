import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'

import i18n from '@/i18n'
import { AuditEventTypeBadge } from './audit-event-type-badge'

beforeEach(async () => {
  await i18n.changeLanguage('en')
})

describe('AuditEventTypeBadge', () => {
  it('renders a human label for every known event type', () => {
    const cases: Array<[string, string]> = [
      ['APPROVAL_REQUEST_CREATED', 'Approval request created'],
      ['APPROVAL_APPROVED', 'Approval approved'],
      ['APPROVAL_REJECTED', 'Approval rejected'],
      ['PROCUREMENT_TASK_CREATION_ATTEMPTED', 'Procurement action creation attempted'],
      ['PROCUREMENT_TASK_CREATED', 'Procurement action created'],
      ['PROCUREMENT_TASK_CREATION_FAILED', 'Procurement action creation failed'],
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
