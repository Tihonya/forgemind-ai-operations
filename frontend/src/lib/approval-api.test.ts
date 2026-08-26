import { describe, expect, it } from 'vitest'
import type { AxiosError } from 'axios'
import {
  getApprovalErrorCode,
  getApprovalErrorKey,
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

describe('SUPPORTED_ACTION_TYPE', () => {
  it('remains the single controlled machine enum value (never translated)', () => {
    expect(SUPPORTED_ACTION_TYPE).toBe('CREATE_PROCUREMENT_TASK')
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

describe('getApprovalErrorKey', () => {
  it('maps an already-decided conflict to a safe key', () => {
    const error = axiosError(409, { error: 'approval_request_not_pending' })
    expect(getApprovalErrorKey(error)).toBe(
      'approval:errors.approvalRequestNotPending',
    )
  })

  it('maps self-decision to a safe key', () => {
    const error = axiosError(403, { error: 'self_decision_forbidden' })
    expect(getApprovalErrorKey(error)).toBe(
      'approval:errors.selfDecisionForbidden',
    )
  })

  it('maps a duplicate to a safe key', () => {
    const error = axiosError(409, { error: 'approval_request_duplicate' })
    expect(getApprovalErrorKey(error)).toBe(
      'approval:errors.approvalRequestDuplicate',
    )
  })

  it('maps a binding/parameter mismatch to a safe key', () => {
    const error = axiosError(422, { error: 'risk_action_parameters_mismatch' })
    expect(getApprovalErrorKey(error)).toBe(
      'approval:errors.riskActionParametersMismatch',
    )
  })

  it('maps a scoped-out/missing 404 without disclosing existence', () => {
    const error = axiosError(404, { error: 'approval_request_not_found' })
    const key = getApprovalErrorKey(error)
    expect(key).toBe('approval:errors.approvalRequestNotFound')
    // The key must not distinguish scoped-out from missing, nor leak any
    // raw identifier or access-grant detail.
    expect(key).not.toMatch(/uuid|record exists|access|forbidden|id=/i)
  })

  it('maps a generic 404 without a code to a safe not-found key', () => {
    expect(getApprovalErrorKey(axiosError(404, undefined))).toBe(
      'common:errors.notFound',
    )
  })

  it('maps a network error (no response) to a reachability key', () => {
    const error = {
      isAxiosError: true,
      response: undefined,
    } as unknown as AxiosError
    expect(getApprovalErrorKey(error)).toBe(
      'common:errors.serverUnreachable',
    )
  })

  it('falls back to a generic key for unknown errors', () => {
    expect(getApprovalErrorKey(new Error('boom'))).toBe(
      'common:errors.unexpected',
    )
  })
})
