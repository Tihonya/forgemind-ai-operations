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
import { isSupportedLocale, type SupportedLocale } from './types'

export function useActiveLocale(): {
  locale: SupportedLocale
  setLocale: (locale: SupportedLocale) => void
} {
  // Resolved once per mount: restores a saved selection or the default
  // (the stored selection, not the module-level language, is authoritative
  // for a mount — the i18n module resolves the same storage source at
  // startup, so a persisted-English boot yields this same 'en' here without
  // any Ukrainian pass).
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
    // Follow locale changes initiated ANYWHERE (the switcher, another mounted
    // consumer, or a direct i18next changeLanguage) so every mount stays
    // synchronized with the active locale — this is what lets localized
    // formatters re-render reactively when the language changes.
    const follow = (lng?: string) => {
      if (isSupportedLocale(lng)) {
        setLocaleState(lng)
      }
    }
    i18n.on('languageChanged', follow)
    return () => {
      i18n.off('languageChanged', follow)
    }
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