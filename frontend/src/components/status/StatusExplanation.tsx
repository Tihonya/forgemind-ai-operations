/**
 * StatusExplanation (WP-UX-UA-04): plain-language, accessible status
 * explanation for every status value.
 *
 * - Inline text where space permits (``inline`` variant).
 * - Accessible disclosure (details element) for narrow/dense surfaces
 *   (``details`` variant, default): the trigger carries an aria-label, is
 *   keyboard-operable, and needs no hover.
 *
 * Both variants read the registry explanation via the same (domain, code)
 * resolver, so unknown codes show the diagnostic fallback and never invent
 * meaning.
 *
 * Motion reduced: no animation is used (static disclosure marker).
 */

import { resolveStatus, type StatusDomain } from '@/lib/status-registry'
import { useStatusTranslation } from '@/lib/status-i18n'

interface StatusExplanationProps {
  domain: StatusDomain
  code: string | null | undefined
  /** ``inline``: static supporting text; ``details``: disclosure trigger. */
  variant?: 'inline' | 'details'
  /** i18n key for the disclosure trigger's aria-label (status namespace). */
  triggerLabelKey?: string
  /** Optional test id override. */
  testId?: string
}

/**
 * Render a localized status explanation.
 */
export default function StatusExplanation({
  domain,
  code,
  variant = 'details',
  triggerLabelKey = 'explanation.labelTrigger',
  testId = 'status-explanation',
}: StatusExplanationProps) {
  const entry = resolveStatus(domain, code)
  const { t } = useStatusTranslation()
  const description = t(entry.descriptionKey)

  if (variant === 'inline') {
    return (
      <span className="text-xs text-muted-foreground" data-testid={testId}>
        {description}
      </span>
    )
  }

  return (
    <details className="relative" data-testid={testId}>
      <summary
        className="inline-flex min-h-11 cursor-pointer select-none items-center gap-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t(triggerLabelKey)}
      >
        <span aria-hidden="true" className="rounded-full border border-current px-1.5 leading-none">
          ?
        </span>
        <span>{t('explanation.title')}</span>
        <span aria-hidden="true" className="chevron inline-block text-[8px]">
          ▼
        </span>
      </summary>
      <p className="mt-1 rounded-md border border-steel-700 bg-steel-800/60 px-3 py-2 text-xs leading-relaxed text-steel-200">
        {description}
        {!entry.known && entry.code !== '' && (
          <span className="mt-1 block font-mono text-[10px] text-steel-400">
            {entry.code}
          </span>
        )}
      </p>
      <style>{`
        details[open] summary .chevron { transform: rotate(180deg); }
      `}</style>
    </details>
  )
}