/**
 * Localized formatting integration (WP-UX-UA-01 remediation F-1; broadened
 * WP-UX-UA-03).
 *
 * React integration layer that connects the ACTIVE locale to the pure
 * formatters from ``@/lib/format``:
 * - obtains the reactive active locale from ``useActiveLocale`` (the
 *   existing locale/i18n integration — no second global store);
 * - exposes localized ``formatDate``, ``formatDateTime`` and
 *   ``formatQuantity`` callbacks for the current locale;
 * - re-renders mounted consumers after any ``languageChanged`` — the same
 *   mount reflects the new locale without a manual reload;
 * - passes only sanitized supported locale codes (``uk`` | ``en``) to the
 *   pure formatters, which map them to ``uk-UA`` / ``en-US`` with
 *   ``Europe/Kyiv`` preserved.
 *
 * ``@/lib/format`` stays a pure module with NO React imports and NO access
 * to a mutable global locale: real display call sites obtain the active
 * locale here and pass it explicitly through to the pure helpers.
 */

import { useCallback } from 'react'

import type { SupportedLocale } from '@/i18n/types'
import { useActiveLocale } from '@/i18n/use-locale'
import { formatDate, formatDateTime, formatQuantity } from '@/lib/format'

export interface UseLocalizedFormattersResult {
  /** The reactive active locale (uk | en). */
  locale: SupportedLocale
  /** ``formatDate`` bound to the reactive active locale. */
  formatDate: (isoDate: string) => string
  /** ``formatDateTime`` bound to the reactive active locale. */
  formatDateTime: (isoDate: string) => string
  /** ``formatQuantity`` bound to the reactive active locale. */
  formatQuantity: (value: string) => string
}

/**
 * Localized formatters for the active locale.
 *
 * The returned callbacks are stable for a given locale (a new callback only
 * after the locale changes) and always format through the CURRENT active
 * locale — never the helper's Ukrainian default in a React display context.
 */
export function useLocalizedFormatters(): UseLocalizedFormattersResult {
  const { locale } = useActiveLocale()
  const formatDateForLocale = useCallback(
    (isoDate: string) => formatDate(isoDate, locale),
    [locale],
  )
  const formatDateTimeForLocale = useCallback(
    (isoDate: string) => formatDateTime(isoDate, locale),
    [locale],
  )
  const formatQuantityForLocale = useCallback(
    (value: string) => formatQuantity(value, locale),
    [locale],
  )
  return {
    locale,
    formatDate: formatDateForLocale,
    formatDateTime: formatDateTimeForLocale,
    formatQuantity: formatQuantityForLocale,
  }
}
