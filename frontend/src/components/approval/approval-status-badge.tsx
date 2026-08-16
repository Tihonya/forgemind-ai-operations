/**
 * Approval-status badge (WP-REC-04D).
 *
 * Compact, readable badge for the single-shot approval lifecycle
 * (PENDING / APPROVED / REJECTED). Unknown statuses fall back to neutral
 * styling (no crash, no silent skip).
 */

const STATUS_STYLES: Record<string, string> = {
  PENDING: 'bg-amber-600/20 text-amber-300 border-amber-600/40',
  APPROVED: 'bg-green-600/20 text-green-300 border-green-600/40',
  REJECTED: 'bg-red-600/20 text-red-300 border-red-600/40',
}

const FALLBACK_STYLE = 'bg-steel-600/20 text-steel-300 border-steel-600/40'

interface ApprovalStatusBadgeProps {
  status: string
}

export function ApprovalStatusBadge({ status }: ApprovalStatusBadgeProps) {
  const style = STATUS_STYLES[status] ?? FALLBACK_STYLE
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${style}`}
      data-testid="approval-status-badge"
      data-status={status}
    >
      {status || 'UNKNOWN'}
    </span>
  )
}
