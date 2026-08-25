/**
 * Defensive read-only metadata renderer (WP-REC-04E).
 *
 * Renders arbitrary structured metadata (``before_summary``, ``after_summary``,
 * ``event_metadata``) without ever:
 * - injecting HTML (React escapes all values; no dangerouslySetInnerHTML);
 * - crashing on unknown values;
 * - unbounded deep or oversized structures (depth and item count are capped);
 * - reinterpreting the backend ``[REDACTED]`` sentinel (string values render
 *   verbatim, so ``[REDACTED]`` is preserved exactly).
 *
 * Localized per WP-UX-UA-03: only the overflow hint ("… N more") is localized;
 * raw metadata keys/values (machine content) render verbatim.
 */

import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { isBindingHashKey } from './audit-sanitize'

const MAX_DEPTH = 6
const MAX_ITEMS = 50

interface SafeMetadataProps {
  value: unknown;
  testId?: string;
}

export function SafeMetadata({
  value,
  testId = 'audit-metadata',
}: SafeMetadataProps) {
  const { t } = useTranslation('audit')
  return (
    <div className="text-xs text-steel-300" data-testid={testId}>
      {renderValue(value, 0, t)}
    </div>
  )
}

function renderValue(
  value: unknown,
  depth: number,
  t: (key: string, options?: Record<string, unknown>) => string,
): ReactNode {
  if (value === null) {
    return <span className="text-steel-500">null</span>
  }
  if (typeof value === 'string') {
    return <span>{value}</span>
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <span>{String(value)}</span>
  }
  if (Array.isArray(value)) {
    return renderArray(value, depth, t)
  }
  if (typeof value === 'object') {
    return renderObject(value as Record<string, unknown>, depth, t)
  }
  return <span>{String(value)}</span>
}

function renderArray(
  value: unknown[],
  depth: number,
  t: (key: string, options?: Record<string, unknown>) => string,
): ReactNode {
  if (value.length === 0) {
    return <span className="text-steel-500">[]</span>
  }
  if (depth >= MAX_DEPTH) {
    return <span className="text-steel-500">…</span>
  }
  const visible = value.slice(0, MAX_ITEMS)
  const overflow = value.length - visible.length
  return (
    <ul className="ml-4 list-disc space-y-0.5">
      {visible.map((item, index) => (
        <li key={index}>{renderValue(item, depth + 1, t)}</li>
      ))}
      {overflow > 0 && (
        <li className="list-none text-steel-500">{t('metadata.more', { count: overflow })}</li>
      )}
    </ul>
  )
}

function renderObject(
  value: Record<string, unknown>,
  depth: number,
  t: (key: string, options?: Record<string, unknown>) => string,
): ReactNode {
  // Centralized display-sanitization boundary: suppress binding_hash entries
  // (any spelling variant) so neither the key nor its value reaches the DOM.
  // The filter is non-mutating — the original object and React Query cache
  // entries are left untouched.
  const entries = Object.entries(value).filter(([key]) => !isBindingHashKey(key))
  if (entries.length === 0) {
    return <span className="text-steel-500">{'{}'}</span>
  }
  if (depth >= MAX_DEPTH) {
    return <span className="text-steel-500">…</span>
  }
  const visible = entries.slice(0, MAX_ITEMS)
  const overflow = entries.length - visible.length
  return (
    <dl className="space-y-1">
      {visible.map(([key, val]) => (
        <div key={key} className="flex flex-wrap gap-x-2">
          <dt className="font-medium text-steel-400">{key}:</dt>
          <dd className="break-all">{renderValue(val, depth + 1, t)}</dd>
        </div>
      ))}
      {overflow > 0 && (
        <div className="text-steel-500">{t('metadata.more', { count: overflow })}</div>
      )}
    </dl>
  )
}
