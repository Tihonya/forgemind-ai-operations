import { describe, expect, it } from 'vitest'

import { formatQuantity } from '@/lib/format'

/**
 * Locale-aware quantity formatting (WP-UX-UA-03).
 *
 * English (``en-US``) anchors are byte-literal; Ukrainian (``uk-UA``)
 * anchors verify narrow no-break-space grouping and comma decimals. The
 * pure helper maps the supported locale codes to display locales via the
 * i18n types module.
 */
describe('formatQuantity — English (en-US)', () => {
  it('formats zero correctly', () => {
    expect(formatQuantity('0.0000', 'en')).toBe('0')
  })

  it('formats whole numbers without decimals', () => {
    expect(formatQuantity('100.0000', 'en')).toBe('100')
  })

  it('formats decimal numbers with up to 2 decimals', () => {
    expect(formatQuantity('45.6789', 'en')).toBe('45.68')
    expect(formatQuantity('12.3000', 'en')).toBe('12.3')
  })

  it('formats small decimals', () => {
    expect(formatQuantity('0.5000', 'en')).toBe('0.5')
    expect(formatQuantity('0.0100', 'en')).toBe('0.01')
  })

  it('preserves large numbers', () => {
    expect(formatQuantity('1234567.8900', 'en')).toBe('1,234,567.89')
  })

  it('handles negative numbers', () => {
    expect(formatQuantity('-25.0000', 'en')).toBe('-25')
    expect(formatQuantity('-0.5000', 'en')).toBe('-0.5')
  })
})

describe('formatQuantity — Ukrainian (uk-UA)', () => {
  it('groups thousands with a narrow no-break space and comma decimals', () => {
    expect(formatQuantity('1234567.8900', 'uk')).toBe('1\u00a0234\u00a0567,89')
  })

  it('formats small decimals with a comma', () => {
    expect(formatQuantity('45.6789', 'uk')).toBe('45,68')
    expect(formatQuantity('0.5000', 'uk')).toBe('0,5')
  })

  it('formats whole numbers without a decimal separator', () => {
    expect(formatQuantity('100.0000', 'uk')).toBe('100')
    expect(formatQuantity('0.0000', 'uk')).toBe('0')
  })
})

describe('formatQuantity — default locale and safety', () => {
  it('defaults to Ukrainian (the product default locale)', () => {
    expect(formatQuantity('1234.5000')).toBe(formatQuantity('1234.5000', 'uk'))
  })

  it('returns "0" for unparseable input', () => {
    expect(formatQuantity('not-a-number')).toBe('0')
    expect(formatQuantity('')).toBe('0')
  })
})
