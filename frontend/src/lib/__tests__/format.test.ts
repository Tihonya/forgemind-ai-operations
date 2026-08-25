/**
 * Locale-aware date formatting tests (WP-UX-UA-01 contract).
 *
 * - uk-UA default + Europe/Kyiv;
 * - en-US + Europe/Kyiv;
 * - fixed winter timestamp (UTC+2 in Kyiv);
 * - fixed summer timestamp (UTC+3 in Kyiv — DST-relevant);
 * - safe invalid/null behavior.
 */

import { describe, expect, it } from 'vitest'

import { APP_TIME_ZONE, formatDate } from '../format'

const kyivOptions = {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: APP_TIME_ZONE,
} as const

describe('formatDate — locale contract', () => {
  it('formats Ukrainian by default with uk-UA and Europe/Kyiv', () => {
    const input = '2026-01-15T12:00:00Z'
    const expected = new Intl.DateTimeFormat('uk-UA', kyivOptions).format(
      new Date(input),
    )
    expect(formatDate(input)).toBe(expected)
  })

  it('formats English with en-US and Europe/Kyiv', () => {
    const input = '2026-07-15T12:00:00Z'
    const expected = new Intl.DateTimeFormat('en-US', kyivOptions).format(
      new Date(input),
    )
    expect(formatDate(input, 'en')).toBe(expected)
  })
})

describe('formatDate — fixed instants (winter and summer)', () => {
  it('winter instant: 2026-01-15T22:00:00Z rolls into 2026-01-16 in Kyiv (UTC+2)', () => {
    // In UTC this is still Jan 15; in Europe/Kyiv (UTC+2, winter) it is
    // 2026-01-16 00:00 — the date boundary proves the Kyiv zone applied.
    const got = formatDate('2026-01-15T22:00:00Z')
    const expected = new Intl.DateTimeFormat('uk-UA', kyivOptions).format(
      new Date('2026-01-15T22:00:00Z'),
    )
    expect(got).toBe(expected)
    const utcReference = new Intl.DateTimeFormat('uk-UA', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date('2026-01-15T22:00:00Z'))
    expect(utcReference).not.toBe(expected)
  })

  it('summer instant: 2026-07-15T22:00:00Z rolls into 2026-07-16 in Kyiv (UTC+3)', () => {
    const got = formatDate('2026-07-15T22:00:00Z')
    const expected = new Intl.DateTimeFormat('uk-UA', kyivOptions).format(
      new Date('2026-07-15T22:00:00Z'),
    )
    expect(got).toBe(expected)
  })

  it('produces deterministic output for the same instant and locale', () => {
    const a = formatDate('2026-07-15T22:00:00Z', 'en')
    const b = formatDate('2026-07-15T22:00:00Z', 'en')
    expect(a).toBe(b)
  })
})

describe('formatDate — safe invalid/null behavior', () => {
  it('returns unparseable input unchanged', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date')
  })

  it('returns empty string unchanged', () => {
    expect(formatDate('')).toBe('')
  })

  it('never throws on null-like values passed as strings', () => {
    expect(() => formatDate('null')).not.toThrow()
  })
})