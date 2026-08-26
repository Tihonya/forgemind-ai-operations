import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import { LOCALE_STORAGE_KEY } from '@/i18n/locale-service'
import { ApprovalRequestCard } from './approval-request-card'
import { createApprovalRequest } from '@/test/fixtures/approval-contract'

function renderCard(
  props: Partial<{
    canDecide: boolean
    onDecide: (kind: 'approve' | 'reject', comment: string) => Promise<void>
  }> = {},
  request = createApprovalRequest(),
) {
  return render(
    <MemoryRouter>
      <ApprovalRequestCard
        request={request}
        canDecide={props.canDecide ?? false}
        onDecide={props.onDecide ?? vi.fn()}
      />
    </MemoryRouter>,
  )
}

// Deterministic locale-isolated instants for date assertions. The fixture's
// real timestamps are overridden so the locale strings are pinned
// independent of the fixture defaults (F-1 regression coverage).
const REQUESTED_AT = '2026-07-15T22:00:00Z'  // Kyiv: 2026-07-16 01:00 (UTC+3)
const DECIDED_AT = '2026-01-15T22:00:00Z'    // Kyiv: 2026-01-16 00:00 (UTC+2)

describe('ApprovalRequestCard — locale-connected date formatting', () => {
  afterEach(() => {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY)
    act(() => {
      void i18n.changeLanguage('uk')
    })
  })

  it('Ukrainian active → Ukrainian requested date', async () => {
    renderCard({}, createApprovalRequest({ requested_at: REQUESTED_AT }))
    await act(async () => {
      await i18n.changeLanguage('uk')
    })
    expect(screen.getByTestId('requested-at')).toHaveTextContent('16 лип. 2026 р.')
  })

  it('English active → English requested date', async () => {
    renderCard({}, createApprovalRequest({ requested_at: REQUESTED_AT }))
    await act(async () => {
      await i18n.changeLanguage('en')
    })
    expect(screen.getByTestId('requested-at')).toHaveTextContent('Jul 16, 2026')
  })

  it('locale switch rerenders the SAME mounted card (requested + decided dates)', async () => {
    renderCard(
      {},
      createApprovalRequest({
        status: 'APPROVED',
        decided_by: 'decider-1',
        decided_by_username: 'procurement.demo',
        decided_at: DECIDED_AT,
        decision_comment: 'Approved after review.',
        requested_at: REQUESTED_AT,
      }),
    )
    // Ukrainian first.
    await act(async () => {
      await i18n.changeLanguage('uk')
    })
    expect(screen.getByTestId('requested-at')).toHaveTextContent('16 лип. 2026 р.')
    expect(screen.getByText('16 січ. 2026 р.')).toBeInTheDocument()

    // Switch to English on the same mounted card.
    await act(async () => {
      await i18n.changeLanguage('en')
    })
    expect(screen.getByTestId('requested-at')).toHaveTextContent('Jul 16, 2026')
    expect(screen.getByText('on Jan 16, 2026')).toBeInTheDocument()
    expect(screen.queryByText('16 січ. 2026 р.')).not.toBeInTheDocument()

    // And back — same mount throughout.
    await act(async () => {
      await i18n.changeLanguage('uk')
    })
    expect(screen.getByTestId('requested-at')).toHaveTextContent('16 лип. 2026 р.')
  })

  it('approval status localizes, actions and permissions remain unchanged across the switch', async () => {
    renderCard({ canDecide: true }, createApprovalRequest({ requested_at: REQUESTED_AT }))
    await act(async () => {
      await i18n.changeLanguage('uk')
    })
    // Localized Ukrainian status label; the machine code is preserved on
    // the data attribute (never translated).
    expect(screen.getByTestId('approval-status-badge')).toHaveTextContent('Очікує рішення')
    expect(screen.getByTestId('approval-status-badge')).toHaveAttribute('data-code', 'PENDING')
    expect(screen.getByTestId('approve-button')).toBeInTheDocument()
    expect(screen.getByTestId('reject-button')).toBeInTheDocument()

    await act(async () => {
      await i18n.changeLanguage('en')
    })
    expect(screen.getByTestId('approval-status-badge')).toHaveTextContent('Awaiting decision')
    expect(screen.getByTestId('approval-status-badge')).toHaveAttribute('data-code', 'PENDING')
    expect(screen.getByTestId('approve-button')).toBeInTheDocument()
    expect(screen.getByTestId('reject-button')).toBeInTheDocument()
  })
})

describe('ApprovalRequestCard', () => {
  beforeEach(async () => {
    localStorage.setItem('forgemind_locale', 'en')
    await i18n.changeLanguage('en')
  })

  it('renders status, action snapshot, requester, and timestamp', () => {
    renderCard()
    expect(screen.getByTestId('approval-status-badge')).toHaveTextContent(
      'Awaiting decision',
    )
    expect(screen.getByTestId('approval-status-badge')).toHaveAttribute(
      'data-code',
      'PENDING',
    )
    expect(screen.getByTestId('action-type')).toHaveTextContent(
      'Create procurement task',
    )
    expect(screen.getByTestId('component-code')).toHaveTextContent('CTRL-X4')
    expect(screen.getByTestId('quantity')).toHaveTextContent('250')
    expect(screen.getByTestId('risk-id')).toHaveTextContent('RISK-001')
    expect(screen.getByTestId('requester')).toHaveTextContent('manager.demo')
  })

  it('never renders the binding hash or raw internal identifiers', () => {
    const { container } = renderCard()
    const text = container.textContent ?? ''
    expect(text).not.toContain('binding_hash')
    expect(text).not.toContain(createApprovalRequest().binding_hash)
    expect(text).not.toContain(createApprovalRequest().correlation_id)
  })

  it('shows approve/reject controls for a decider on a PENDING request', () => {
    renderCard({ canDecide: true })
    expect(screen.getByTestId('approve-button')).toBeInTheDocument()
    expect(screen.getByTestId('reject-button')).toBeInTheDocument()
  })

  it('does NOT show decision controls for a non-decider on a PENDING request', () => {
    renderCard({ canDecide: false })
    expect(screen.queryByTestId('approve-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('reject-button')).not.toBeInTheDocument()
  })

  it('does NOT show decision controls for a terminal request even for a decider', () => {
    renderCard(
      { canDecide: true },
      createApprovalRequest({
        status: 'APPROVED',
        decided_by: 'decider-1',
        decided_by_username: 'procurement.demo',
        decided_at: '2026-08-15T11:00:00Z',
        decision_comment: 'Approved after review.',
      }),
    )
    expect(screen.queryByTestId('approve-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('reject-button')).not.toBeInTheDocument()
    expect(screen.getByTestId('decided-by')).toHaveTextContent(
      'procurement.demo',
    )
    expect(screen.getByTestId('decision-comment')).toHaveTextContent(
      'Approved after review.',
    )
  })

  it('approve flow requires a comment and calls onDecide', async () => {
    const onDecide = vi.fn().mockResolvedValue(undefined)
    renderCard({ canDecide: true, onDecide })
    fireEvent.click(screen.getByTestId('approve-button'))
    const submit = screen.getByTestId('decision-submit')
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByTestId('decision-comment'), {
      target: { value: 'Looks good' },
    })
    expect(submit).not.toBeDisabled()
    fireEvent.click(submit)
    await waitFor(() => {
      expect(onDecide).toHaveBeenCalledWith('approve', 'Looks good')
    })
  })

  it('reject flow requires a reason and calls onDecide', async () => {
    const onDecide = vi.fn().mockResolvedValue(undefined)
    renderCard({ canDecide: true, onDecide })
    fireEvent.click(screen.getByTestId('reject-button'))
    expect(screen.getByText('Rejection reason')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('decision-comment'), {
      target: { value: 'Out of budget' },
    })
    fireEvent.click(screen.getByTestId('decision-submit'))
    await waitFor(() => {
      expect(onDecide).toHaveBeenCalledWith('reject', 'Out of budget')
    })
  })

  it('prevents duplicate submission while a decision is in flight', async () => {
    let resolveDecision: () => void = () => {}
    const onDecide = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveDecision = resolve
        }),
    )
    renderCard({ canDecide: true, onDecide })
    fireEvent.click(screen.getByTestId('approve-button'))
    fireEvent.change(screen.getByTestId('decision-comment'), {
      target: { value: 'Approving' },
    })
    fireEvent.click(screen.getByTestId('decision-submit'))
    // While pending, the submit button is disabled and onDecide called once.
    await waitFor(() => {
      expect(onDecide).toHaveBeenCalledTimes(1)
    })
    expect(screen.getByTestId('decision-submit')).toBeDisabled()
    resolveDecision()
  })

  it('shows a safe error message when the decision fails (already decided)', async () => {
    const onDecide = vi.fn().mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 409,
        data: { detail: { error: 'approval_request_not_pending' } },
      },
    })
    renderCard({ canDecide: true, onDecide })
    fireEvent.click(screen.getByTestId('approve-button'))
    fireEvent.change(screen.getByTestId('decision-comment'), {
      target: { value: 'Approve' },
    })
    fireEvent.click(screen.getByTestId('decision-submit'))
    await waitFor(() => {
      expect(screen.getByTestId('decision-error')).toHaveTextContent(
        'This request has already been decided.',
      )
    })
  })
})
