import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CreateApprovalRequestForm } from './create-approval-request-form'
import { SUPPORTED_ACTION_TYPE } from '@/lib/approval-api'

const VALID_UUID = '11111111-2222-3333-4444-555555555555'

function fillForm() {
  fireEvent.change(screen.getByTestId('create-recommendation-id'), {
    target: { value: VALID_UUID },
  })
  fireEvent.change(screen.getByTestId('create-risk-id'), {
    target: { value: 'RISK-001' },
  })
  fireEvent.change(screen.getByTestId('create-component-code'), {
    target: { value: 'CTRL-X4' },
  })
  fireEvent.change(screen.getByTestId('create-quantity'), {
    target: { value: '250' },
  })
}

describe('CreateApprovalRequestForm', () => {
  it('disables submit until all fields are valid', () => {
    render(<CreateApprovalRequestForm onCreate={vi.fn()} />)
    expect(screen.getByTestId('create-submit')).toBeDisabled()
    fillForm()
    expect(screen.getByTestId('create-submit')).not.toBeDisabled()
  })

  it('requires a valid UUID for recommendation id', () => {
    render(<CreateApprovalRequestForm onCreate={vi.fn()} />)
    fillForm()
    fireEvent.change(screen.getByTestId('create-recommendation-id'), {
      target: { value: 'not-a-uuid' },
    })
    expect(screen.getByTestId('create-submit')).toBeDisabled()
  })

  it('requires a positive quantity', () => {
    render(<CreateApprovalRequestForm onCreate={vi.fn()} />)
    fillForm()
    fireEvent.change(screen.getByTestId('create-quantity'), {
      target: { value: '0' },
    })
    expect(screen.getByTestId('create-submit')).toBeDisabled()
  })

  it('submits with the fixed action type and entered fields', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined)
    render(<CreateApprovalRequestForm onCreate={onCreate} />)
    fillForm()
    fireEvent.click(screen.getByTestId('create-submit'))
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledWith({
        recommendation_id: VALID_UUID,
        risk_id: 'RISK-001',
        action_type: SUPPORTED_ACTION_TYPE,
        component_code: 'CTRL-X4',
        quantity: '250',
      })
    })
  })

  it('shows a success message after creation', async () => {
    render(<CreateApprovalRequestForm onCreate={vi.fn().mockResolvedValue(undefined)} />)
    fillForm()
    fireEvent.click(screen.getByTestId('create-submit'))
    await waitFor(() => {
      expect(screen.getByTestId('create-success')).toBeInTheDocument()
    })
  })

  it('shows a safe error message on duplicate failure', async () => {
    const onCreate = vi.fn().mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 409,
        data: { detail: { error: 'approval_request_duplicate' } },
      },
    })
    render(<CreateApprovalRequestForm onCreate={onCreate} />)
    fillForm()
    fireEvent.click(screen.getByTestId('create-submit'))
    await waitFor(() => {
      expect(screen.getByTestId('create-error')).toHaveTextContent(
        'A pending request already exists for this action.',
      )
    })
  })

  it('prevents duplicate submission while a create is in flight', async () => {
    let resolveCreate: () => void = () => {}
    const onCreate = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveCreate = resolve
        }),
    )
    render(<CreateApprovalRequestForm onCreate={onCreate} />)
    fillForm()
    fireEvent.click(screen.getByTestId('create-submit'))
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledTimes(1)
    })
    // The submit button is disabled (and shows a pending label) while in flight.
    expect(screen.getByTestId('create-submit')).toBeDisabled()
    resolveCreate()
  })
})
