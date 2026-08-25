/**
 * i18n initialization (WP-UX-UA-01).
 *
 * Bundled translation catalogs only. No remote translation service; no
 * runtime network loading. No browser-language detector: the Product
 * Owner's Ukrainian default governs until (and unless) the user makes an
 * explicit saved selection.
 *
 * Fail-safe policy:
 * - missing namespaces / keys in ``uk`` fall back to ``en``; missing keys
 *   in ``en`` fall back to the key string itself (never a crash);
 * - ``missingKeyHandler`` is a loud no-op in production (logging only) —
 *   it must NEVER throw; development/test tooling surfaces missing keys
 *   through the catalog-parity test instead.
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enCommon from './locales/en/common.json'
import enDashboard from './locales/en/dashboard.json'
import enShell from './locales/en/shell.json'
import ukCommon from './locales/uk/common.json'
import ukDashboard from './locales/uk/dashboard.json'
import ukShell from './locales/uk/shell.json'
import { DEFAULT_LOCALE } from './types'
import { resolveInitialLocale } from './locale-service'

export const RESOURCES = {
  uk: {
    common: ukCommon,
    shell: ukShell,
    dashboard: ukDashboard,
  },
  en: {
    common: enCommon,
    shell: enShell,
    dashboard: enDashboard,
  },
} as const

/** Namespaces used by this package's catalogs (registry for tests/parity). */
export const CATALOG_NAMESPACES = ['common', 'shell', 'dashboard'] as const

i18n.use(initReactI18next).init({
  resources: RESOURCES,
  lng: DEFAULT_LOCALE,
  // Missing Ukrainian keys fall back to English. English falls back to
  // itself only (a missing en key surfaces the key string, never uk text).
  fallbackLng: {
    uk: ['en'],
    default: ['en'],
  },
  defaultNS: 'common',
  ns: CATALOG_NAMESPACES,
  supportedLngs: ['uk', 'en'],
  interpolation: {
    // React already escapes rendered text; avoid double escaping.
    escapeValue: false,
  },
  missingKeyHandler: (lngs, _ns, key) => {
    // Development visibility. Never throws — production must not crash
    // because of a missing display key.
    console.warn(`[i18n] missing key "${key}" for locales: ${lngs.join(', ')}`)
  },
})

// Synchronize the document locale attribute once at application start so
// it matches the active locale even before the authenticated shell (and the
// locale switcher) mounts — e.g. on the Login route.
if (typeof document !== 'undefined') {
  document.documentElement.lang = resolveInitialLocale()
}

export default i18n