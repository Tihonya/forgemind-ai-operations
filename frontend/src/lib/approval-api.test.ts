import { describe, expect, it } from 'vitest'
import type { AxiosError } from 'axios'
import {
  formatActionType,
  getApprovalErrorCode,
  getApprovalErrorMessage,
  SUPPORTED_ACTION_TYPE,
} from '@/lib/approval-api'

/**
 * Build a minimal AxiosError-shaped object (isAxiosError: true) so the
 * error-mapping helpers can be exercised without a live HTTP call.
 */
function axiosError(status: number, detail?: unknown): AxiosError {
  return {
    isAxiosError: true,
    response: {
      status,
      data: detail !== undefined ? { detail } : undefined,
    },
  } as unknown as AxiosError
}

describe('formatActionType', () => {
  it('maps the supported action type to a human label', () => {
    expect(formatActionType(SUPPORTED_ACTION_TYPE)).toBe(
      'Create procurement task',
    )
  })

  it('falls back to the raw value for unknown action types', () => {
    expect(formatActionType('SOME_OTHER_ACTION')).toBe('SOME_OTHER_ACTION')
  })
})

describe('getApprovalErrorCode', () => {
  it('extracts the stable error code from the detail body', () => {
    const error = axiosError(409, { error: 'approval_request_not_pending' })
    expect(getApprovalErrorCode(error)).toBe('approval_request_not_pending')
  })

  it('returns null for non-axios errors', () => {
    expect(getApprovalErrorCode(new Error('boom'))).toBeNull()
  })

  it('returns null for bodies without an error code', () => {
    expect(getApprovalErrorCode(axiosError(400, undefined))).toBeNull()
  })
})

describe('getApprovalErrorMessage', () => {
  it('maps an already-decided conflict to a safe message', () => {
    const error = axiosError(409, { error: 'approval_request_not_pending' })
    expect(getApprovalErrorMessage(error)).toBe(
      'This request has already been decided.',
    )
  })

  it('maps self-decision to a safe message', () => {
    const error = axiosError(403, { error: 'self_decision_forbidden' })
    expect(getApprovalErrorMessage(error)).toBe(
      'You cannot decide your own request.',
    )
  })

  it('maps a duplicate to a safe message', () => {
    const error = axiosError(409, { error: 'approval_request_duplicate' })
    expect(getApprovalErrorMessage(error)).toBe(
      'A pending request already exists for this action.',
    )
  })

  it('maps a binding/parameter mismatch to a safe message', () => {
    const error = axiosError(422, { error: 'risk_action_parameters_mismatch' })
    expect(getApprovalErrorMessage(error)).toBe(
      'The action parameters do not match the current risk.',
    )
  })

  it('maps a scoped-out/missing 404 without disclosing existence', () => {
    const error = axiosError(404, { error: 'approval_request_not_found' })
    const message = getApprovalErrorMessage(error)
    expect(message).toBe('The approval request was not found.')
    // The message must not distinguish scoped-out from missing, nor leak any
    // raw identifier or access-grant detail.
    expect(message).not.toMatch(/uuid|record exists|access|forbidden|id=/i)
  })

  it('maps a generic 404 without a code to a safe not-found message', () => {
    expect(getApprovalErrorMessage(axiosError(404, undefined))).toBe(
      'The requested record was not found.',
    )
  })

  it('maps a network error (no response) to a reachability message', () => {
    const error = {
      isAxiosError: true,
      response: undefined,
    } as unknown as AxiosError
    expect(getApprovalErrorMessage(error)).toBe(
      'Unable to reach the server. Please try again.',
    )
  })

  it('falls back to a generic message for unknown errors', () => {
    expect(getApprovalErrorMessage(new Error('boom'))).toBe(
      'An unexpected error occurred. Please try again.',
    )
  })
})
