/**
 * Pure client-side page filter for audit events (WP-REC-04E).
 *
 * The backend audit API exposes only ``limit``/``offset``; it supports no
 * server-side event-type/entity/actor/correlation/time filters. This filter
 * is therefore strictly local to a single loaded page and must be labeled as
 * page-scoped (not history-scoped) wherever it is surfaced.
 */

import {
  formatEntityType,
  formatEventType,
  type AuditEventResponse,
} from '@/lib/audit-api'

export function filterAuditEvents(
  events: AuditEventResponse[],
  query: string,
): AuditEventResponse[] {
  const q = query.trim().toLowerCase()
  if (!q) return events
  return events.filter((event) => {
    const haystack = [
      event.event_type,
      formatEventType(event.event_type),
      event.entity_type,
      formatEntityType(event.entity_type),
      event.entity_id,
      event.actor_username ?? '',
      event.correlation_id,
      event.risk_id ?? '',
      event.workflow_run_id ?? '',
    ]
      .join(' ')
      .toLowerCase()
    return haystack.includes(q)
  })
}
