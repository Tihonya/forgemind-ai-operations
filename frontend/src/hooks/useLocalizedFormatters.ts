/**
 * Localized formatting integration (WP-UX-UA-01 remediation F-1).
 *
 * React integration layer that connects the ACTIVE locale to the pure
 * ``formatDate`` helper from ``@/lib/format``:
 * - obtains the reactive active locale from ``useActiveLocale`` (the
 *   existing locale/i18n integration — no second global store);
 * - exposes a localized ``formatDate`` callback for the current locale;
 * - re-renders mounted consumers after any ``languageChanged`` — the same
 *   mount reflects the new locale without a manual reload;
 * - passes only sanitized supported locale codes (``uk`` | ``en``) to the
 *   pure formatter, which maps them to ``uk-UA`` / ``en-US`` with
 *   ``Europe/Kyiv`` preserved.
 *
 * ``@/lib/format`` stays a pure module with NO React imports and NO access
 * to a mutable global locale: real display call sites obtain the active
 * locale here and pass it explicitly through to the pure helper.
 */

import { useCallback } from 'react'

import type { SupportedLocale } from '@/i18n/types'
import { useActiveLocale } from '@/i18n/use-locale'
import { formatDate } from '@/lib/format'

export interface UseLocalizedFormattersResult {
  /** The reactive active locale (uk | en). */
  locale: SupportedLocale
  /** ``formatDate`` bound to the reactive active locale. */
  formatDate: (isoDate: string) => string
}

/**
 * Localized formatters for the active locale.
 *
 * The returned ``formatDate`` is stable for a given locale (a new callback
 * only after the locale changes) and always formats through the CURRENT
 * active locale — never the helper's Ukrainian default in a React display
 * context.
 */
export function useLocalizedFormatters(): UseLocalizedFormattersResult {
  const { locale } = useActiveLocale()
  const formatDateForLocale = useCallback(
    (isoDate: string) => formatDate(isoDate, locale),
    [locale],
  )
  return { locale, formatDate: formatDateForLocale }
}