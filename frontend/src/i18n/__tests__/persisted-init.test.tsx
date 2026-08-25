/**
 * Synchronous persisted-locale initialization tests
 * (WP-UX-UA-01 remediation F-2).
 *
 * Two complementary strategies:
 *
 * 1. Module-isolated scenarios (``vi.resetModules`` + dynamic ``import``) —
 *    the storage state is prepared BEFORE the i18n module initializes,
 *    exactly matching the production order (``main.tsx`` imports ``@/i18n``
 *    before ``createRoot`` renders the application). No React is rendered in
 *    these scenarios (rendering a fresh-registry hook would require a second
 *    React copy), so the assertions run on the module-initialization side
 *    effects alone: initialized ``i18n.language`` and the synchronously set
 *    ``html[lang]`` BEFORE any render.
 *
 * 2. A hook-mount latch scenario in the normal registry (runs FIRST in this
 *    file): an already-active English i18n instance must NOT be regressed
 *    back to ``uk`` by a mounted ``useActiveLocale`` consumer — the path
 *    that produced the two-frame Ukrainian heading flash.
 */

import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import { LOCALE_STORAGE_KEY } from '@/i18n/locale-service'
import { useActiveLocale } from '@/i18n/use-locale'

function HookProbe() {
  const { locale } = useActiveLocale()
  return <span data-testid="active-locale">{locale}</span>
}

describe('useActiveLocale — no redundant uk pass on an active English boot', () => {
  beforeEach(() => {
    window.localStorage.clear()
    // Real persisted-English boot shape: the stored selection exists AND the
    // active language is already en (resolved synchronously at startup).
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    act(() => {
      void i18n.changeLanguage('en')
    })
    expect(i18n.language).toBe('en')
  })

  afterEach(() => {
    act(() => {
      void i18n.changeLanguage('uk')
    })
    window.localStorage.clear()
  })

  it('mounts with en and never invokes changeLanguage("uk")', async () => {
    const changeSpy = vi.spyOn(i18n, 'changeLanguage')
    changeSpy.mockResolvedValue(i18n.t)

    const { unmount } = render(<HookProbe />)
    expect(screen.getByTestId('active-locale')).toHaveTextContent('en')

    // Flush the mount effect; the only changeLanguage pass is the already
    // active locale — a Ukrainian reset would be the F-2 regression.
    await act(async () => {})
    expect(
      changeSpy.mock.calls.filter(([lng]) => lng === 'uk'),
    ).toHaveLength(0)
    expect(document.documentElement.lang).toBe('en')
    unmount()
  })
})

describe('synchronous persisted-locale initialization (module isolation)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.resetModules()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('stored en: i18n initializes as en and html[lang] is en, all before render', async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    vi.resetModules()

    const i18nMod = await import('../index')
    // Module top-level side effects have already run at this point — no
    // React component has been rendered anywhere in this scenario.
    expect(i18nMod.default.language).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    expect(i18nMod.default.language).not.toBe('uk')
  })

  it('no stored value: i18n initializes as uk and html[lang] is uk before render', async () => {
    const i18nMod = await import('../index')
    expect(i18nMod.default.language).toBe('uk')
    expect(document.documentElement.lang).toBe('uk')
  })

  it('stored uk: i18n initializes as uk', async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'uk')
    vi.resetModules()
    const i18nMod = await import('../index')
    expect(i18nMod.default.language).toBe('uk')
    expect(document.documentElement.lang).toBe('uk')
  })

  it('malformed stored value: initializes to uk', async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'fr-FR')
    vi.resetModules()
    const i18nMod = await import('../index')
    expect(i18nMod.default.language).toBe('uk')
    expect(document.documentElement.lang).toBe('uk')
  })

  it('storage read failure: initializes safely to uk', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage blocked')
    })
    vi.resetModules()
    const i18nMod = await import('../index')
    expect(i18nMod.default.language).toBe('uk')
    expect(document.documentElement.lang).toBe('uk')
  })
})