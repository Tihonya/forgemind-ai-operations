/**
 * Human-readable reference helpers (WP-UX-UA-05 §8).
 *
 * Persisted UUIDs and machine contracts remain unchanged. Where an entity has
 * only a UUID, these helpers derive a presentation-only short reference
 * (``REC-…``, ``APR-…``, ``TASK-…``) for display. The full UUID stays
 * available in technical details when useful.
 */

/** Derive a presentation-only short reference from an opaque UUID. */
export function shortRef(prefix: string, id: string | null | undefined): string {
  if (!id) return '—'
  const compact = id.length > 8 ? id.slice(0, 8) : id
  return prefix ? `${prefix}-${compact.toUpperCase()}` : compact.toUpperCase()
}
