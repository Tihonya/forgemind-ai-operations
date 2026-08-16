/**
 * Audit-event API client (WP-REC-04E).
 *
 * Strictly read-only typed client for the WP-REC-04B audit-event backend
 * endpoints:
 * - GET /audit-events            — paginated list (limit/offset only).
 * - GET /audit-events/{event_id} — single event detail.
 *
 * The backend exposes NO write method for audit events; this client
 * deliberately exposes no POST/PUT/PATCH/DELETE and no mutation helper. The
 * response types mirror the backend wire schema exactly (no invented fields).
 *
 * Secret-safety: the backend redacts secret-bearing structured fields before
 * persistence, so ``before_summary`` / ``after_summary`` / ``event_metadata``
 * may contain the ``[REDACTED]`` sentinel but never a raw credential. This
 * client carries those structures verbatim and never reinterprets redaction.
 */

import axios from 'axios'
import api from './api'

/**
 * Canonical Phase 6 audit-event taxonomy (WP-REC-04B). The API response is
 * typed as ``string`` so unknown values degrade safely instead of failing
 * type checks; the known set below drives labels/styling.
 */
export const AUDIT_EVENT_TYPES = [
  'APPROVAL_REQUEST_CREATED',
  'APPROVAL_APPROVED',
  'APPROVAL_REJECTED',
  'PROCUREMENT_TASK_CREATION_ATTEMPTED',
  'PROCUREMENT_TASK_CREATED',
  'PROCUREMENT_TASK_CREATION_FAILED',
] as const

export const AUDIT_ENTITY_TYPES = [
  'APPROVAL_REQUEST',
  'PROCUREMENT_TASK',
] as const

/**
 * Human-readable labels for every incorporated audit event type. Unknown
 * values fall back to the raw value (no crash, no silent skip).
 */
export const EVENT_TYPE_LABELS: Record<string, string> = {
  APPROVAL_REQUEST_CREATED: 'Approval request created',
  APPROVAL_APPROVED: 'Approval approved',
  APPROVAL_REJECTED: 'Approval rejected',
  PROCUREMENT_TASK_CREATION_ATTEMPTED: 'Procurement task creation attempted',
  PROCUREMENT_TASK_CREATED: 'Procurement task created',
  PROCUREMENT_TASK_CREATION_FAILED: 'Procurement task creation failed',
}

export const ENTITY_TYPE_LABELS: Record<string, string> = {
  APPROVAL_REQUEST: 'Approval request',
  PROCUREMENT_TASK: 'Procurement task',
}

/** Redaction sentinel the backend writes for secret-bearing values. */
export const REDACTED_SENTINEL = '[REDACTED]'

export interface AuditEventResponse {
  id: string
  correlation_id: string
  event_type: string
  actor_id: string | null
  actor_username: string | null
  entity_type: string
  entity_id: string
  workflow_run_id: string | null
  risk_id: string | null
  before_summary: Record<string, unknown> | null
  after_summary: Record<string, unknown> | null
  event_metadata: Record<string, unknown> | null
  created_at: string
}

export interface AuditEventListResponse {
  items: AuditEventResponse[]
  limit: number
  offset: number
  total: number
}

/** Backend pagination bounds (mirrors the FastAPI Query constraints). */
export const AUDIT_PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const
export const AUDIT_DEFAULT_PAGE_SIZE = 50
export const AUDIT_MAX_PAGE_SIZE = 200
export const AUDIT_MIN_PAGE_SIZE = 1

/**
 * Return a human-readable label for an event type, falling back to the raw
 * value for unknown types.
 */
export function formatEventType(eventType: string): string {
  return EVENT_TYPE_LABELS[eventType] ?? eventType
}

/**
 * Return a human-readable label for an entity type, falling back to the raw
 * value for unknown types.
 */
export function formatEntityType(entityType: string): string {
  return ENTITY_TYPE_LABELS[entityType] ?? entityType
}

/**
 * Canonical nine-item AT-012 trace categories in fixed display order
 * (mirrors the backend ``TRACE_CATEGORY_ORDER``).
 */
export const TRACE_CATEGORY_ORDER = [
  'user_action',
  'deterministic_calculation',
  'retrieval',
  'model_call',
  'structured_validation',
  'recommendation',
  'approval_request',
  'human_decision',
  'write_action',
] as const

/**
 * Human-readable labels for the nine trace categories. Unknown values fall
 * back to the raw value (no crash, no silent skip).
 */
export const TRACE_CATEGORY_LABELS: Record<string, string> = {
  user_action: 'User action',
  deterministic_calculation: 'Deterministic calculation',
  retrieval: 'Retrieval',
  model_call: 'Model call',
  structured_validation: 'Structured validation',
  recommendation: 'Recommendation',
  approval_request: 'Approval request',
  human_decision: 'Human decision',
  write_action: 'Write action',
}

/** A single normalized item in the nine-item trace. */
export interface AuditTraceItem {
  category: string
  category_order: number
  occurred_at: string
  source: 'workflow_step' | 'audit_event'
  source_id: string
  actor: string | null
  entity_type: string | null
  entity_id: string | null
  risk_id: string | null
  summary: Record<string, unknown> | null
}

/** Normalized, correlation-scoped nine-item trace response. */
export interface AuditTraceResponse {
  correlation_id: string
  workflow_run_id: string
  triggered_by: string | null
  final_state: string
  complete: boolean
  is_legacy: boolean
  missing_categories: string[]
  items: AuditTraceItem[]
}

/**
 * Return a human-readable label for a trace category, falling back to the raw
 * value for unknown categories.
 */
export function formatTraceCategory(category: string): string {
  return TRACE_CATEGORY_LABELS[category] ?? category
}

/**
 * Shorten an opaque UUID for compact list display (first 8 characters). The
 * full value remains available in the detail view and via ``title``.
 */
export function formatShortId(value: string): string {
  return value.length > 8 ? `${value.slice(0, 8)}…` : value
}

/**
 * Format an ISO timestamp for consistent, human-readable display
 * (``Aug 16, 2026, 08:00:00``). Falls back to the raw value on parse failure.
 */
export function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

/**
 * Fetch a single page of audit events.
 *
 * The backend orders events deterministically (created_at DESC, id DESC) and
 * supports only ``limit``/``offset``. No other query parameter is sent.
 */
export async function fetchAuditEvents(
  limit = AUDIT_DEFAULT_PAGE_SIZE,
  offset = 0,
): Promise<AuditEventListResponse> {
  const response = await api.get<AuditEventListResponse>('/audit-events', {
    params: { limit, offset },
  })
  return response.data
}

/**
 * Fetch a single audit event by ID (read-only detail).
 */
export async function fetchAuditEvent(
  eventId: string,
): Promise<AuditEventResponse> {
  const response = await api.get<AuditEventResponse>(
    `/audit-events/${eventId}`,
  )
  return response.data
}

/**
 * Fetch the normalized nine-item trace for a correlation ID (read-only).
 *
 * The backend exposes only a GET for the trace; this client deliberately
 * exposes no mutation helper for it.
 */
export async function fetchAuditTrace(
  correlationId: string,
): Promise<AuditTraceResponse> {
  const response = await api.get<AuditTraceResponse>(
    `/audit-trace/${correlationId}`,
  )
  return response.data
}

/**
 * Extract the stable backend error code from an API error response body of
 * shape ``{ detail: { error: "..." } }`` (the repository-standard HTTP error).
 */
export function getAuditErrorCode(error: unknown): string | null {
  if (!axios.isAxiosError(error)) return null
  const detail: unknown = error.response?.data?.detail
  if (detail && typeof detail === 'object') {
    const code = (detail as Record<string, unknown>).error
    if (typeof code === 'string') return code
  }
  return null
}

/**
 * Bounded, safe human-readable messages for audit-read failures. 404 scoped
 * out/missing detail is indistinguishable by design; both surface the same
 * "not found" wording without disclosing whether an event exists.
 */
const ERROR_MESSAGES: Record<string, string> = {
  audit_event_not_found: 'The audit event was not found.',
  audit_trace_not_found: 'The trace was not found.',
}

/**
 * Map an arbitrary error to a safe, human-readable message. Never exposes raw
 * backend identifiers, error details, or whether a scoped-out record exists.
 */
export function getAuditErrorMessage(error: unknown): string {
  const code = getAuditErrorCode(error)
  if (code && ERROR_MESSAGES[code]) {
    return ERROR_MESSAGES[code]
  }
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 401) {
      return 'Your session has expired. Please sign in again.'
    }
    if (error.response?.status === 403) {
      return 'You do not have permission to view the audit log.'
    }
    if (error.response?.status === 404) {
      return 'The requested record was not found.'
    }
    if (!error.response) {
      return 'Unable to reach the server. Please try again.'
    }
  }
  return 'An unexpected error occurred. Please try again.'
}
