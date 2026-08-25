/**
 * Supported-locale contract for the ForgeMind presentation layer.
 *
 * Product-language contract (DEC-059 / WP-UX-UA-01):
 * - ``uk`` is the default locale; ``en`` is the secondary locale.
 * - Only these two codes are ever presented to, or accepted from,
 *   persistence. Unknown or malformed stored values fall back to ``uk``.
 * - API enums, database values, role codes, event codes, status codes,
 *   correlation IDs and persisted identifiers remain English machine
 *   values and are NEVER translated here.
 */

export const SUPPORTED_LOCALES = ['uk', 'en'] as const

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]

export const DEFAULT_LOCALE: SupportedLocale = 'uk'

export const FALLBACK_LOCALE: SupportedLocale = 'uk'

/**
 * The display locale for each supported application locale:
 * - Ukrainian uses ``uk-UA``;
 * - English uses ``en-US`` unless repository evidence requires another
 *   (none found at WP-UX-UA-01; revisit in WP-UX-UA-03 if call sites
 *   expect a different English convention).
 */
export const DISPLAY_LOCALES: Record<SupportedLocale, string> = {
  uk: 'uk-UA',
  en: 'en-US',
}

/**
 * Guard: is a runtime string a supported locale code?
 */
export function isSupportedLocale(value: unknown): value is SupportedLocale {
  return (
    typeof value === 'string' &&
    (SUPPORTED_LOCALES as readonly string[]).includes(value)
  )
}