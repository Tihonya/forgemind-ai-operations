/**
 * Business-facing workflow state labels.
 *
 * Maps raw backend state-machine enum values to user-friendly labels so the
 * Dashboard and future WP-UX-02 / WP-UX-03 surfaces never expose raw
 * terminology as the primary copy.
 *
 * Raw enum values are preserved for technical/reference contexts but should
 * not be the primary user-facing label.
 */

/** Canonical mapping from raw state to business label. */
export const WORKFLOW_STATE_LABELS: Record<string, string> = {
  PENDING: 'Queued',
  RUNNING: 'Analysis in progress',
  AWAITING_VALIDATION: 'Validating result',
  COMPLETED: 'Completed',
  FAILED_PROVIDER: 'AI service unavailable',
  FAILED_VALIDATION: 'Validation failed',
  FAILED_RETRIEVAL: 'Evidence retrieval failed',
  FAILED_INTERNAL: 'Analysis failed',
};

/** Fallback label for unknown state values. */
const UNKNOWN_LABEL = 'Unknown';

/**
 * Return a business-friendly label for a raw workflow state.
 * Falls back to the raw value when known, or 'Unknown' when the raw value
 * is falsy/empty.
 */
export function getWorkflowStateLabel(state: string | null | undefined): string {
  if (!state) return UNKNOWN_LABEL;
  return WORKFLOW_STATE_LABELS[state] ?? state;
}

/**
 * Visual tone for a workflow state, used by badge styling.
 * Maps to Tailwind color classes.
 */
export type WorkflowStateTone = 'neutral' | 'active' | 'success' | 'error';

const STATE_TONES: Record<string, WorkflowStateTone> = {
  PENDING: 'neutral',
  RUNNING: 'active',
  AWAITING_VALIDATION: 'active',
  COMPLETED: 'success',
  FAILED_PROVIDER: 'error',
  FAILED_VALIDATION: 'error',
  FAILED_RETRIEVAL: 'error',
  FAILED_INTERNAL: 'error',
};

/**
 * Return the visual tone for a workflow state.
 */
export function getWorkflowStateTone(
  state: string | null | undefined,
): WorkflowStateTone {
  if (!state) return 'neutral';
  return STATE_TONES[state] ?? 'neutral';
}

/** Set of nonterminal workflow states. */
export const NONTERMINAL_STATES = new Set<string>([
  'PENDING',
  'RUNNING',
  'AWAITING_VALIDATION',
]);

/** Set of failed (terminal) workflow states. */
export const FAILED_STATES = new Set<string>([
  'FAILED_PROVIDER',
  'FAILED_VALIDATION',
  'FAILED_RETRIEVAL',
  'FAILED_INTERNAL',
]);

/**
 * Whether the workflow state is nonterminal (PENDING, RUNNING,
 * AWAITING_VALIDATION).
 */
export function isNonterminalState(state: string | null | undefined): boolean {
  return !!state && NONTERMINAL_STATES.has(state);
}

/**
 * Whether the workflow state is a failed terminal state.
 */
export function isFailedState(state: string | null | undefined): boolean {
  return !!state && FAILED_STATES.has(state);
}
