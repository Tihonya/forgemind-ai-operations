/**
 * Latest AI Analysis widget — replaces the stale "Latest Agent Runs —
 * Unavailable — Phase 5" placeholder.
 *
 * Shows the most recent workflow run with business-facing state, plan,
 * timestamp, and a state-aware CTA that routes to:
 *   - existing run → /workflow-runs/{run_id}
 *   - no run       → /supply-risk
 */

import { Link } from 'react-router-dom';
import { Bot, ArrowRight } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import WorkflowStateBadge from '@/components/dashboard/WorkflowStateBadge';
import { useWorkflowRuns } from '@/hooks/use-workflow-runs';
import {
  isNonterminalState,
  isFailedState,
} from '@/lib/workflow-state-labels';

/**
 * Format an ISO timestamp to a short, human-readable date-time.
 */
function formatTimestamp(iso: string | null): string | null {
  if (!iso) return null;
  try {
    const date = new Date(iso);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

/**
 * Determine the CTA label for a given run state.
 */
function getCtaLabel(state: string | null | undefined): string {
  if (!state) return 'Review supply risks';
  if (state === 'COMPLETED') return 'View recommendation';
  if (isNonterminalState(state)) return 'View progress';
  if (isFailedState(state)) return 'Review failure';
  return 'Review supply risks';
}

/**
 * Determine the CTA destination for a given run.
 */
function getCtaDestination(runId: string | undefined, state: string | null | undefined): string {
  if (runId && state) return `/workflow-runs/${runId}`;
  return '/supply-risk';
}

export default function LatestAIAnalysisWidget() {
  const { runs, isLoading, isError, refetch } = useWorkflowRuns({ limit: 5, offset: 0 });
  const latestRun = runs.length > 0 ? runs[0] : undefined;
  const ctaLabel = getCtaLabel(latestRun?.state);
  const ctaDestination = getCtaDestination(latestRun?.id, latestRun?.state);

  return (
    <Card
      className="bg-steel-900/60 border-steel-700"
      data-testid="latest-ai-analysis-widget"
    >
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <Bot className="h-4 w-4 text-steel-500" aria-hidden="true" />
          Latest AI Analysis
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-3" data-testid="latest-ai-analysis-loading">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-4 w-36" />
            <Skeleton className="h-4 w-28" />
          </div>
        )}

        {isError && (
          <div className="space-y-2" data-testid="latest-ai-analysis-error">
            <p className="text-sm text-red-400" role="alert">
              Unable to load AI analysis
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void refetch();
              }}
              data-testid="latest-ai-analysis-retry"
              className="border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
            >
              Retry
            </Button>
          </div>
        )}

        {!isLoading && !isError && !latestRun && (
          <div className="space-y-3" data-testid="latest-ai-analysis-empty">
            <p className="text-sm text-steel-400">
              No AI analysis yet
            </p>
            <Button asChild size="sm" data-testid="latest-ai-analysis-cta">
              <Link to={ctaDestination}>
                {ctaLabel}
                <ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </Button>
          </div>
        )}

        {!isLoading && !isError && latestRun && (
          <div className="space-y-3" data-testid="latest-ai-analysis-content">
            <div className="flex items-center justify-between">
              <span
                className="text-sm font-semibold text-white"
                data-testid="latest-ai-analysis-plan"
              >
                {latestRun.plan_id}
              </span>
              <WorkflowStateBadge state={latestRun.state} />
            </div>
            <div className="flex items-center gap-2 text-xs text-steel-400">
              {latestRun.triggered_by && (
                <span data-testid="latest-ai-analysis-triggered-by">
                  {latestRun.triggered_by}
                </span>
              )}
              {latestRun.triggered_by && latestRun.created_at && (
                <span aria-hidden="true">·</span>
              )}
              {latestRun.created_at && (
                <span data-testid="latest-ai-analysis-timestamp">
                  {formatTimestamp(latestRun.created_at)}
                </span>
              )}
            </div>
            <Button asChild size="sm" data-testid="latest-ai-analysis-cta">
              <Link to={ctaDestination}>
                {ctaLabel}
                <ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
