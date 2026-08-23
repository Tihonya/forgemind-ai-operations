/**
 * Business-facing workflow state badge.
 *
 * Displays a user-friendly label for a raw workflow state enum value.
 * Reusable by WP-UX-01 (Dashboard), WP-UX-02 (Risk Detail), and WP-UX-03
 * (AI Analyses Archive).
 */

import { getWorkflowStateLabel, getWorkflowStateTone } from '@/lib/workflow-state-labels';

const TONE_CLASSES: Record<string, string> = {
  neutral: 'bg-steel-700/40 text-steel-300 border-steel-600/40',
  active: 'bg-primary-600/20 text-primary-300 border-primary-600/40',
  success: 'bg-emerald-600/20 text-emerald-300 border-emerald-600/40',
  error: 'bg-red-600/20 text-red-300 border-red-600/40',
};

interface WorkflowStateBadgeProps {
  state: string | null | undefined;
  testId?: string;
}

/**
 * Render a business-labeled badge for a workflow state.
 */
export default function WorkflowStateBadge({
  state,
  testId = 'workflow-state-badge',
}: WorkflowStateBadgeProps) {
  const label = getWorkflowStateLabel(state);
  const tone = getWorkflowStateTone(state);
  const classes = TONE_CLASSES[tone] ?? TONE_CLASSES.neutral;

  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${classes}`}
      data-testid={testId}
    >
      {label}
    </span>
  );
}
