import { useParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AlertCircle } from 'lucide-react'
import axios from 'axios'

import { useWorkflowRun } from '@/hooks/use-workflow-run'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import type {
  AttemptHistoryRecord,
  RecommendationContent,
  WorkflowStep,
} from '@/lib/workflow-api'
import { Button } from '@/components/ui/button'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

// ---------------------------------------------------------------------------
// State/status presentation: migrated to the WP-UX-UA-04 localized status
// registry (StatusBadge). Raw state enum values remain available as machine
// metadata on ``data-code`` attributes and are never the primary label.
// ---------------------------------------------------------------------------

import StatusBadge from '@/components/status/StatusBadge'

// ---------------------------------------------------------------------------
// Retry visibility helpers (defensive narrowing of step_metadata)
// ---------------------------------------------------------------------------

function isNumber(v: unknown): v is number {
  return typeof v === 'number'
}

function isString(v: unknown): v is string {
  return typeof v === 'string'
}

function isAttemptRecord(v: unknown): v is AttemptHistoryRecord {
  return (
    v !== null &&
    typeof v === 'object' &&
    'attempt_number' in v &&
    'outcome' in v &&
    'error_type' in v &&
    'backoff_delay_seconds' in v
  )
}

function RetryInfo({
  metadata,
  t,
}: {
  metadata: Record<string, unknown>;
  t: (key: string) => string;
}) {
  const retryCount = metadata.retry_count
  const attemptHistory = metadata.attempt_history
  const showRetryCount = isNumber(retryCount) && retryCount > 0
  const history: AttemptHistoryRecord[] = Array.isArray(attemptHistory)
    ? attemptHistory.filter(isAttemptRecord)
    : []

  if (!showRetryCount && history.length === 0) return null

  return (
    <div className="mt-2 space-y-1 text-sm text-muted-foreground" data-testid="retry-info">
      {showRetryCount && (
        <div>
          <span className="font-medium">{t('retry.retries')}</span>{' '}
          <span data-testid="retry-count">{retryCount}</span>
        </div>
      )}
      {history.length > 0 && (
        <div className="space-y-1" data-testid="attempt-history">
          <div className="font-medium">{t('retry.attemptHistory')}</div>
          {history.map((attempt, idx) => (
            <div
              key={idx}
              className="ml-4 space-y-0.5 text-xs"
              data-testid={`attempt-${idx}`}
            >
              <span>
                {t('retry.attempt')}{' '}
                <span data-testid="attempt-number">{attempt.attempt_number}</span>
              </span>
              {' — '}
              <span data-testid="attempt-outcome">{attempt.outcome}</span>
              {isString(attempt.error_type) && attempt.error_type !== '' && (
                <>
                  {' — '}
                  <span data-testid="attempt-error-type">{attempt.error_type}</span>
                </>
              )}
              {isNumber(attempt.backoff_delay_seconds) && (
                <>
                  {' — '}
                  <span data-testid="attempt-backoff">
                    {attempt.backoff_delay_seconds}s
                  </span>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step rendering
// ---------------------------------------------------------------------------

function StepRow({ step, t }: { step: WorkflowStep; t: (key: string) => string }) {
  return (
    <div
      className="border-b border-border pb-3 last:border-b-0 last:pb-0"
      data-testid={`step-${step.seq}`}
    >
      <div className="flex items-center gap-3">
        <StatusBadge
          domain="workflowStep"
          code={step.status}
          testId="step-status-badge"
        />
        <span className="font-medium">{step.step_name}</span>
        <span className="text-xs text-muted-foreground">#{step.seq}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-4 text-sm text-muted-foreground">
        {step.model_name && (
          <span>
            <span className="font-medium">{t('steps.model')}</span> {step.model_name}
          </span>
        )}
        {step.latency_ms !== null && step.latency_ms !== undefined && (
          <span>
            <span className="font-medium">{t('steps.latency')}</span> {step.latency_ms}ms
          </span>
        )}
        {step.token_usage && (
          <span>
            <span className="font-medium">{t('steps.tokens')}</span>{' '}
            {JSON.stringify(step.token_usage)}
          </span>
        )}
      </div>
      {(step.error_code || step.error_detail) && (
        <div className="mt-2 space-y-0.5 text-sm text-red-300" data-testid="step-errors">
          {step.error_code && (
            <div>
              <span className="font-medium">{t('steps.errorCode')}</span>{' '}
              <span data-testid="step-error-code">{step.error_code}</span>
            </div>
          )}
          {step.error_detail && (
            <div>
              <span className="font-medium">{t('steps.errorDetail')}</span>{' '}
              <span data-testid="step-error-detail">{step.error_detail}</span>
            </div>
          )}
        </div>
      )}
      {step.step_metadata && typeof step.step_metadata === 'object' && (
        <RetryInfo metadata={step.step_metadata} t={t} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Recommendation rendering
// ---------------------------------------------------------------------------

function RecommendationSection({
  recommendation,
  t,
}: {
  recommendation: NonNullable<ReturnType<typeof useWorkflowRun>['run']>['recommendation'];
  t: (key: string) => string;
}) {
  if (recommendation === null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('recommendation.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground" data-testid="no-recommendation">
            {t('recommendation.empty')}
          </p>
        </CardContent>
      </Card>
    )
  }

  const content: RecommendationContent | null = recommendation.content

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('recommendation.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="font-medium">{t('fields.status')}</span>
            <StatusBadge
              domain="recommendation"
              code={recommendation.status}
              testId="recommendation-status"
            />
          </span>
          {recommendation.schema_version && (
            <span>
              <span className="font-medium">{t('fields.schema')}</span>{' '}
              {recommendation.schema_version}
            </span>
          )}
        </div>
        {content === null && (
          <p
            className="text-muted-foreground"
            data-testid="no-validated-content"
          >
            {t('recommendation.noValidatedContent')}
          </p>
        )}
        {content !== null && (
          <div className="space-y-4">
            {content.risks.map((risk) => (
              <div key={risk.risk_id} className="space-y-2" data-testid={`risk-${risk.risk_id}`}>
                <div className="font-medium">{risk.risk_id}</div>
                <div>
                  <span className="text-xs font-medium text-muted-foreground">{t('recommendation.summary')}</span>{' '}
                  {risk.summary}
                </div>
                <div>
                  <span className="text-xs font-medium text-muted-foreground">{t('recommendation.businessImpact')}</span>{' '}
                  {risk.business_impact}
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{t('recommendation.recommendedActions')}</span>
                  {risk.recommended_actions.map((action, idx) => (
                    <div key={idx} className="ml-4 text-sm">
                      <span className="font-medium">{action.title}</span>{' '}
                      <span className="text-xs text-muted-foreground">({action.action_type})</span>
                      <div className="text-xs text-muted-foreground">{action.rationale}</div>
                      {action.requires_approval && (
                        <div className="text-xs text-amber-300">{t('recommendation.requiresApproval')}</div>
                      )}
                    </div>
                  ))}
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">{t('recommendation.sources')}</span>
                  {risk.sources.map((source, idx) => (
                    <div key={idx} className="ml-4 text-xs text-muted-foreground">
                      {source.document_id} (v{source.version})
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Duration computation
// ---------------------------------------------------------------------------

function computeDuration(
  startedAt: string | null,
  completedAt: string | null,
): string | null {
  if (!startedAt || !completedAt) return null
  const start = new Date(startedAt).getTime()
  const end = new Date(completedAt).getTime()
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null
  const diff = end - start
  if (diff < 1000) return `${diff}ms`
  return `${(diff / 1000).toFixed(1)}s`
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function WorkflowRunDetail() {
  const { t } = useTranslation('workflow')
  const { formatDateTime } = useLocalizedFormatters()
  const { runId } = useParams<{ runId: string }>()
  const { run, isLoading, isError, error, refetch } = useWorkflowRun(runId)

  // Not-found detection via Axios contract
  const isNotFound =
    error !== null &&
    axios.isAxiosError(error) &&
    error.response?.status === 404

  // Loading state
  if (isLoading && !run) {
    return (
      <div className="space-y-4 p-4" data-testid="loading-state">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  // Not-found state (404 via Axios contract)
  if (isNotFound) {
    return (
      <div className="flex flex-col items-center gap-4 p-8" data-testid="not-found-state">
        <AlertCircle className="h-12 w-12 text-muted-foreground" />
        <p className="text-lg text-muted-foreground">{t('notFound')}</p>
        <Link to="/">
          <Button variant="outline">{t('backToDashboard')}</Button>
        </Link>
      </div>
    )
  }

  // Error state (non-404)
  if (isError && !run) {
    return (
      <div
        className="flex flex-col items-center gap-4 p-8"
        data-testid="error-state"
      >
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-lg text-destructive">{t('loadFailed')}</p>
        <Button onClick={() => refetch()} data-testid="reload-button">
          {t('reload')}
        </Button>
      </div>
    )
  }

  if (!run) return null

  const duration = computeDuration(run.started_at, run.completed_at)

  return (
    <div className="space-y-4 p-4" data-testid="run-detail">
      {/* Breadcrumb */}
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/">{t('breadcrumb.dashboard')}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{t('breadcrumb.run', { runId: run.id })}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Run header */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <CardTitle>{t('title')}</CardTitle>
            <StatusBadge
              domain="workflowRun"
              code={run.state}
              showCode
              testId="run-state-badge"
            />
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <div>
            <span className="font-medium">{t('fields.runId')}</span> {run.id}
          </div>
          <div>
            <span className="font-medium">{t('fields.correlationId')}</span>{' '}
            {run.correlation_id}
          </div>
          <div>
            <span className="font-medium">{t('fields.planId')}</span> {run.plan_id}
          </div>
          {run.triggered_by && (
            <div>
              <span className="font-medium">{t('fields.triggeredBy')}</span>{' '}
              {run.triggered_by}
            </div>
          )}
          {run.started_at && (
            <div>
              <span className="font-medium">{t('fields.started')}</span> {formatDateTime(run.started_at)}
            </div>
          )}
          {run.completed_at && (
            <div>
              <span className="font-medium">{t('fields.completed')}</span> {formatDateTime(run.completed_at)}
            </div>
          )}
          {duration && (
            <div>
              <span className="font-medium">{t('fields.duration')}</span> {duration}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Run-level error banner */}
      {(run.error_code || run.error_detail) && (
        <Card>
          <CardHeader>
            <CardTitle>{t('error.title')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-red-300" data-testid="run-error-banner">
            {run.error_code && (
              <div>
                <span className="font-medium">{t('error.errorCode')}</span> {run.error_code}
              </div>
            )}
            {run.error_detail && (
              <div>
                <span className="font-medium">{t('error.errorDetail')}</span> {run.error_detail}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Steps */}
      <Card>
        <CardHeader>
          <CardTitle>{t('steps.title')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {run.steps.length === 0 ? (
            <p className="text-muted-foreground">{t('steps.empty')}</p>
          ) : (
            run.steps.map((step) => <StepRow key={step.id} step={step} t={t} />)
          )}
        </CardContent>
      </Card>

      {/* Recommendation */}
      <RecommendationSection recommendation={run.recommendation} t={t} />
    </div>
  )
}
