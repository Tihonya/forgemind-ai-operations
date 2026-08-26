/**
 * Procurement-task API client (WP-UX-UA-05).
 *
 * Typed client for the WP-REC-04C procurement-task backend endpoints:
 * - GET  /procurement-tasks            — caller-scoped paginated list.
 * - GET  /procurement-tasks/{task_id}  — single task detail.
 * - POST /procurement-tasks            — create exactly one task from an
 *                                        APPROVED approval request (the
 *                                        approving specialist only).
 *
 * The executable ``component_code`` and ``quantity`` are never accepted from
 * the client; they are re-read from the immutable approval snapshot on the
 * backend. This client mirrors the wire contract exactly and exposes no
 * vendor, supplier, price, or secret-bearing field.
 */

import axios from 'axios'
import api from './api'

/** Synthetic procurement-task state (machine enum, never translated). */
export type ProcurementTaskState = string

export interface ProcurementTaskResponse {
  id: string
  correlation_id: string
  approval_request_id: string
  recommendation_id: string
  workflow_run_id: string
  risk_id: string
  action_type: string
  component_code: string
  quantity: string
  binding_hash: string
  task_state: ProcurementTaskState
  requested_by: string
  requested_by_username: string
  approved_by: string
  approved_by_username: string
  created_at: string
}

export interface ProcurementTaskListResponse {
  items: ProcurementTaskResponse[]
  limit: number
  offset: number
  total: number
}

/**
 * Fetch the caller-scoped page of procurement tasks.
 */
export async function fetchProcurementTasks(
  limit = 200,
  offset = 0,
): Promise<ProcurementTaskListResponse> {
  const response = await api.get<ProcurementTaskListResponse>(
    '/procurement-tasks',
    { params: { limit, offset } },
  )
  return response.data
}

/**
 * Create exactly one procurement task from an APPROVED approval request.
 * Only the specialist who approved the request may execute this action.
 */
export async function createProcurementTask(
  approvalRequestId: string,
): Promise<ProcurementTaskResponse> {
  const response = await api.post<ProcurementTaskResponse>(
    '/procurement-tasks',
    { approval_request_id: approvalRequestId },
  )
  return response.data
}

/** Extract the stable backend error code from a repository-standard error body. */
export function getProcurementErrorCode(error: unknown): string | null {
  if (!axios.isAxiosError(error)) return null
  const detail: unknown = error.response?.data?.detail
  if (detail && typeof detail === 'object') {
    const code = (detail as Record<string, unknown>).error
    if (typeof code === 'string') return code
  }
  return null
}

/**
 * Bounded, safe message KEYS for procurement create/read failures. Maps a
 * stable backend error code to a semantic i18n key resolved by the caller
 * through ``t()`` so the message follows the active locale.
 */
const ERROR_KEY_MAP: Record<string, string> = {
  approval_request_not_found: 'approval:errors.approvalRequestNotFound',
  approval_request_not_approved: 'approval:errors.approvalRequestNotApproved',
  approval_request_rejected: 'approval:errors.approvalRequestRejected',
  approver_mismatch: 'approval:errors.approverMismatch',
  binding_mismatch: 'approval:errors.bindingMismatch',
  procurement_task_not_found: 'approval:errors.procurementTaskNotFound',
  procurement_service_error: 'approval:errors.procurementServiceError',
}

/**
 * Map an arbitrary error to a safe, localized i18n message key.
 */
export function getProcurementErrorKey(error: unknown): string {
  const code = getProcurementErrorCode(error)
  if (code && ERROR_KEY_MAP[code]) {
    return ERROR_KEY_MAP[code]
  }
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 404) {
      return 'common:errors.notFound'
    }
    if (!error.response) {
      return 'common:errors.serverUnreachable'
    }
  }
  return 'common:errors.unexpected'
}
