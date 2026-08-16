import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

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
    <ApprovalRequestCard
      request={request}
      canDecide={props.canDecide ?? false}
      onDecide={props.onDecide ?? vi.fn()}
    />,
  )
}

describe('ApprovalRequestCard', () => {
  it('renders status, action snapshot, requester, and timestamp', () => {
    renderCard()
    expect(screen.getByTestId('approval-status-badge')).toHaveTextContent(
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
