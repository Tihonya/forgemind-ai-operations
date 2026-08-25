/**
 * Safe action snapshot preview for an approval request (WP-REC-04D).
 *
 * Renders only the business-relevant fields: action type, component/item
 * identity, quantity, and the originating risk/recommendation context.
 * Binding hashes, raw payloads, prompts, secrets, and internal identifiers
 * are never shown as UI content.
 *
 * Localized per WP-UX-UA-03; the action type label (machine code → English
 * label, WP-UX-UA-04 scope), component code, risk ID, and recommendation
 * title remain machine content; the quantity formats with the active locale.
 */

import { useTranslation } from 'react-i18next'

import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import {
  formatActionType,
  type ApprovalRequestResponse,
} from '@/lib/approval-api'

interface ApprovalActionSnapshotProps {
  request: ApprovalRequestResponse;
}

export function ApprovalActionSnapshot({
  request,
}: ApprovalActionSnapshotProps) {
  const { t } = useTranslation('approval')
  const { formatQuantity } = useLocalizedFormatters()
  const { component_code: componentCode, quantity, title } = request.action_snapshot

  return (
    <div
      className="space-y-1.5 text-sm text-steel-400"
      data-testid="approval-action-snapshot"
    >
      <div>
        <span className="font-medium text-steel-300">{t('snapshot.action')}</span>{' '}
        <span data-testid="action-type">
          {formatActionType(request.action_type)}
        </span>
      </div>
      {componentCode && (
        <div>
          <span className="font-medium text-steel-300">{t('snapshot.component')}</span>{' '}
          <span data-testid="component-code">{componentCode}</span>
        </div>
      )}
      {quantity && quantity !== '' && (
        <div>
          <span className="font-medium text-steel-300">{t('snapshot.quantity')}</span>{' '}
          <span data-testid="quantity">{formatQuantity(quantity)}</span>
        </div>
      )}
      <div>
        <span className="font-medium text-steel-300">{t('snapshot.risk')}</span>{' '}
        <span data-testid="risk-id">{request.risk_id}</span>
      </div>
      {title && (
        <div>
          <span className="font-medium text-steel-300">{t('snapshot.recommendation')}</span>{' '}
          <span data-testid="recommendation-title">{title}</span>
        </div>
      )}
    </div>
  )
}
