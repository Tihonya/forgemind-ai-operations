/**
 * Audit event-type badge (WP-REC-04E lineage, registry-backed since
 * WP-UX-UA-04).
 *
 * Renders a readable, icon-carrying badge for every incorporated WP-REC-04B
 * event type. Labels now come from the localized status registry (``status``
 * catalog); the per-type icons and a stable all-neutral palette are
 * retained. Attempts, successes, failures, approvals, and rejections are
 * visually distinguished with distinct icons so color is never the only
 * signal. Unknown event types degrade to a neutral badge that preserves the
 * raw value as technical metadata (no crash, no silent skip).
 */

import {
  CheckCircle2,
  FilePlus2,
  FileText,
  XCircle,
} from 'lucide-react'
import type { ElementType } from 'react'

import { useStatusTranslation } from '@/lib/status-i18n'
import { resolveStatus } from '@/lib/status-registry'

/** Per-event non-color cue (icon), retained from the WP-REC-04E surface. */
const EVENT_ICONS: Record<string, ElementType> = {
  APPROVAL_REQUEST_CREATED: FilePlus2,
  APPROVAL_APPROVED: CheckCircle2,
  APPROVAL_REJECTED: XCircle,
  PROCUREMENT_TASK_CREATION_ATTEMPTED: FilePlus2,
  PROCUREMENT_TASK_CREATED: CheckCircle2,
  PROCUREMENT_TASK_CREATION_FAILED: XCircle,
}

interface AuditEventTypeBadgeProps {
  eventType: string;
}

export function AuditEventTypeBadge({ eventType }: AuditEventTypeBadgeProps) {
  const { t } = useStatusTranslation()
  const entry = resolveStatus('auditEvent', eventType)
  const Icon = entry.known ? EVENT_ICONS[entry.code] ?? FileText : FileText
  const label = t(entry.labelKey)
  const showRaw = !entry.known && entry.code !== ''

  return (
    <span
      className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-steel-600/40 bg-steel-700/40 px-2 py-0.5 text-xs font-medium text-steel-300"
      data-testid="audit-event-type-badge"
      data-event-type={eventType}
      data-code={entry.code}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="min-w-0 break-words">{label}</span>
      {showRaw && (
        <span className="ml-0.5 min-w-0 font-mono text-[10px] opacity-70 break-all">
          {entry.code}
        </span>
      )}
    </span>
  )
}