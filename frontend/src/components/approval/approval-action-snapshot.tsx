/**
 * Safe action snapshot preview for an approval request (WP-REC-04D).
 *
 * Renders only the business-relevant fields: action type, component/item
 * identity, quantity, and the originating risk/recommendation context.
 * Binding hashes, raw payloads, prompts, secrets, and internal identifiers
 * are never shown as UI content.
 */

import { formatQuantity } from '@/lib/utils'
import {
  formatActionType,
  type ApprovalRequestResponse,
} from '@/lib/approval-api'

interface ApprovalActionSnapshotProps {
  request: ApprovalRequestResponse
}

export function ApprovalActionSnapshot({
  request,
}: ApprovalActionSnapshotProps) {
  const { component_code: componentCode, quantity, title } = request.action_snapshot

  return (
    <div
      className="space-y-1.5 text-sm text-steel-400"
      data-testid="approval-action-snapshot"
    >
      <div>
        <span className="font-medium text-steel-300">Action:</span>{' '}
        <span data-testid="action-type">
          {formatActionType(request.action_type)}
        </span>
      </div>
      {componentCode && (
        <div>
          <span className="font-medium text-steel-300">Component:</span>{' '}
          <span data-testid="component-code">{componentCode}</span>
        </div>
      )}
      {quantity && quantity !== '' && (
        <div>
          <span className="font-medium text-steel-300">Quantity:</span>{' '}
          <span data-testid="quantity">{formatQuantity(quantity)}</span>
        </div>
      )}
      <div>
        <span className="font-medium text-steel-300">Risk:</span>{' '}
        <span data-testid="risk-id">{request.risk_id}</span>
      </div>
      {title && (
        <div>
          <span className="font-medium text-steel-300">Recommendation:</span>{' '}
          <span data-testid="recommendation-title">{title}</span>
        </div>
      )}
    </div>
  )
}
