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
 */

import type { ReactNode } from 'react'

const MAX_DEPTH = 6
const MAX_ITEMS = 50

interface SafeMetadataProps {
  value: unknown
  testId?: string
}

export function SafeMetadata({
  value,
  testId = 'audit-metadata',
}: SafeMetadataProps) {
  return (
    <div className="text-xs text-steel-300" data-testid={testId}>
      {renderValue(value, 0)}
    </div>
  )
}

function renderValue(value: unknown, depth: number): ReactNode {
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
    return renderArray(value, depth)
  }
  if (typeof value === 'object') {
    return renderObject(value as Record<string, unknown>, depth)
  }
  return <span>{String(value)}</span>
}

function renderArray(value: unknown[], depth: number): ReactNode {
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
        <li key={index}>{renderValue(item, depth + 1)}</li>
      ))}
      {overflow > 0 && (
        <li className="list-none text-steel-500">… {overflow} more</li>
      )}
    </ul>
  )
}

function renderObject(value: Record<string, unknown>, depth: number): ReactNode {
  const entries = Object.entries(value)
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
          <dd className="break-all">{renderValue(val, depth + 1)}</dd>
        </div>
      ))}
      {overflow > 0 && (
        <div className="text-steel-500">… {overflow} more</div>
      )}
    </dl>
  )
}
