/**
 * StatusEntityContext (WP-UX-UA-04): labels which state machine owns a
 * status, so statuses from different domains are never conflated.
 *
 * Maps a status domain to a localized entity-context heading from the
 * ``status`` catalog (``entity.<domain>``). Intended Ukrainian product
 * language examples:
 *   Стан виконання процесу · Стан кроку · Рішення щодо погодження ·
 *   Рівень ризику · Стан даних
 */

import { type StatusDomain } from '@/lib/status-registry'
import { useStatusTranslation } from '@/lib/status-i18n'

export interface StatusEntityContextProps {
  domain: StatusDomain
  /** Optional custom entity label (e.g. a concrete plan code). */
  context?: string
  /** Render as a small uppercase heading (default) or inline text. */
  variant?: 'heading' | 'inline'
  testId?: string
}

/**
 * Render a localized domain-owner label for status context.
 */
export default function StatusEntityContext({
  domain,
  context,
  variant = 'heading',
  testId = 'status-entity-context',
}: StatusEntityContextProps) {
  const { t } = useStatusTranslation()
  const label = t(`entity.${domain}`)

  if (variant === 'inline') {
    return (
      <span className="text-xs text-steel-500" data-testid={testId}>
        {label}
        {context ? ` — ${context}` : ''}
      </span>
    )
  }

  return (
    <span
      className="text-[10px] font-semibold uppercase tracking-wider text-steel-500"
      data-testid={testId}
    >
      {label}
      {context ? ` — ${context}` : ''}
    </span>
  )
}