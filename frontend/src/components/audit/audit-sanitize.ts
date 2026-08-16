/**
 * Centralized display-sanitization for Audit Log metadata (WP-REC-04E).
 *
 * The audit wire schema legitimately carries ``binding_hash`` inside
 * ``event_metadata``, ``before_summary``, and ``after_summary`` (emitted by
 * the approval/procurement services). The Audit Log must never surface that
 * key or its value in the DOM. This module provides the narrow, non-mutating
 * predicate the centralized metadata renderer (``SafeMetadata``) uses to
 * suppress those entries before rendering — regardless of key spelling
 * variant or nesting depth.
 */

const BINDING_HASH_NORMALIZED = 'bindinghash'

/**
 * Normalize a metadata key to a canonical, case/separator-insensitive form:
 * lowercase, then strip underscores and hyphens. This maps ``binding_hash``,
 * ``bindingHash``, and ``binding-hash`` to the same canonical token.
 */
export function normalizeMetadataKey(key: string): string {
  return key.toLowerCase().replace(/[-_]/g, '')
}

/**
 * Return true when the given metadata key is a ``binding_hash`` field under
 * any of its reasonable spelling variants (``binding_hash``, ``bindingHash``,
 * ``binding-hash``). Unrelated keys (e.g. ``binding_version``) do not match.
 */
export function isBindingHashKey(key: string): boolean {
  return normalizeMetadataKey(key) === BINDING_HASH_NORMALIZED
}
