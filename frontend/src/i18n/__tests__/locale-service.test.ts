/**
 * Locale policy and persistence tests (WP-UX-UA-01 core contract).
 *
 * Product-language contract:
 * 1. no valid saved preference → uk;
 * 2. saved uk → uk;
 * 3. saved en → en;
 * 4. unknown/malformed stored value → uk;
 * 5. locale selection persists;
 * 6. html[lang] follows the active locale (covered in use-locale tests);
 * 7. missing uk key falls back to en (covered in fallback tests).
 */

import { describe, expect, it } from 'vitest'

import {
  LOCALE_STORAGE_KEY,
  persistLocale,
  readStoredLocaleRaw,
  resolveInitialLocale,
  sanitizeLocale,
} from '../locale-service'
import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from '../types'

describe('locale-service — default and fallback policy', () => {
  it('default locale is uk', () => {
    expect(DEFAULT_LOCALE).toBe('uk')
  })

  it('supported locales are exactly uk and en (uk-first order)', () => {
    expect([...SUPPORTED_LOCALES]).toEqual(['uk', 'en'])
  })

  it('resolves uk when nothing is stored', () => {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY)
    expect(resolveInitialLocale()).toBe('uk')
  })

  it('resolves uk when the stored value is malformed', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'ua-UA')
    expect(resolveInitialLocale()).toBe('uk')
  })

  it('resolves uk when the stored value is unknown', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'fr')
    expect(resolveInitialLocale()).toBe('uk')
  })

  it('resolves uk when the stored value is not a string-like JSON value', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, '{"broken":')
    expect(resolveInitialLocale()).toBe('uk')
  })

  it('sanitizeLocale maps unknown values to uk without crashing', () => {
    expect(sanitizeLocale('fr')).toBe('uk')
    expect(sanitizeLocale(null)).toBe('uk')
    expect(sanitizeLocale(42)).toBe('uk')
    expect(sanitizeLocale('en')).toBe('en')
  })

  it('readStoredLocaleRaw returns the raw stored string', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    expect(readStoredLocaleRaw()).toBe('en')
    window.localStorage.removeItem(LOCALE_STORAGE_KEY)
    expect(readStoredLocaleRaw()).toBeNull()
  })
})

describe('locale-service — explicit selection restoration', () => {
  it('saved uk is restored', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'uk')
    expect(resolveInitialLocale()).toBe('uk')
  })

  it('saved en is restored', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    expect(resolveInitialLocale()).toBe('en')
  })
})

describe('locale-service — persistence', () => {
  it('persistLocale stores only supported codes', () => {
    persistLocale('uk')
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('uk')
    persistLocale('en')
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en')
  })

  it('a subsequent resolve restores the persisted selection', () => {
    persistLocale('en')
    expect(resolveInitialLocale()).toBe('en')
  })
})