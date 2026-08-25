/**
 * Catalog key-parity validation (WP-UX-UA-01).
 *
 * Compares the complete LEAF-KEY sets of the Ukrainian and English catalogs
 * per namespace. Translated values are deliberately never compared for
 * equality — Ukrainian and English values differ by definition.
 *
 * Fails when:
 * - a key exists only in Ukrainian;
 * - a key exists only in English;
 * - a nested object/leaf shape differs;
 * - a required namespace is missing.
 */

import { CATALOG_NAMESPACES, RESOURCES } from './index'

/** Collect all leaf-key JSON paths (dot-joined) of a catalog subtree. */
export function collectLeafKeys(
  node: unknown,
  prefix = '',
  out: string[] = [],
): string[] {
  if (node === null || typeof node !== 'object') {
    out.push(prefix)
    return out
  }
  if (Array.isArray(node)) {
    out.push(prefix)
    return out
  }
  const entries = Object.entries(node as Record<string, unknown>)
  if (entries.length === 0) {
    out.push(prefix)
    return out
  }
  for (const [key, value] of entries) {
    const path = prefix ? `${prefix}.${key}` : key
    collectLeafKeys(value, path, out)
  }
  return out
}

export interface ParityFailure {
  namespace: string
  locale: 'uk' | 'en'
  kind: 'missing-in-uk' | 'missing-in-en' | 'shape-differs'
  key?: string
  message: string
}

/**
 * Compare two locale catalogs for key-set parity PLUS value-shape parity
 * (a key mapped to an object in one catalog and to a string in the other is
 * a shape difference and is reported).
 */
export function compareCatalogs(
  enCatalog: unknown,
  ukCatalog: unknown,
  namespace: string,
): ParityFailure[] {
  const failures: ParityFailure[] = []

  const enKeys = collectLeafKeys(enCatalog).sort()
  const ukKeys = collectLeafKeys(ukCatalog).sort()

  const enSet = new Set(enKeys)
  const ukSet = new Set(ukKeys)

  for (const key of ukKeys) {
    if (!enSet.has(key)) {
      failures.push({
        namespace,
        locale: 'en',
        kind: 'missing-in-en',
        key,
        message: `Key "${key}" exists in uk/${namespace} but not in en/${namespace}`,
      })
    }
  }
  for (const key of enKeys) {
    if (!ukSet.has(key)) {
      failures.push({
        namespace,
        locale: 'uk',
        kind: 'missing-in-uk',
        key,
        message: `Key "${key}" exists in en/${namespace} but not in uk/${namespace}`,
      })
    }
  }

  // Shape check is inclusive: even when key sets match, a value shape
  // (object/array vs scalar) mismatch is a contract violation.
  const commonKeys = enKeys.filter((k) => ukSet.has(k))
  const readAt = (root: unknown, key: string): unknown => {
    if (key === '') return root
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let cur: any = root ?? {}
    for (const part of key.split('.')) {
      if (cur == null || typeof cur !== 'object') return undefined
      cur = cur[part]
    }
    return cur
  }
  for (const key of commonKeys) {
    const enVal = readAt(enCatalog, key)
    const ukVal = readAt(ukCatalog, key)
    const enShape = enVal === null || typeof enVal !== 'object' ? 'scalar' : Array.isArray(enVal) ? 'array' : 'object'
    const ukShape = ukVal === null || typeof ukVal !== 'object' ? 'scalar' : Array.isArray(ukVal) ? 'array' : 'object'
    if (enShape !== ukShape) {
      failures.push({
        namespace,
        locale: 'uk',
        kind: 'shape-differs',
        key,
        message: `Key "${key}" in ${namespace}: shape differs (en=${enShape}, uk=${ukShape})`,
      })
    }
  }

  return failures
}

/** Validate the committed bundled catalogs across all required namespaces. */
export function validateCommittedCatalogs(): ParityFailure[] {
  const failures: ParityFailure[] = []
  for (const namespace of CATALOG_NAMESPACES) {
    const enCatalog = (RESOURCES.en as Record<string, unknown>)[namespace]
    const ukCatalog = (RESOURCES.uk as Record<string, unknown>)[namespace]
    if (enCatalog === undefined) {
      failures.push({
        namespace,
        locale: 'en',
        kind: 'missing-in-en',
        message: `Required namespace "${namespace}" missing from en catalogs`,
      })
    }
    if (ukCatalog === undefined) {
      failures.push({
        namespace,
        locale: 'uk',
        kind: 'missing-in-uk',
        message: `Required namespace "${namespace}" missing from uk catalogs`,
      })
    }
    if (enCatalog === undefined || ukCatalog === undefined) continue
    failures.push(...compareCatalogs(enCatalog, ukCatalog, namespace))
  }
  return failures
}