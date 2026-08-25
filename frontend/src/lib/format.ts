/**
 * Locale-aware date and number formatting (WP-UX-UA-01; broadened WP-UX-UA-03).
 *
 * Contract:
 * - default Ukrainian formatting uses locale ``uk-UA``;
 * - English uses ``en-US`` (no repository evidence for another convention);
 * - timezone is explicitly ``Europe/Kyiv`` for user-facing application
 *   timestamps covered by these helpers;
 * - the active locale controls display formatting;
 * - fixed instants produce deterministic output (see tests);
 * - invalid/null input follows the existing safe behavior (raw passthrough
 *   for dates, ``0`` for unparseable quantities);
 * - API values remain unchanged; no manual UTC-offset arithmetic anywhere;
 * - no manual thousands-separator / decimal arithmetic — all number and
 *   quantity formatting goes through ``Intl.NumberFormat`` for the active
 *   display locale (``uk-UA`` uses narrow no-break space + comma decimals).
 */

import type { SupportedLocale } from '@/i18n/types'
import { DEFAULT_LOCALE, DISPLAY_LOCALES } from '@/i18n/types'

/** User-facing application timezone (Kyiv, no DST-offset arithmetic). */
export const APP_TIME_ZONE = 'Europe/Kyiv'

/**
 * Format an ISO date string to a short readable date in the given locale
 * (default ``uk`` → ``uk-UA``), rendered in Europe/Kyiv time.
 *
 * Safe behavior: unparseable input (including null/empty strings through
 * ``new Date``) returns the raw input unchanged — it never throws.
 */
export function formatDate(
  isoDate: string,
  locale: SupportedLocale = DEFAULT_LOCALE,
): string {
  try {
    const date = new Date(isoDate)
    if (Number.isNaN(date.getTime())) {
      return isoDate
    }
    return date.toLocaleDateString(DISPLAY_LOCALES[locale], {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      timeZone: APP_TIME_ZONE,
    })
  } catch {
    return isoDate
  }
}

/**
 * Format an ISO date-time string to a full readable date and time in the
 * given locale (default ``uk`` → ``uk-UA``), rendered in Europe/Kyiv time
 * with 24-hour clock. Replaces the previous ad-hoc ``en-US``
 * ``toLocaleString`` call sites (audit timestamps, workflow run timestamps).
 *
 * Safe behavior: unparseable input returns the raw input unchanged.
 */
export function formatDateTime(
  isoDate: string,
  locale: SupportedLocale = DEFAULT_LOCALE,
): string {
  try {
    const date = new Date(isoDate)
    if (Number.isNaN(date.getTime())) {
      return isoDate
    }
    return date.toLocaleString(DISPLAY_LOCALES[locale], {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: APP_TIME_ZONE,
    })
  } catch {
    return isoDate
  }
}

/**
 * Format a decimal quantity string for display using the active display
 * locale. Replaces the previous manual thousands-separator logic: numbers
 * render with the locale's digit-grouping and decimal separators
 * (``uk-UA`` → narrow no-break space + comma; ``en-US`` → comma + period),
 * rounded to at most two fraction digits with trailing zeros removed.
 *
 * Safe behavior: an unparseable value renders ``0`` (matching the prior
 * ``formatQuantity`` contract) — it never throws.
 */
export function formatQuantity(
  value: string,
  locale: SupportedLocale = DEFAULT_LOCALE,
): string {
  const num = Number.parseFloat(value)
  if (Number.isNaN(num)) return '0'
  return new Intl.NumberFormat(DISPLAY_LOCALES[locale], {
    maximumFractionDigits: 2,
  }).format(num)
}
