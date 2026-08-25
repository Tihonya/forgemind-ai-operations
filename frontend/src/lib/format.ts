/**
 * Locale-aware date formatting (WP-UX-UA-01).
 *
 * Contract:
 * - default Ukrainian formatting uses locale ``uk-UA``;
 * - English uses ``en-US`` (no repository evidence for another convention);
 * - timezone is explicitly ``Europe/Kyiv`` for user-facing application
 *   timestamps covered by this helper;
 * - the active locale controls display formatting;
 * - fixed instants produce deterministic output (see tests);
 * - invalid/null input follows the existing safe behavior (raw passthrough);
 * - API values remain unchanged; no manual UTC-offset arithmetic anywhere.
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