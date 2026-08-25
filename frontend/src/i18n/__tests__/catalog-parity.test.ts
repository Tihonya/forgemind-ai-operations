/**
 * Catalog key-parity tests (WP-UX-UA-01).
 *
 * Contract: uk and en catalogs share the exact leaf-key set and the same
 * nested shape per namespace. Values are never compared for equality.
 *
 * Committed catalogs → parity PASS.
 * Deliberately constructed asymmetry → parity FAIL (unit case).
 */

import { describe, expect, it } from 'vitest'

import {
  CATALOG_NAMESPACES,
  RESOURCES,
} from '../index'
import {
  collectLeafKeys,
  compareCatalogs,
  validateCommittedCatalogs,
  type ParityFailure,
} from '../catalog-parity'

describe('catalog key parity — committed catalogs', () => {
  it('all required namespaces are present in both locales', () => {
    const en = RESOURCES.en as Record<string, unknown>
    const uk = RESOURCES.uk as Record<string, unknown>
    for (const namespace of CATALOG_NAMESPACES) {
      expect(en[namespace], `en.${namespace}`).toBeDefined()
      expect(uk[namespace], `uk.${namespace}`).toBeDefined()
    }
  })

  it('uk and en leaf-key sets are identical for every namespace', () => {
    const failures = validateCommittedCatalogs()
    expect(failures, JSON.stringify(failures, null, 2)).toEqual([])
  })

  it('every uk navigation label resolves inside the uk shell catalog', () => {
    const shell = (RESOURCES.uk as Record<string, unknown>)
      .shell as Record<string, Record<string, unknown>>
    for (const key of Object.keys(shell.navigation)) {
      expect(typeof shell.navigation[key]).toBe('string')
    }
  })
})

describe('catalog key parity — deliberately broken unit cases', () => {
  it('fails when a key exists only in Ukrainian', () => {
    const en = { greetings: { hello: 'Hello' } }
    const uk = { greetings: { hello: 'Привіт', extra: 'Додатковий' } }
    const failures = compareCatalogs(en, uk, 'ns')
    expect(failures).toContainEqual(
      expect.objectContaining({ kind: 'missing-in-en', key: 'greetings.extra' }),
    )
  })

  it('fails when a key exists only in English', () => {
    const en = { navigation: { dashboard: 'Dashboard', admin: 'Admin' } }
    const uk = { navigation: { dashboard: 'Огляд' } }
    const failures = compareCatalogs(en, uk, 'ns')
    expect(failures).toContainEqual(
      expect.objectContaining({ kind: 'missing-in-uk', key: 'navigation.admin' }),
    )
  })

  it('fails when a nested object/leaf shape differs', () => {
    const en = { navigation: { dashboard: 'Dashboard' } }
    const uk = { navigation: { dashboard: { title: 'Огляд' } } }
    const leafFailures = compareCatalogs(en, uk, 'ns')
    expect(
      leafFailures.some(
        (f: ParityFailure) =>
          f.kind === 'missing-in-uk' ||
          f.kind === 'missing-in-en' ||
          f.kind === 'shape-differs',
      ),
    ).toBe(true)
  })

  it('reports a missing required namespace in a constructed catalog set', () => {
    // Construct a catalog set that omits the shell namespace and run the
    // same namespace-presence check logic manually (validateCommittedCatalogs
    // itself is bound to the committed resources, which must never fail).
    const enOnly = { common: { a: 'A' } }
    const ukOnly = { common: { a: 'Б' } }
    const required = ['common', 'shell', 'dashboard']
    const missing: string[] = []
    for (const namespace of required) {
      if (
        (enOnly as Record<string, unknown>)[namespace] === undefined ||
        (ukOnly as Record<string, unknown>)[namespace] === undefined
      ) {
        missing.push(namespace)
      }
    }
    expect(missing).toEqual(['shell', 'dashboard'])
  })

  it('collectLeafKeys flattens nested objects into dot-joined paths', () => {
    const keys = collectLeafKeys({
      a: { b: 1, c: 'x' },
      d: 'y',
    }).sort()
    expect(keys).toEqual(['a.b', 'a.c', 'd'])
  })
})