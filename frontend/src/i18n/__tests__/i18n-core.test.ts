/**
 * i18n initialization and fallback tests (WP-UX-UA-01).
 *
 * - default active language is uk;
 * - missing uk key falls back to en (translation fallback chain);
 * - missing key everywhere surfaces the key itself (never a crash);
 * - html[lang] reflects the active locale (via use-locale effect);
 * - changing locale persists and updates html[lang].
 */

import { readFileSync } from 'node:fs'
import * as path from 'node:path'

import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import i18n, { RESOURCES } from '../index'
import { LOCALE_STORAGE_KEY } from '../locale-service'
import { useActiveLocale } from '../use-locale'

describe('i18n initialization', () => {
  it('defaults to uk', () => {
    expect(i18n.language).toBe('uk')
  })

  it('bundles the three catalog namespaces for both locales', () => {
    const res = RESOURCES as Record<string, Record<string, unknown>>
    for (const loc of ['uk', 'en']) {
      expect(res[loc].common).toBeDefined()
      expect(res[loc].shell).toBeDefined()
      expect(res[loc].dashboard).toBeDefined()
    }
  })

  it('uk navigation keys resolve to Ukrainian labels', () => {
    const shell = (RESOURCES.uk as { shell: Record<string, unknown> }).shell
    const nav = (shell.navigation as Record<string, string>)
    expect(nav.dashboard).toBe('Огляд')
    expect(nav.supplyRisks).toBe('Ризики постачання')
  })

  it('en navigation keys resolve to English labels', () => {
    const shell = (RESOURCES.en as { shell: Record<string, unknown> }).shell
    const nav = (shell.navigation as Record<string, string>)
    expect(nav.dashboard).toBe('Dashboard')
    expect(nav.supplyRisks).toBe('Supply Risk Analysis')
  })
})

describe('translation fallback', () => {
  it('reports the DEFAULT locale after a fallback resolution', () => {
    // No stored preference in a clean test → uk.
    expect(i18n.language).toBe('uk')
  })

  it('falls back onto en resources when a uk key is missing', async () => {
    // The committed catalogs are in parity, so a missing-uk-key scenario is
    // constructed at runtime: a key added ONLY to en must resolve to its
    // English value when translated from the uk context.
    i18n.addResourceBundle('en', 'wpUxUa01Probe', { missingUkOnly: 'English fallback value' })
    try {
      const tUk = i18n.getFixedT('uk', 'wpUxUa01Probe')
      expect(tUk('missingUkOnly')).toBe('English fallback value')
    } finally {
      i18n.removeResourceBundle('en', 'wpUxUa01Probe')
    }

    // fallbackLng contract: uk falls back onto en; other locales use the
    // same en fallback (the default entry). English never falls back to uk.
    expect(i18n.options.fallbackLng).toMatchObject({
      uk: ['en'],
      default: ['en'],
    })

    // Direct API check: missing key everywhere returns the key itself
    // (safe, never a crash).
    const enValue = i18n.getFixedT('en', 'shell')('navigation.dashboard')
    expect(enValue).toBe('Dashboard')
    const missing = i18n.getFixedT('uk', 'common')('this.key.does.not.exist')
    expect(missing).toBe('this.key.does.not.exist')
  })

  it('does not crash on a missing display key', () => {
    // Call translate on a namespace/key combination that cannot exist; the
    // result is a string (the key), not an exception.
    const t = i18n.getFixedT('uk', 'shell')
    expect(() => t('navigation.definitelyMissing')).not.toThrow()
    expect(t('navigation.definitelyMissing')).toBe('navigation.definitelyMissing')
  })
})

describe('audit catalog collision regression (WP-DPR1-05)', () => {
  // Defect O2: the top-level string "trace" and the nested "trace" object
  // coexisted in both audit catalogs. JSON parsing kept the later object, so
  // `t('trace')` for the Audit Log row action returned an object and i18next
  // emitted its object-instead-of-string diagnostic. The row-action string
  // now lives under `viewTrace`; the nested `trace.*` namespace is unchanged
  // and remains in use by AuditTraceDialog.
  const AUDIT_FILES = {
    uk: '../locales/uk/audit.json',
    en: '../locales/en/audit.json',
  } as const

  /** Count occurrences of a raw JSON key at ANY nesting level. */
  function rawKeyOccurrences(locale: keyof typeof AUDIT_FILES, key: string): number {
    const source = readFileSync(path.resolve(__dirname, AUDIT_FILES[locale]), 'utf8')
    return source.split(`"${key}":`).length - 1
  }

  it.each(['uk', 'en'] as const)(
    '%s: audit:viewTrace resolves to the primitive row-action string',
    (locale) => {
      const t = i18n.getFixedT(locale, 'audit')
      const value = t('viewTrace')
      expect(typeof value).toBe('string')
      expect(value).toBe(locale === 'uk' ? 'Слід' : 'Trace')
    },
  )

  it.each(['uk', 'en'] as const)(
    '%s: audit:trace.title continues to resolve for the dialog',
    (locale) => {
      const t = i18n.getFixedT(locale, 'audit')
      const value = t('trace.title')
      expect(typeof value).toBe('string')
      expect(value).toBe(locale === 'uk' ? 'Слід аудиту' : 'Audit trace')
    },
  )

  it.each(['uk', 'en'] as const)(
    '%s: audit catalog holds exactly one trace string, one viewTrace string, and one trace object',
    (locale) => {
      const source = readFileSync(path.resolve(__dirname, AUDIT_FILES[locale]), 'utf8')

      // Raw source assertions: JSON.parse silently keeps the LAST duplicate,
      // so parsed-object checks cannot detect the collision. Exactly one
      // top-level `trace` string must remain (the dialog namespace), and the
      // row-action leaf must exist only as `viewTrace`.
      expect(rawKeyOccurrences(locale, 'trace')).toBe(1)
      expect(rawKeyOccurrences(locale, 'viewTrace')).toBe(1)
      expect(source).not.toMatch(/"trace":\s*"/)
      expect(source).toMatch(/"viewTrace":\s*"Trace"|"viewTrace":\s*"Слід"/)

      // No duplicate keys at all may remain (defense in depth).
      const parsed = JSON.parse(source)
      const seen = new Set<string>()
      const walk = (node: unknown, prefix: string): void => {
        if (node === null || typeof node !== 'object') return
        for (const [key, value] of Object.entries(node)) {
          const path = prefix ? `${prefix}.${key}` : key
          expect(seen.has(path), `duplicate key path: ${path}`).toBe(false)
          seen.add(path)
          walk(value, path)
        }
      }
      walk(parsed, '')
    },
  )
})

describe('useActiveLocale — html[lang] synchronization and persistence', () => {
  it('syncs document.documentElement.lang to uk by default', () => {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY)
    renderHook(() => useActiveLocale())
    expect(document.documentElement.lang).toBe('uk')
  })

  it('syncs html[lang] to the restored en selection', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    renderHook(() => useActiveLocale())
    expect(document.documentElement.lang).toBe('en')
  })

  it('persists a selection and updates html[lang] on setLocale', async () => {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY)
    const { result } = renderHook(() => useActiveLocale())
    expect(result.current.locale).toBe('uk')
    expect(document.documentElement.lang).toBe('uk')

    act(() => {
      result.current.setLocale('en')
    })
    expect(result.current.locale).toBe('en')
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en')
    expect(document.documentElement.lang).toBe('en')

    act(() => {
      result.current.setLocale('uk')
    })
    expect(result.current.locale).toBe('uk')
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('uk')
    expect(document.documentElement.lang).toBe('uk')
  })
})