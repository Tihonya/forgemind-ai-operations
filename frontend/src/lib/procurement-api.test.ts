import { describe, expect, it } from 'vitest'
import type { AxiosError } from 'axios'
import { getProcurementErrorCode, getProcurementErrorKey } from '@/lib/procurement-api'

function axiosError(status: number, detail?: unknown): AxiosError {
  return {
    isAxiosError: true,
    response: {
      status,
      data: detail !== undefined ? { detail } : undefined,
    },
  } as unknown as AxiosError
}

describe('getProcurementErrorCode', () => {
  it('extracts the stable error code from the detail body', () => {
    expect(getProcurementErrorCode(axiosError(403, { error: 'approver_mismatch' }))).toBe(
      'approver_mismatch',
    )
  })

  it('returns null for non-axios errors', () => {
    expect(getProcurementErrorCode(new Error('boom'))).toBeNull()
  })
})

describe('getProcurementErrorKey', () => {
  it('maps approver mismatch to a safe localized key', () => {
    expect(getProcurementErrorKey(axiosError(403, { error: 'approver_mismatch' }))).toBe(
      'approval:errors.approverMismatch',
    )
  })

  it('maps a not-approved request to a safe localized key', () => {
    expect(
      getProcurementErrorKey(axiosError(409, { error: 'approval_request_not_approved' })),
    ).toBe('approval:errors.approvalRequestNotApproved')
  })

  it('maps a rejected request to a safe localized key', () => {
    expect(
      getProcurementErrorKey(axiosError(409, { error: 'approval_request_rejected' })),
    ).toBe('approval:errors.approvalRequestRejected')
  })

  it('falls back to a generic key for unknown errors', () => {
    expect(getProcurementErrorKey(new Error('boom'))).toBe('common:errors.unexpected')
  })
})
