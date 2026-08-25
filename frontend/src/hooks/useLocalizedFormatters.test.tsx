/**
 * Localized formatters integration tests (WP-UX-UA-01 remediation F-1).
 *
 * Proves the React integration layer connects the ACTIVE locale to the pure
 * ``formatDate`` helper through the existing locale/i18n integration:
 * - starts with ``uk`` (Product Owner default, no saved preference);
 * - formats through ``uk-UA`` (Europe/Kyiv);
 * - switches reactively to ``en`` — the SAME mounted consumer re-renders
 *   with ``en-US`` output, no reload, no manual re-mount;
 * - switches back to ``uk``;
 * - only supported locale values are ever produced/exposed.
 */

import { act, render, renderHook, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import i18n from '@/i18n'
import { LOCALE_STORAGE_KEY } from '@/i18n/locale-service'
import { useLocalizedFormatters } from './useLocalizedFormatters'

function Consumer({ isoDate }: { isoDate: string }) {
  const { locale, formatDate } = useLocalizedFormatters()
  return (
    <span data-testid="consumer">
      {locale}:{formatDate(isoDate)}
    </span>
  )
}

describe('useLocalizedFormatters — active-locale formatting integration', () => {
  afterEach(() => {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY)
    act(() => {
      void i18n.changeLanguage('uk')
    })
  })

  it('starts with uk and formats through uk-UA (Europe/Kyiv)', () => {
    const { result } = renderHook(() => useLocalizedFormatters())
    expect(result.current.locale).toBe('uk')
    // Winter instant 2026-01-15T22:00:00Z = 2026-01-16 00:00 Europe/Kyiv.
    expect(result.current.formatDate('2026-01-15T22:00:00Z')).toBe(
      '16 січ. 2026 р.',
    )
  })

  it('switches reactively to en: the SAME mounted consumer rerenders with en-US, no reload', () => {
    render(<Consumer isoDate="2026-01-15T22:00:00Z" />)
    expect(screen.getByTestId('consumer')).toHaveTextContent(
      'uk:16 січ. 2026 р.',
    )

    act(() => {
      void i18n.changeLanguage('en')
    })
    expect(screen.getByTestId('consumer')).toHaveTextContent('en:Jan 16, 2026')
    expect(i18n.language).toBe('en')
  })

  it('switches back to uk on the same mounted consumer', () => {
    render(<Consumer isoDate="2026-07-15T22:00:00Z" />)
    act(() => {
      void i18n.changeLanguage('en')
    })
    expect(screen.getByTestId('consumer')).toHaveTextContent('en:Jul 16, 2026')

    act(() => {
      void i18n.changeLanguage('uk')
    })
    // Summer instant 2026-07-15T22:00:00Z = 2026-07-16 01:00 Europe/Kyiv.
    expect(screen.getByTestId('consumer')).toHaveTextContent(
      'uk:16 лип. 2026 р.',
    )
  })

  it('re-renders without an explicit locale argument at the call site', () => {
    // The localized callback requires only the ISO date — it cannot
    // accidentally fall back to the helper default when the locale changes.
    const { result } = renderHook(() => useLocalizedFormatters())
    act(() => {
      void i18n.changeLanguage('en')
    })
    expect(result.current.formatDate('2026-01-15T22:00:00Z')).toBe(
      'Jan 16, 2026',
    )
  })

  it('exposes only supported locale values (uk | en)', () => {
    const { result } = renderHook(() => useLocalizedFormatters())
    expect(['uk', 'en']).toContain(result.current.locale)
    act(() => {
      void i18n.changeLanguage('en')
    })
    expect(result.current.locale).toBe('en')
  })
})