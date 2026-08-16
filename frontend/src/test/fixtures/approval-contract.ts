import type {
  ApprovalRequestResponse,
  ApprovalStatus,
} from '@/lib/approval-api'

/**
 * Deterministic approval-request fixture factory (WP-REC-04D).
 *
 * Produces a full ApprovalRequestResponse matching the backend wire schema,
 * with sensible defaults and per-test overrides.
 */
export function createApprovalRequest(
  overrides: Partial<ApprovalRequestResponse> = {},
): ApprovalRequestResponse {
  return {
    id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    correlation_id: '11111111-2222-3333-4444-555555555555',
    recommendation_id: '22222222-3333-4444-5555-666666666666',
    workflow_run_id: '33333333-4444-5555-6666-777777777777',
    risk_id: 'RISK-001',
    action_type: 'CREATE_PROCUREMENT_TASK',
    action_snapshot: {
      binding_version: 1,
      action_type: 'CREATE_PROCUREMENT_TASK',
      component_code: 'CTRL-X4',
      quantity: '250',
      risk_id: 'RISK-001',
      workflow_run_id: '33333333-4444-5555-6666-777777777777',
      recommendation_id: '22222222-3333-4444-5555-666666666666',
      title: 'Procure additional CTRL-X4 units',
      rationale: 'Deterministic shortage requires additional units.',
    },
    binding_hash: 'a'.repeat(64),
    requested_by: '44444444-5555-6666-7777-888888888888',
    requested_by_username: 'manager.demo',
    status: 'PENDING' as ApprovalStatus,
    decided_by: null,
    decided_by_username: null,
    decision_comment: null,
    requested_at: '2026-08-15T10:00:00Z',
    decided_at: null,
    ...overrides,
  }
}
