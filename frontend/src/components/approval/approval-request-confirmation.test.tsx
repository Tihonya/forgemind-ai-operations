import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import i18n from '@/i18n'
import {
  ApprovalRequestConfirmation,
  type ApprovalPrefill,
} from './approval-request-confirmation'
import { createApprovalRequest } from '@/test/fixtures/approval-contract'
import type {
  ApprovalRequestCreate,
  ApprovalRequestResponse,
} from '@/lib/approval-api'

beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})

function completePrefill(): ApprovalPrefill {
  return {
    riskId: 'RISK-001',
    componentCode: 'CTRL-X4',
    quantity: '250',
    actionTitle: 'Procure additional CTRL-X4 units',
    actionRationale: 'Deterministic shortage requires additional units.',
    recommendationId: '22222222-3333-4444-5555-666666666666',
    workflowRunId: '33333333-4444-5555-6666-777777777777',
    correlationId: '11111111-2222-3333-4444-555555555555',
  }
}

function renderConfirmation(
  props: Partial<{
    prefill: ApprovalPrefill
    requester: string
    onCreate: (payload: ApprovalRequestCreate) => Promise<ApprovalRequestResponse>
    onCancel: () => void
  }> = {},
) {
  return render(
    <MemoryRouter>
      <ApprovalRequestConfirmation
        prefill={props.prefill ?? completePrefill()}
        requester={props.requester ?? 'manager.demo'}
        onCreate={props.onCreate ?? vi.fn().mockResolvedValue(createApprovalRequest())}
        onCancel={props.onCancel ?? vi.fn()}
      />
    </MemoryRouter>,
  )
}

describe('ApprovalRequestConfirmation', () => {
  it('renders the prefilled business values (no blank UUID input)', () => {
    renderConfirmation()
    expect(screen.getByText('RISK-001')).toBeInTheDocument()
    expect(screen.getByText('CTRL-X4')).toBeInTheDocument()
    expect(screen.getByText('250')).toBeInTheDocument()
    expect(
      screen.getByText('Procure additional CTRL-X4 units'),
    ).toBeInTheDocument()
    expect(screen.getByText('manager.demo')).toBeInTheDocument()
    // No raw recommendation UUID is shown as a primary field.
    expect(
      screen.queryByDisplayValue('22222222-3333-4444-5555-666666666666'),
    ).not.toBeInTheDocument()
  })

  it('hides technical identifiers behind a collapsed expandable details section', () => {
    renderConfirmation()
    const details = screen.getByTestId('confirm-technical')
    expect(details.tagName).toBe('DETAILS')
    // The technical details are collapsed by default (not expanded).
    expect(details).not.toHaveAttribute('open')
  })

  it('submits the correct existing machine identifiers', async () => {
    const onCreate = vi.fn().mockResolvedValue(createApprovalRequest())
    renderConfirmation({ onCreate })
    fireEvent.click(screen.getByTestId('confirm-submit'))
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledTimes(1)
    })
    expect(onCreate).toHaveBeenCalledWith({
      recommendation_id: '22222222-3333-4444-5555-666666666666',
      risk_id: 'RISK-001',
      action_type: 'CREATE_PROCUREMENT_TASK',
      component_code: 'CTRL-X4',
      quantity: '250',
    })
  })

  it('prevents duplicate submission while a request is in flight', async () => {
    let resolveCreate: () => void = () => {}
    const onCreate = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = () => resolve(createApprovalRequest())
        }),
    )
    renderConfirmation({ onCreate })
    const submit = screen.getByTestId('confirm-submit')
    fireEvent.click(submit)
    // Disabled while pending; a second click is ignored.
    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1))
    expect(submit).toBeDisabled()
    resolveCreate()
  })

  it('shows an explanatory state when required data is missing', () => {
    renderConfirmation({
      prefill: { ...completePrefill(), recommendationId: '' },
    })
    expect(screen.getByTestId('confirm-missing')).toBeInTheDocument()
    expect(screen.getByTestId('confirm-submit')).toBeDisabled()
  })

  it('shows the created request and links on success', async () => {
    const created = createApprovalRequest()
    const onCreate = vi.fn().mockResolvedValue(created)
    renderConfirmation({ onCreate })
    fireEvent.click(screen.getByTestId('confirm-submit'))
    await waitFor(() => {
      expect(screen.getByTestId('confirm-success')).toBeInTheDocument()
    })
    expect(screen.getByTestId('confirm-open-request').closest('a')).toHaveAttribute(
      'href',
      `/approval-requests/${created.id}`,
    )
    expect(screen.getByTestId('confirm-open-center').closest('a')).toHaveAttribute(
      'href',
      '/approval-center',
    )
  })
})
