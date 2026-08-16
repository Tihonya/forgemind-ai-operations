/**
 * Approval-request API client (WP-REC-04D).
 *
 * Typed client for the WP-REC-04A approval-request backend endpoints:
 * - GET  /approval-requests
 * - POST /approval-requests
 * - POST /approval-requests/{request_id}/approve
 * - POST /approval-requests/{request_id}/reject
 *
 * The response schema mirrors the backend wire contract exactly. The UI only
 * ever renders the safe action snapshot fields; binding hashes and internal
 * payloads are carried here for contract fidelity but never displayed.
 */

import axios from 'axios'
import api from './api'

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

/**
 * Immutable action snapshot bound to an approval request (backend JSONB).
 * `quantity` is the canonical decimal string produced by the backend.
 */
export interface ApprovalActionSnapshot {
  binding_version: number
  action_type: string
  component_code: string
  quantity: string
  risk_id: string
  workflow_run_id: string
  recommendation_id: string
  title: string
  rationale: string
}

export interface ApprovalRequestResponse {
  id: string
  correlation_id: string
  recommendation_id: string
  workflow_run_id: string
  risk_id: string
  action_type: string
  action_snapshot: ApprovalActionSnapshot
  binding_hash: string
  requested_by: string
  requested_by_username: string
  status: ApprovalStatus
  decided_by: string | null
  decided_by_username: string | null
  decision_comment: string | null
  requested_at: string
  decided_at: string | null
}

export interface ApprovalRequestListResponse {
  items: ApprovalRequestResponse[]
  limit: number
  offset: number
  total: number
}

export interface ApprovalRequestCreate {
  recommendation_id: string
  risk_id: string
  action_type: string
  component_code: string
  quantity: string
}

export interface DecisionRequest {
  comment: string
}

/**
 * The single controlled action type supported by the MVP (DEC-052 G2/G3).
 * Matches the backend ``SUPPORTED_ACTION_TYPE``.
 */
export const SUPPORTED_ACTION_TYPE = 'CREATE_PROCUREMENT_TASK'

/**
 * Human-readable labels for the bounded action-type allow-list.
 */
const ACTION_TYPE_LABELS: Record<string, string> = {
  CREATE_PROCUREMENT_TASK: 'Create procurement task',
}

/**
 * Return a human-readable label for an action type, falling back to the raw
 * value for unknown types (no crash, no silent skip).
 */
export function formatActionType(actionType: string): string {
  return ACTION_TYPE_LABELS[actionType] ?? actionType
}

/**
 * Fetch the caller-scoped page of approval requests.
 */
export async function fetchApprovalRequests(
  limit = 50,
  offset = 0,
): Promise<ApprovalRequestListResponse> {
  const response = await api.get<ApprovalRequestListResponse>(
    '/approval-requests',
    { params: { limit, offset } },
  )
  return response.data
}

/**
 * Create a PENDING approval request (PRODUCTION_MANAGER).
 */
export async function createApprovalRequest(
  payload: ApprovalRequestCreate,
): Promise<ApprovalRequestResponse> {
  const response = await api.post<ApprovalRequestResponse>(
    '/approval-requests',
    payload,
  )
  return response.data
}

/**
 * Approve a PENDING approval request (PROCUREMENT_SPECIALIST).
 */
export async function approveApprovalRequest(
  requestId: string,
  comment: string,
): Promise<ApprovalRequestResponse> {
  const response = await api.post<ApprovalRequestResponse>(
    `/approval-requests/${requestId}/approve`,
    { comment },
  )
  return response.data
}

/**
 * Reject a PENDING approval request (PROCUREMENT_SPECIALIST).
 */
export async function rejectApprovalRequest(
  requestId: string,
  comment: string,
): Promise<ApprovalRequestResponse> {
  const response = await api.post<ApprovalRequestResponse>(
    `/approval-requests/${requestId}/reject`,
    { comment },
  )
  return response.data
}

/**
 * Extract the stable backend error code from an API error response body of
 * shape ``{ detail: { error: "..." } }`` (the repository-standard HTTP error).
 */
export function getApprovalErrorCode(error: unknown): string | null {
  if (!axios.isAxiosError(error)) return null
  const detail: unknown = error.response?.data?.detail
  if (detail && typeof detail === 'object') {
    const code = (detail as Record<string, unknown>).error
    if (typeof code === 'string') return code
  }
  return null
}

/**
 * Bounded, safe human-readable messages for backend validation/conflict
 * responses. 404 scoped-out and missing records are indistinguishable by
 * design; both surface the same "not found" wording without disclosing
 * whether a record exists.
 */
const ERROR_MESSAGES: Record<string, string> = {
  recommendation_not_found: 'The selected recommendation could not be found.',
  invalid_recommendation_content: 'The recommendation data is not valid.',
  recommendation_not_validated: 'The recommendation has not been validated.',
  risk_not_found_in_recommendation:
    'The risk is not part of the selected recommendation.',
  action_not_found_in_recommendation:
    'The action is not part of the selected recommendation.',
  action_not_requiring_approval: 'This action does not require approval.',
  unsupported_action_type: 'This action type is not supported.',
  risk_action_parameters_mismatch:
    'The action parameters do not match the current risk.',
  approval_request_not_found: 'The approval request was not found.',
  approval_request_not_pending: 'This request has already been decided.',
  approval_request_duplicate:
    'A pending request already exists for this action.',
  self_decision_forbidden: 'You cannot decide your own request.',
  approval_service_error: 'The approval service could not complete the request.',
}

/**
 * Map an arbitrary error to a safe, human-readable message. Never exposes raw
 * backend identifiers, error details, or whether a scoped-out record exists.
 */
export function getApprovalErrorMessage(error: unknown): string {
  const code = getApprovalErrorCode(error)
  if (code && ERROR_MESSAGES[code]) {
    return ERROR_MESSAGES[code]
  }
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 404) {
      return 'The requested record was not found.'
    }
    if (!error.response) {
      return 'Unable to reach the server. Please try again.'
    }
  }
  return 'An unexpected error occurred. Please try again.'
}
