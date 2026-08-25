/**
 * Latest AI Analysis widget — replaces the stale "Latest Agent Runs —
 * Unavailable — Phase 5" placeholder.
 *
 * Shows the most recent workflow run with business-facing state, plan,
 * timestamp, and a state-aware CTA that routes to:
 *   - existing run → /workflow-runs/{run_id}
 *   - no run       → /supply-risk
 *
 * Localized per WP-UX-UA-03; the workflow state badge keeps its machine
 * status label (WP-UX-UA-04 scope), and the timestamp formats with the
 * active locale.
 */

import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Bot, ArrowRight } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import WorkflowStateBadge from '@/components/dashboard/WorkflowStateBadge'
import { useWorkflowRuns } from '@/hooks/use-workflow-runs'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import {
  isNonterminalState,
  isFailedState,
} from '@/lib/workflow-state-labels'

/**
 * Determine the CTA label key for a given run state.
 */
function getCtaLabelKey(state: string | null | undefined): string {
  if (!state) return 'widgets.latestAiAnalysis.reviewSupplyRisks'
  if (state === 'COMPLETED') return 'widgets.latestAiAnalysis.viewRecommendation'
  if (isNonterminalState(state)) return 'widgets.latestAiAnalysis.viewProgress'
  if (isFailedState(state)) return 'widgets.latestAiAnalysis.reviewFailure'
  return 'widgets.latestAiAnalysis.reviewSupplyRisks'
}

/**
 * Determine the CTA destination for a given run.
 */
function getCtaDestination(runId: string | undefined, state: string | null | undefined): string {
  if (runId && state) return `/workflow-runs/${runId}`
  return '/supply-risk'
}

export default function LatestAIAnalysisWidget() {
  const { t } = useTranslation('dashboard')
  const { runs, isLoading, isError, refetch } = useWorkflowRuns({ limit: 5, offset: 0 })
  const { formatDateTime } = useLocalizedFormatters()
  const latestRun = runs.length > 0 ? runs[0] : undefined
  const ctaLabel = t(getCtaLabelKey(latestRun?.state))
  const ctaDestination = getCtaDestination(latestRun?.id, latestRun?.state)

  return (
    <Card data-testid="latest-ai-analysis-widget">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <Bot className="h-4 w-4 text-steel-500" aria-hidden="true" />
          {t('widgets.latestAiAnalysis.title')}
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
              {t('widgets.latestAiAnalysis.error')}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void refetch()
              }}
              data-testid="latest-ai-analysis-retry"
              className="border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
            >
              {t('common:actions.retry')}
            </Button>
          </div>
        )}

        {!isLoading && !isError && !latestRun && (
          <div className="space-y-3" data-testid="latest-ai-analysis-empty">
            <p className="text-sm text-steel-400">
              {t('widgets.latestAiAnalysis.empty')}
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
                  {formatDateTime(latestRun.created_at)}
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
  )
}
