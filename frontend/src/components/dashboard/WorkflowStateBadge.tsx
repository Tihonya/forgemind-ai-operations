/**
 * Business-facing workflow state badge (WP-UX-01/02 lineage, registry-backed
 * since WP-UX-UA-04).
 *
 * Displays the localized label for a raw workflow run state enum value via
 * the shared status registry — no component-local label maps. Reusable by
 * WP-UX-01 (Dashboard), WP-UX-02 (Risk Detail), and WP-UX-03 (AI Analyses
 * Archive).
 *
 * The raw enum is preserved on ``data-code`` for technical contexts.
 */

import StatusBadgeExplained from '@/components/status/StatusBadgeExplained'

interface WorkflowStateBadgeProps {
  state: string | null | undefined;
  testId?: string;
}

/**
 * Render a registry-backed workflow run state badge with an accessible
 * tooltip explanation.
 */
export default function WorkflowStateBadge({
  state,
  testId = 'workflow-state-badge',
}: WorkflowStateBadgeProps) {
  return (
    <StatusBadgeExplained
      domain="workflowRun"
      code={state}
      testId={testId}
    />
  )
}