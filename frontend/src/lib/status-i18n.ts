/**
 * Status i18n dispatch (WP-UX-UA-04).
 *
 * Thin helpers that resolve registry-owned keys through the ``status``
 * namespace so consumers never pass a hardcoded namespace. Two forms:
 * - ``useStatusTranslation`` — the reactive React hook;
 * - ``translateStatus*`` — non-reactive helpers backed by the shared i18n
 *   instance, for pure library modules (e.g. audit filter haystacks and
 *   label-wrapper functions) that cannot use hooks. React components
 *   re-render on locale change, so their render-time calls still follow the
 *   active locale.
 */

import { useTranslation } from 'react-i18next'

import i18n from '@/i18n'
import {
  allStatusEntries,
  type ResolvedStatus,
  type StatusDomain,
} from '@/lib/status-registry'

/** Translation bound to the ``status`` namespace. */
export function useStatusTranslation() {
  return useTranslation('status')
}

/**
 * Build a non-reactive ``{machineCode -> localizedLabel}`` map for one
 * registry domain, for library modules (e.g. audit filter haystacks) that
 * cannot use hooks. Values resolve through the shared i18n instance, so
 * callers must evaluate them at lookup time, not at module load, to follow
 * locale switches. Unknown codes are NOT present — consumers fall back to
 * the raw value themselves (no silent skips).
 */
export function buildRegistryLabelMap(
  domain: StatusDomain,
): Record<string, string> {
  const map: Record<string, string> = {}
  for (const entry of allStatusEntries()) {
    if (entry.domain === domain) {
      map[entry.code] = i18n.t(entry.labelKey, { ns: 'status' })
    }
  }
  return map
}

/**
 * Non-reactive label resolution for a resolved status entry.
 */
export function translateStatusLabel(entry: ResolvedStatus): string {
  return i18n.t(entry.labelKey, { ns: 'status' })
}

/**
 * Non-reactive description resolution for a resolved status entry.
 */
export function translateStatusDescription(entry: ResolvedStatus): string {
  return i18n.t(entry.descriptionKey, { ns: 'status' })
}