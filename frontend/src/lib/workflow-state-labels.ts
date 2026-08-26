/**
 * Workflow-state helpers (WP-UX-01 lineage, registry-backed since
 * WP-UX-UA-04).
 *
 * Label and tone resolution now delegate to the shared localized status
 * registry (lookup keyed by domain + machine code), so the Dashboard and
 * Risk Detail surfaces never expose raw terminology as the primary copy and
 * no component-local label map remains here.
 *
 * The terminal/nonterminal classification helpers are unchanged — they are
 * behavior predicates, not presentation, and keep their exact semantics.
 */

import { resolveStatus } from '@/lib/status-registry'
import { translateStatusLabel } from '@/lib/status-i18n'

/** Fallback label for unknown state values. */
const UNKNOWN_LABEL = 'Unknown'

/**
 * Return the registry-localized label for a raw workflow state. Unknown
 * states preserve the raw machine value verbatim (diagnosable, never
 * hidden); falsy input returns the neutral Unknown word.
 */
export function getWorkflowStateLabel(state: string | null | undefined): string {
  if (!state) return UNKNOWN_LABEL
  const entry = resolveStatus('workflowRun', state)
  return entry.known ? translateStatusLabel(entry) : state
}

/**
 * Visual tone for a workflow state — semantic design-token vocabulary
 * (neutral / info / success / warning / danger), resolved by the registry.
 */
export type WorkflowStateTone =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'danger'

/**
 * Return the registry-resolved semantic tone for a workflow state.
 */
export function getWorkflowStateTone(
  state: string | null | undefined,
): WorkflowStateTone {
  if (!state) return 'neutral'
  return resolveStatus('workflowRun', state).tone
}

/** Set of nonterminal workflow states. */
export const NONTERMINAL_STATES = new Set<string>([
  'PENDING',
  'RUNNING',
  'AWAITING_VALIDATION',
])

/** Set of failed (terminal) workflow states. */
export const FAILED_STATES = new Set<string>([
  'FAILED_PROVIDER',
  'FAILED_VALIDATION',
  'FAILED_RETRIEVAL',
  'FAILED_INTERNAL',
])

/**
 * Whether the workflow state is nonterminal (PENDING, RUNNING,
 * AWAITING_VALIDATION).
 */
export function isNonterminalState(state: string | null | undefined): boolean {
  return !!state && NONTERMINAL_STATES.has(state)
}

/**
 * Whether the workflow state is a failed terminal state.
 */
export function isFailedState(state: string | null | undefined): boolean {
  return !!state && FAILED_STATES.has(state)
}