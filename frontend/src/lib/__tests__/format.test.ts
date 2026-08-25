/**
 * Locale-aware date formatting tests (WP-UX-UA-01 contract + F-1 remediation).
 *
 * Primary assertions are INDEPENDENT literal anchors — the expected strings
 * are written out byte-for-byte (verified against full-ICU Node 22 with the
 * Europe/Kyiv zone) instead of being recomputed with the same
 * ``Intl.DateTimeFormat`` options the implementation uses. This makes the
 * suite able to detect an accidental ``uk-UA ↔ en-US`` swap, and keeps the
 * calendar-day rollover assertions anchored to UTC divergence:
 *
 * - 2026-01-15T22:00:00Z is 2026-01-16 00:00 in Europe/Kyiv (UTC+2, winter)
 *   while it is still 2026-01-15 in UTC;
 * - 2026-07-15T22:00:00Z is 2026-07-16 01:00 in Europe/Kyiv (UTC+3, DST)
 *   while it is still 2026-07-15 in UTC.
 *
 * A small number of comparator-based checks remains ONLY to prove the
 * default-locale contract (default ≡ explicit 'uk') and determinism;
 * locale-string correctness never depends on them.
 */

import { describe, expect, it } from 'vitest'

import { APP_TIME_ZONE, formatDate } from '../format'

describe('formatDate — literal locale anchors (uk-UA vs en-US)', () => {
  it('Ukrainian winter date in Europe/Kyiv (UTC+2, calendar-day rollover)', () => {
    // 2026-01-15T22:00:00Z = 2026-01-16 00:00 Europe/Kyiv.
    expect(formatDate('2026-01-15T22:00:00Z', 'uk')).toBe('16 січ. 2026 р.')
    // Same instant, midnight UTC — the anchor for the rollover assertion.
    expect(formatDate('2026-01-15T12:00:00Z', 'uk')).toBe('15 січ. 2026 р.')
  })

  it('Ukrainian summer date in Europe/Kyiv (UTC+3, DST, calendar-day rollover)', () => {
    // 2026-07-15T22:00:00Z = 2026-07-16 01:00 Europe/Kyiv.
    expect(formatDate('2026-07-15T22:00:00Z', 'uk')).toBe('16 лип. 2026 р.')
    expect(formatDate('2026-07-15T12:00:00Z', 'uk')).toBe('15 лип. 2026 р.')
  })

  it('English winter date in Europe/Kyiv (UTC+2, calendar-day rollover)', () => {
    expect(formatDate('2026-01-15T22:00:00Z', 'en')).toBe('Jan 16, 2026')
    expect(formatDate('2026-01-15T12:00:00Z', 'en')).toBe('Jan 15, 2026')
  })

  it('English summer date in Europe/Kyiv (UTC+3, DST, calendar-day rollover)', () => {
    expect(formatDate('2026-07-15T22:00:00Z', 'en')).toBe('Jul 16, 2026')
    expect(formatDate('2026-07-15T12:00:00Z', 'en')).toBe('Jul 15, 2026')
  })

  it('formats the seeded plan period shapes identically in the live bundle', () => {
    // Date-only strings parse as UTC midnight; Kyiv rendering keeps the
    // same calendar day in both winter and summer offsets.
    expect(formatDate('2026-07-31', 'uk')).toBe('31 лип. 2026 р.')
    expect(formatDate('2026-08-06', 'uk')).toBe('6 серп. 2026 р.')
    expect(formatDate('2026-07-31', 'en')).toBe('Jul 31, 2026')
    expect(formatDate('2026-08-06', 'en')).toBe('Aug 6, 2026')
  })
})

describe('formatDate — Europe/Kyiv zone divergence from UTC (independent anchor)', () => {
  const kyiv = { month: 'short', day: 'numeric', year: 'numeric' } as const

  it('winter rollover instant renders a day ahead of UTC', () => {
    const input = '2026-01-15T22:00:00Z'
    const utcReference = new Intl.DateTimeFormat('uk-UA', {
      ...kyiv,
      timeZone: 'UTC',
    }).format(new Date(input))
    // UTC still says Jan 15 while Kyiv says Jan 16 — proves the Kyiv zone.
    expect(utcReference).toBe('15 січ. 2026 р.')
    expect(formatDate(input, 'uk')).toBe('16 січ. 2026 р.')
    expect(formatDate(input, 'uk')).not.toBe(utcReference)
  })

  it('summer rollover instant renders a day ahead of UTC', () => {
    const input = '2026-07-15T22:00:00Z'
    const utcReference = new Intl.DateTimeFormat('uk-UA', {
      ...kyiv,
      timeZone: 'UTC',
    }).format(new Date(input))
    expect(utcReference).toBe('15 лип. 2026 р.')
    expect(formatDate(input, 'uk')).toBe('16 лип. 2026 р.')
  })

  it('uses Europe/Kyiv explicitly (APP_TIME_ZONE contract)', () => {
    expect(APP_TIME_ZONE).toBe('Europe/Kyiv')
  })
})

describe('formatDate — default-locale contract', () => {
  it('formats Ukrainian by default (default ≡ explicit uk)', () => {
    const input = '2026-01-15T22:00:00Z'
    expect(formatDate(input)).toBe(formatDate(input, 'uk'))
    expect(formatDate(input)).toBe('16 січ. 2026 р.')
  })

  it('produces deterministic output for the same instant and locale', () => {
    expect(formatDate('2026-07-15T22:00:00Z', 'en')).toBe(
      formatDate('2026-07-15T22:00:00Z', 'en'),
    )
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
    expect(formatDate('null')).toBe('null')
  })
})