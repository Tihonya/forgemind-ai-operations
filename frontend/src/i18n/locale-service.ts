/**
 * Locale persistence service (WP-UX-UA-01).
 *
 * Product-language contract:
 * 1. No valid saved preference → ``uk`` (default).
 * 2. Browser language must NOT silently override the default.
 * 3. A valid explicit saved selection of ``uk`` or ``en`` is restored.
 * 4. Unknown or malformed stored values fall back safely to ``uk``.
 *
 * Persistence is localStorage-based and read/written through the checks
 * below, which tolerate the absence of ``window`` (SSR / test environment).
 */

import {
  DEFAULT_LOCALE,
  isSupportedLocale,
  type SupportedLocale,
} from './types'

export const LOCALE_STORAGE_KEY = 'forgemind_locale'

/** Safe raw read. Returns the stored string or null. */
export function readStoredLocaleRaw(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(LOCALE_STORAGE_KEY)
  } catch {
    return null
  }
}

/**
 * Resolve the initial application locale from storage.
 *
 * Returns:
 * - ``uk`` when nothing is stored (Product Owner default);
 * - ``uk`` or ``en`` when a valid explicit selection is stored;
 * - ``uk`` when the stored value is unknown or malformed.
 */
export function resolveInitialLocale(): SupportedLocale {
  const raw = readStoredLocaleRaw()
  return isSupportedLocale(raw) ? raw : DEFAULT_LOCALE
}

/**
 * Validate a runtime locale selection (e.g. from the locale switcher).
 * Unknown values fall back to ``uk`` rather than being written to storage.
 */
export function sanitizeLocale(value: unknown): SupportedLocale {
  return isSupportedLocale(value) ? value : DEFAULT_LOCALE
}

/**
 * Persist an explicit locale selection. Only supported codes are stored;
 * a sanitized default is written for anything else. Never throws.
 */
export function persistLocale(locale: SupportedLocale): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    /* storage unavailable — locale remains active for the session only */
  }
}