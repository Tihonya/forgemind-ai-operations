/**
 * Audit event-type badge (WP-REC-04E).
 *
 * Renders a readable, color-coded badge for every incorporated WP-REC-04B
 * event type. Attempts, successes, failures, approvals, and rejections are
 * visually distinguished; an icon + text label ensure color is not the only
 * signal. Unknown event types degrade to a neutral badge showing the raw
 * value (no crash, no silent skip).
 */

import {
  CheckCircle2,
  FilePlus2,
  FileText,
  XCircle,
} from 'lucide-react'
import type { ElementType } from 'react'

import { formatEventType } from '@/lib/audit-api'

interface BadgeStyle {
  label: string
  icon: ElementType
  className: string
}

const KNOWN_STYLES: Record<string, BadgeStyle> = {
  APPROVAL_REQUEST_CREATED: {
    label: 'Approval request created',
    icon: FilePlus2,
    className: 'bg-sky-600/20 text-sky-300 border-sky-600/40',
  },
  APPROVAL_APPROVED: {
    label: 'Approval approved',
    icon: CheckCircle2,
    className: 'bg-green-600/20 text-green-300 border-green-600/40',
  },
  APPROVAL_REJECTED: {
    label: 'Approval rejected',
    icon: XCircle,
    className: 'bg-red-600/20 text-red-300 border-red-600/40',
  },
  PROCUREMENT_TASK_CREATION_ATTEMPTED: {
    label: 'Procurement task creation attempted',
    icon: FilePlus2,
    className: 'bg-amber-600/20 text-amber-300 border-amber-600/40',
  },
  PROCUREMENT_TASK_CREATED: {
    label: 'Procurement task created',
    icon: CheckCircle2,
    className: 'bg-green-600/20 text-green-300 border-green-600/40',
  },
  PROCUREMENT_TASK_CREATION_FAILED: {
    label: 'Procurement task creation failed',
    icon: XCircle,
    className: 'bg-red-600/20 text-red-300 border-red-600/40',
  },
}

const FALLBACK_STYLE: BadgeStyle = {
  label: '',
  icon: FileText,
  className: 'bg-steel-600/20 text-steel-300 border-steel-600/40',
}

interface AuditEventTypeBadgeProps {
  eventType: string
}

export function AuditEventTypeBadge({ eventType }: AuditEventTypeBadgeProps) {
  const style = KNOWN_STYLES[eventType] ?? FALLBACK_STYLE
  const label = KNOWN_STYLES[eventType]
    ? KNOWN_STYLES[eventType].label
    : formatEventType(eventType)
  const Icon = style.icon

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium ${style.className}`}
      data-testid="audit-event-type-badge"
      data-event-type={eventType}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      <span>{label}</span>
    </span>
  )
}
