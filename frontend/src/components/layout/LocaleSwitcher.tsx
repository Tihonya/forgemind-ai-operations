/**
 * Accessible locale switcher (WP-UX-UA-01).
 *
 * Two explicit options — `Українська` / `English` — rendered as a simple
 * two-button group. Requirements honoured:
 * - active locale is visually (pressed state) and semantically
 *   (`aria-pressed`) identifiable;
 * - keyboard usable (native buttons);
 * - touch usable with ≥44×44 CSS px targets;
 * - no hover-only interaction;
 * - does NOT navigate away — only changes the active locale;
 * - persists the valid selection and updates `html[lang]` via
 *   ``useActiveLocale``.
 */

import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { SupportedLocale } from '@/i18n/types'
import { useActiveLocale } from '@/i18n/use-locale'

export default function LocaleSwitcher() {
  const { t } = useTranslation('common')
  const { locale, setLocale } = useActiveLocale()

  const ariaLabel = t('languages.ariaLabel')

  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex items-center rounded-md border border-steel-700 bg-steel-900 p-0.5"
    >
      {(['uk', 'en'] as const).map((code) => {
        const active = locale === code
        return (
          <button
            key={code}
            type="button"
            aria-pressed={active}
            aria-label={t(`languages.${code}`)}
            onClick={() => setLocale(code as SupportedLocale)}
            data-testid={`locale-switch-${code}`}
            className={cn(
              'inline-flex min-h-[44px] min-w-[44px] items-center justify-center gap-1.5 rounded px-3 py-2.5 text-sm font-medium',
              'transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
              active
                ? 'bg-primary-600 text-white'
                : 'text-steel-300 hover:bg-steel-800 hover:text-white',
            )}
          >
            <span aria-hidden="true">{localeFullName(code)}</span>
            <span className="uppercase text-[10px] font-semibold tracking-wider opacity-80">
              {code}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/**
 * Compact display names for the switcher buttons. Mirrors the catalog
 * values (translated via ``common.languages``); this local map is the
 * layout-only text ("Українська"/"English") shown under the aria label of
 * the two-option group. Text is non-semantic (aria-hidden) — screen readers
 * announce the full translation via aria-label.
 */
function localeFullName(code: 'uk' | 'en'): string {
  return code === 'uk' ? 'Українська' : 'English'
}