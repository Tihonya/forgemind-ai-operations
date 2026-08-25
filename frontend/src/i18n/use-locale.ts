/**
 * React bindings for the active locale (WP-UX-UA-01).
 *
 * Centralizes the three responsibilities every locale change must fulfill:
 * 1. activate the new locale in i18next (re-renders all translate() hooks);
 * 2. persist the valid selection (localStorage);
 * 3. synchronize ``document.documentElement.lang`` with the active locale.
 *
 * Locale changes must never trigger authentication, navigation or API
 * mutations — this module performs none of those.
 */

import { useCallback, useEffect, useState } from 'react'

import i18n from './index'
import { persistLocale, resolveInitialLocale } from './locale-service'
import type { SupportedLocale } from './types'

export function useActiveLocale(): {
  locale: SupportedLocale
  setLocale: (locale: SupportedLocale) => void
} {
  // Resolved once per mount: restores a saved selection or the default.
  const [locale, setLocaleState] = useState<SupportedLocale>(() =>
    resolveInitialLocale(),
  )

  useEffect(() => {
    void i18n.changeLanguage(locale)
  }, [locale])

  const setLocale = useCallback((next: SupportedLocale) => {
    setLocaleState(next)
    persistLocale(next)
  }, [])

  useEffect(() => {
    // Keep the document locale attribute in sync with the ACTIVE locale.
    const sync = (lng?: string) => {
      if (typeof document === 'undefined') return
      const active =
        typeof lng === 'string' && (lng === 'uk' || lng === 'en')
          ? (lng as SupportedLocale)
          : locale
      document.documentElement.lang = active
    }
    sync(i18n.language || locale)
    i18n.on('languageChanged', sync)
    return () => {
      i18n.off('languageChanged', sync)
    }
  }, [locale])

  return { locale, setLocale }
}