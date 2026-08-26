/**
 * Approval-status badge (WP-REC-04D lineage, registry-backed since
 * WP-UX-UA-04).
 *
 * Compact, readable badge for the single-shot approval lifecycle
 * (PENDING / APPROVED / REJECTED). Unknown statuses fail safely: neutral
 * tone with the preserved machine code as technical metadata (no crash, no
 * silent skip).
 */

import StatusBadgeExplained from '@/components/status/StatusBadgeExplained'

interface ApprovalStatusBadgeProps {
  status: string;
}

/**
 * Render a localized approval status badge with a tooltip explanation.
 */
export function ApprovalStatusBadge({ status }: ApprovalStatusBadgeProps) {
  return (
    <StatusBadgeExplained
      domain="approval"
      code={status}
      testId="approval-status-badge"
    />
  )
}