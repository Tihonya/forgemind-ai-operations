/**
 * StatusTransition (WP-UX-UA-04, Phase 5 readiness): presentation primitive
 * for a real status transition.
 *
 * Renders: Попередній стан → Новий стан
 * (from_status → to_status) with optional actor, timestamp, reason, and
 * correlation ID. Both machine codes are preserved as optional technical
 * metadata; values are localized through the registry for the given domain.
 *
 * READINESS BOUNDARY (documented in the PR body): the current API does NOT
 * provide a real transition pair, so this primitive must not be mounted in
 * the live UI — there is no backend field to feed it. It is a tested,
 * import-ready Phase-5 primitive that prevents fabricated transitions.
 */

import { ChevronRight } from 'lucide-react'

import StatusBadge from '@/components/status/StatusBadge'
import { useStatusTranslation } from '@/lib/status-i18n'
import type { StatusDomain } from '@/lib/status-registry'

interface StatusTransitionProps {
  domain: StatusDomain
  fromStatus?: string | null
  toStatus?: string | null
  /** Actor (username) when supplied by existing data. */
  actor?: string | null
  /** Timestamp when supplied by existing data (already-formatted). */
  timestamp?: string | null
  /** Reason/comment when supplied by existing data. */
  reason?: string | null
  /** Correlation ID when supplied by existing data. */
  correlationId?: string | null
  testId?: string
}

/**
 * Render a status transition pair. Requires BOTH statuses — if either is
 * missing the component renders nothing rather than fabricate a transition.
 */
export default function StatusTransition({
  domain,
  fromStatus,
  toStatus,
  actor,
  timestamp,
  reason,
  correlationId,
  testId = 'status-transition',
}: StatusTransitionProps) {
  const { t } = useStatusTranslation()

  if (!fromStatus || !toStatus) return null

  return (
    <div className="space-y-2" data-testid={testId}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge domain={domain} code={fromStatus} testId={`${testId}-from`} />
        <ChevronRight className="size-4 shrink-0 text-steel-500" aria-hidden="true" />
        <StatusBadge domain={domain} code={toStatus} testId={`${testId}-to`} />
      </div>
      {(actor || timestamp || reason || correlationId) && (
        <dl className="grid gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-2">
          {actor && (
            <div className="flex flex-wrap gap-1">
              <dt className="font-medium">{t('transition.actor')}</dt>
              <dd>{actor}</dd>
            </div>
          )}
          {timestamp && (
            <div className="flex flex-wrap gap-1">
              <dt className="font-medium">{t('transition.time')}</dt>
              <dd>{timestamp}</dd>
            </div>
          )}
          {reason && (
            <div className="flex flex-wrap gap-1 sm:col-span-2">
              <dt className="font-medium">{t('transition.reason')}</dt>
              <dd>{reason}</dd>
            </div>
          )}
          {correlationId && (
            <div className="flex flex-wrap gap-1 sm:col-span-2">
              <dt className="font-medium">{t('transition.correlationId')}</dt>
              <dd className="break-all font-mono">{correlationId}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  )
}