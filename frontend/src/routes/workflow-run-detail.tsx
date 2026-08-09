import { useParams, Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import axios from 'axios';

import { useWorkflowRun } from '@/hooks/use-workflow-run';
import type {
  AttemptHistoryRecord,
  RecommendationContent,
  WorkflowStep,
} from '@/lib/workflow-api';
import { Button } from '@/components/ui/button';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

// ---------------------------------------------------------------------------
// State label styling (locally styled — no Badge component in repo)
// ---------------------------------------------------------------------------

const STATE_STYLES: Record<string, string> = {
  PENDING: 'bg-steel-600/20 text-steel-300 border-steel-600/40',
  RUNNING: 'bg-blue-600/20 text-blue-300 border-blue-600/40',
  AWAITING_VALIDATION: 'bg-amber-600/20 text-amber-300 border-amber-600/40',
  COMPLETED: 'bg-green-600/20 text-green-300 border-green-600/40',
  FAILED_VALIDATION: 'bg-red-600/20 text-red-300 border-red-600/40',
  FAILED_PROVIDER: 'bg-red-600/20 text-red-300 border-red-600/40',
  FAILED_INTERNAL: 'bg-red-600/20 text-red-300 border-red-600/40',
};

const STEP_STATUS_STYLES: Record<string, string> = {
  started: 'bg-blue-600/20 text-blue-300 border-blue-600/40',
  completed: 'bg-green-600/20 text-green-300 border-green-600/40',
  failed: 'bg-red-600/20 text-red-300 border-red-600/40',
};

const FALLBACK_STYLE = 'bg-steel-600/20 text-steel-300 border-steel-600/40';

function StateLabel({ state }: { state: string }) {
  const style = STATE_STYLES[state] ?? FALLBACK_STYLE;
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${style}`}
      data-testid="run-state-badge"
      data-state={state}
    >
      {state}
    </span>
  );
}

function StepStatusLabel({ status }: { status: string }) {
  const style = STEP_STATUS_STYLES[status] ?? FALLBACK_STYLE;
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${style}`}
      data-testid="step-status-badge"
      data-status={status}
    >
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Retry visibility helpers (defensive narrowing of step_metadata)
// ---------------------------------------------------------------------------

function isNumber(v: unknown): v is number {
  return typeof v === 'number';
}

function isString(v: unknown): v is string {
  return typeof v === 'string';
}

function isAttemptRecord(v: unknown): v is AttemptHistoryRecord {
  return (
    v !== null &&
    typeof v === 'object' &&
    'attempt_number' in v &&
    'outcome' in v &&
    'error_type' in v &&
    'backoff_delay_seconds' in v
  );
}

function RetryInfo({ metadata }: { metadata: Record<string, unknown> }) {
  const retryCount = metadata.retry_count;
  const attemptHistory = metadata.attempt_history;
  const showRetryCount = isNumber(retryCount) && retryCount > 0;
  const history: AttemptHistoryRecord[] = Array.isArray(attemptHistory)
    ? attemptHistory.filter(isAttemptRecord)
    : [];

  if (!showRetryCount && history.length === 0) return null;

  return (
    <div className="mt-2 space-y-1 text-sm text-muted-foreground" data-testid="retry-info">
      {showRetryCount && (
        <div>
          <span className="font-medium">Retries:</span>{' '}
          <span data-testid="retry-count">{retryCount}</span>
        </div>
      )}
      {history.length > 0 && (
        <div className="space-y-1" data-testid="attempt-history">
          <div className="font-medium">Attempt History:</div>
          {history.map((attempt, idx) => (
            <div
              key={idx}
              className="ml-4 space-y-0.5 text-xs"
              data-testid={`attempt-${idx}`}
            >
              <span>
                Attempt{' '}
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
  );
}

// ---------------------------------------------------------------------------
// Step rendering
// ---------------------------------------------------------------------------

function StepRow({ step }: { step: WorkflowStep }) {
  return (
    <div
      className="border-b border-border pb-3 last:border-b-0 last:pb-0"
      data-testid={`step-${step.seq}`}
    >
      <div className="flex items-center gap-3">
        <StepStatusLabel status={step.status} />
        <span className="font-medium">{step.step_name}</span>
        <span className="text-xs text-muted-foreground">#{step.seq}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-4 text-sm text-muted-foreground">
        {step.model_name && (
          <span>
            <span className="font-medium">Model:</span> {step.model_name}
          </span>
        )}
        {step.latency_ms !== null && step.latency_ms !== undefined && (
          <span>
            <span className="font-medium">Latency:</span> {step.latency_ms}ms
          </span>
        )}
        {step.token_usage && (
          <span>
            <span className="font-medium">Tokens:</span>{' '}
            {JSON.stringify(step.token_usage)}
          </span>
        )}
      </div>
      {(step.error_code || step.error_detail) && (
        <div className="mt-2 space-y-0.5 text-sm text-red-300" data-testid="step-errors">
          {step.error_code && (
            <div>
              <span className="font-medium">Error Code:</span>{' '}
              <span data-testid="step-error-code">{step.error_code}</span>
            </div>
          )}
          {step.error_detail && (
            <div>
              <span className="font-medium">Error Detail:</span>{' '}
              <span data-testid="step-error-detail">{step.error_detail}</span>
            </div>
          )}
        </div>
      )}
      {step.step_metadata && typeof step.step_metadata === 'object' && (
        <RetryInfo metadata={step.step_metadata} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recommendation rendering
// ---------------------------------------------------------------------------

function RecommendationSection({
  recommendation,
}: {
  recommendation: NonNullable<ReturnType<typeof useWorkflowRun>['run']>['recommendation'];
}) {
  if (recommendation === null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recommendation</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground" data-testid="no-recommendation">
            No recommendation
          </p>
        </CardContent>
      </Card>
    );
  }

  const content: RecommendationContent | null = recommendation.content;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommendation</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-4 text-sm text-muted-foreground">
          <span>
            <span className="font-medium">Status:</span> {recommendation.status}
          </span>
          {recommendation.schema_version && (
            <span>
              <span className="font-medium">Schema:</span>{' '}
              {recommendation.schema_version}
            </span>
          )}
        </div>
        {content === null && (
          <p
            className="text-muted-foreground"
            data-testid="no-validated-content"
          >
            No validated content available
          </p>
        )}
        {content !== null && (
          <div className="space-y-4">
            {content.risks.map((risk) => (
              <div key={risk.risk_id} className="space-y-2" data-testid={`risk-${risk.risk_id}`}>
                <div className="font-medium">{risk.risk_id}</div>
                <div>
                  <span className="text-xs font-medium text-muted-foreground">Summary:</span>{' '}
                  {risk.summary}
                </div>
                <div>
                  <span className="text-xs font-medium text-muted-foreground">Business Impact:</span>{' '}
                  {risk.business_impact}
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">Recommended Actions:</span>
                  {risk.recommended_actions.map((action, idx) => (
                    <div key={idx} className="ml-4 text-sm">
                      <span className="font-medium">{action.title}</span>{' '}
                      <span className="text-xs text-muted-foreground">({action.action_type})</span>
                      <div className="text-xs text-muted-foreground">{action.rationale}</div>
                      {action.requires_approval && (
                        <div className="text-xs text-amber-300">Requires approval</div>
                      )}
                    </div>
                  ))}
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">Sources:</span>
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
  );
}

// ---------------------------------------------------------------------------
// Duration computation
// ---------------------------------------------------------------------------

function computeDuration(
  startedAt: string | null,
  completedAt: string | null,
): string | null {
  if (!startedAt || !completedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = new Date(completedAt).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null;
  const diff = end - start;
  if (diff < 1000) return `${diff}ms`;
  return `${(diff / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function WorkflowRunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const { run, isLoading, isError, error, refetch } = useWorkflowRun(runId);

  // Not-found detection via Axios contract
  const isNotFound =
    error !== null &&
    axios.isAxiosError(error) &&
    error.response?.status === 404;

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
    );
  }

  // Not-found state (404 via Axios contract)
  if (isNotFound) {
    return (
      <div className="flex flex-col items-center gap-4 p-8" data-testid="not-found-state">
        <AlertCircle className="h-12 w-12 text-muted-foreground" />
        <p className="text-lg text-muted-foreground">Workflow run not found</p>
        <Link to="/">
          <Button variant="outline">Back to Dashboard</Button>
        </Link>
      </div>
    );
  }

  // Error state (non-404)
  if (isError && !run) {
    return (
      <div
        className="flex flex-col items-center gap-4 p-8"
        data-testid="error-state"
      >
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-lg text-destructive">
          Failed to load workflow run details.
        </p>
        <Button onClick={() => refetch()} data-testid="reload-button">
          Reload details
        </Button>
      </div>
    );
  }

  if (!run) return null;

  const duration = computeDuration(run.started_at, run.completed_at);

  return (
    <div className="space-y-4 p-4" data-testid="run-detail">
      {/* Breadcrumb */}
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/">Dashboard</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Workflow Run {run.id}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Run header */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <CardTitle>Workflow Run</CardTitle>
            <StateLabel state={run.state} />
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <div>
            <span className="font-medium">Run ID:</span> {run.id}
          </div>
          <div>
            <span className="font-medium">Correlation ID:</span>{' '}
            {run.correlation_id}
          </div>
          <div>
            <span className="font-medium">Plan ID:</span> {run.plan_id}
          </div>
          {run.triggered_by && (
            <div>
              <span className="font-medium">Triggered By:</span>{' '}
              {run.triggered_by}
            </div>
          )}
          {run.started_at && (
            <div>
              <span className="font-medium">Started:</span> {run.started_at}
            </div>
          )}
          {run.completed_at && (
            <div>
              <span className="font-medium">Completed:</span> {run.completed_at}
            </div>
          )}
          {duration && (
            <div>
              <span className="font-medium">Duration:</span> {duration}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Run-level error banner */}
      {(run.error_code || run.error_detail) && (
        <Card>
          <CardHeader>
            <CardTitle>Error</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-red-300" data-testid="run-error-banner">
            {run.error_code && (
              <div>
                <span className="font-medium">Error Code:</span> {run.error_code}
              </div>
            )}
            {run.error_detail && (
              <div>
                <span className="font-medium">Error Detail:</span> {run.error_detail}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Steps */}
      <Card>
        <CardHeader>
          <CardTitle>Steps</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {run.steps.length === 0 ? (
            <p className="text-muted-foreground">No steps recorded</p>
          ) : (
            run.steps.map((step) => <StepRow key={step.id} step={step} />)
          )}
        </CardContent>
      </Card>

      {/* Recommendation */}
      <RecommendationSection recommendation={run.recommendation} />
    </div>
  );
}
