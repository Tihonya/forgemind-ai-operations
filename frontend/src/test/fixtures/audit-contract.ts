import type {
  AuditEventListResponse,
  AuditEventResponse,
} from '@/lib/audit-api'

/**
 * Deterministic audit-event fixture factory (WP-REC-04E).
 *
 * Produces full AuditEventResponse values matching the WP-REC-04B backend wire
 * schema exactly, with sensible defaults and per-test overrides.
 */
export function createAuditEvent(
  overrides: Partial<AuditEventResponse> = {},
): AuditEventResponse {
  return {
    id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    correlation_id: '11111111-2222-3333-4444-555555555555',
    event_type: 'APPROVAL_REQUEST_CREATED',
    actor_id: '22222222-3333-4444-5555-666666666666',
    actor_username: 'manager.demo',
    entity_type: 'APPROVAL_REQUEST',
    entity_id: '33333333-4444-5555-6666-777777777777',
    workflow_run_id: '44444444-5555-6666-7777-888888888888',
    risk_id: 'RISK-001',
    before_summary: null,
    after_summary: null,
    event_metadata: null,
    created_at: '2026-08-16T08:00:00Z',
    ...overrides,
  }
}

/**
 * Deterministic paginated-list fixture matching AuditEventListResponse.
 */
export function createAuditEventList(
  items: AuditEventResponse[] = [],
  overrides: Partial<Omit<AuditEventListResponse, 'items'>> = {},
): AuditEventListResponse {
  return {
    items,
    limit: 50,
    offset: 0,
    total: items.length,
    ...overrides,
  }
}
