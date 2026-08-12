import { useState, useCallback, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { AlertCircle, Loader2, RotateCw, Sparkles } from 'lucide-react';

import { useActivePlan } from '@/hooks/useActivePlan';
import { useRisks } from '@/hooks/useRisks';
import { useRiskDetail } from '@/hooks/useRiskDetail';
import { useAuth } from '@/contexts/auth.context';
import { useWorkflowRun } from '@/hooks/use-workflow-run';
import { useWorkflowStart } from '@/hooks/use-workflow-start';
import { useWorkflowRetry } from '@/hooks/use-workflow-retry';
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
import { RiskSummary } from '@/components/supply-risk/RiskSummary';
import { EvidencePanel } from '@/components/supply-risk/EvidencePanel';
import { ComponentPanel } from '@/components/supply-risk/ComponentPanel';
import { InventoryPanel } from '@/components/supply-risk/InventoryPanel';
import { IncomingSupplyPanel } from '@/components/supply-risk/IncomingSupplyPanel';
import { ProductionOrderPanel } from '@/components/supply-risk/ProductionOrderPanel';
import { PlanContextPanel } from '@/components/supply-risk/PlanContextPanel';
import { PartialFailurePlaceholder } from '@/components/supply-risk/PartialFailurePlaceholder';
import { Skeleton } from '@/components/ui/skeleton';

export default function SupplyRiskDetail() {
  const { riskId } = useParams<{ riskId: string }>();
  const navigate = useNavigate();

  // Fetch active plan
  const { activePlan, isLoading: planLoading, error: planError } = useActivePlan();

  // Fetch risks for the active plan
  const { risks, isLoading: risksLoading, error: risksError } = useRisks(activePlan?.code ?? null);

  // Fetch risk detail and enrichment data
  const {
    risk,
    component,
    inventory,
    purchaseOrders,
    purchaseOrdersPartial,
    productionOrder,
    productionPlan,
    isLoading: detailLoading,
    componentError,
    inventoryError,
    purchaseOrderError,
    productionOrderError,
    productionPlanError,
    refetchComponent,
    refetchInventory,
    refetchPurchaseOrders,
    refetchProductionOrder,
    refetchProductionPlan,
  } = useRiskDetail({ risks, riskId: riskId ?? '' });

  // -----------------------------------------------------------------------
  // Workflow start/retry/polling (WP-REC-03G)
  // -----------------------------------------------------------------------

  /**
   * Active workflow run ID. Set by successful start or retry, feeding
   * the existing useWorkflowRun polling hook. This is the single source
   * of truth for the currently-polled run — no duplicate polling logic.
   */
  const [activeRunId, setActiveRunId] = useState<string | undefined>(undefined);

  const { user } = useAuth();

  // Role normalization: backend returns UPPERCASE, frontend uses lowercase.
  const isProductionManager = (user?.roles ?? []).some(
    (r) => r.trim().toLowerCase() === 'production_manager',
  );

  // -----------------------------------------------------------------------
  // Plan-change guard (E1): Reset activeRunId when the active plan changes.
  // Without this, a run belonging to one plan could remain displayed after
  // navigating to another plan's risk detail. The effect tracks the previous
  // plan code and clears activeRunId when it changes, preventing cross-plan
  // state leaks. This also disables polling (useWorkflowRun is gated by
  // activeRunId) so no stale run is fetched.
  // -----------------------------------------------------------------------
  const currentPlanCode = activePlan?.code;
  // Live ref updated every render — mutation callbacks read this to detect
  // plan changes that occurred after the mutation was initiated. Using a ref
  // (instead of the closure-captured activePlan) ensures the callback sees
  // the current plan, not the plan from the render that started the mutation.
  const currentPlanCodeRef = useRef<string | undefined>(currentPlanCode);
  currentPlanCodeRef.current = currentPlanCode;
  const prevPlanCodeRef = useRef<string | null>(null);
  useEffect(() => {
    if (
      prevPlanCodeRef.current !== null &&
      prevPlanCodeRef.current !== currentPlanCode
    ) {
      setActiveRunId(undefined);
    }
    prevPlanCodeRef.current = currentPlanCode ?? null;
  }, [currentPlanCode]);

  const workflowStart = useWorkflowStart();
  const workflowRetry = useWorkflowRetry();
  const queryClient = useQueryClient();
  const { run: workflowRun, isError: workflowPollingError, error: workflowPollingErrorDetail } =
    useWorkflowRun(activeRunId);

  // Retry-eligible terminal failure states (canonical, from
  // backend/app/ai/workflow/state_machine.py).
  const RETRY_ELIGIBLE_STATES = new Set<string>([
    'FAILED_PROVIDER',
    'FAILED_VALIDATION',
    'FAILED_INTERNAL',
  ]);

  // Terminal states (no outgoing transitions except user-initiated retry).
  const TERMINAL_STATES = new Set<string>([
    'COMPLETED',
    'FAILED_VALIDATION',
    'FAILED_PROVIDER',
    'FAILED_INTERNAL',
  ]);

  const workflowState = workflowRun?.state;
  const isRetryEligible =
    workflowState !== undefined && RETRY_ELIGIBLE_STATES.has(workflowState);
  const isWorkflowRunning =
    workflowState !== undefined && !TERMINAL_STATES.has(workflowState);

  // Show Start only when no known run exists (no activeRunId) and no
  // non-terminal workflow is active. A polling error for an existing
  // activeRunId must NOT re-enable Start — that would allow a duplicate
  // start request for an unresolved run (Target A).
  const canStart =
    isProductionManager &&
    activeRunId === undefined &&
    (workflowState === undefined || workflowState === 'COMPLETED');

  // Show Retry only when a run exists, is in a retry-eligible terminal
  // failure state, and the user is authorized. Per D2, the backend permits
  // retry by the run creator OR PRODUCTION_MANAGER. The frontend can
  // determine creator ownership from the workflow-run response's
  // triggered_by field, which is the username stored on creation.
  // The button is shown (but disabled) while the retry mutation is pending.
  const isRunCreator =
    workflowRun?.triggered_by !== null &&
    workflowRun?.triggered_by !== undefined &&
    user?.username !== undefined &&
    workflowRun.triggered_by === user.username;
  const canRetry = (isProductionManager || isRunCreator) && isRetryEligible;

  const handleStart = useCallback(() => {
    if (!activePlan) return;
    const startedPlanCode = activePlan.code;
    workflowStart.mutate(
      { plan_id: startedPlanCode },
      {
        onSuccess: (data) => {
          // Guard against stale completion after plan navigation (Target C):
          // only install the run_id if the active plan hasn't changed.
          // Read the live plan code from the ref — the closure-captured
          // activePlan is frozen at the render that initiated the mutation.
          if (currentPlanCodeRef.current !== startedPlanCode) return;
          setActiveRunId(data.run_id);
        },
      },
    );
  }, [activePlan, workflowStart]);

  const handleRetry = useCallback(() => {
    if (!activeRunId) return;
    const retryPlanCode = activePlan?.code;
    workflowRetry.mutate(activeRunId, {
      onSuccess: (data) => {
        // Guard against stale completion after plan navigation (Target C).
        // Read the live plan code from the ref — the closure-captured
        // activePlan is frozen at the render that initiated the mutation.
        // MUST check staleness BEFORE invalidation — a stale response must
        // not trigger query invalidation for the old plan's run.
        if (retryPlanCode !== undefined && currentPlanCodeRef.current !== retryPlanCode) return;
        // Invalidate the cached workflow-run query so polling resumes
        // with fresh data after the D1 FAILED_* → PENDING transition.
        void queryClient.invalidateQueries({
          queryKey: ['workflow-run', data.run_id],
        });
        setActiveRunId(data.run_id);
      },
    });
  }, [activeRunId, activePlan, workflowRetry, queryClient]);

  // Safe error message extraction — no raw stack traces or internal details.
  // Only backend-provided messages from the structured error response
  // (FastAPI default: {"detail": {"error": "...", "message": "..."}})
  // are considered safe for display. The generic error.message fallback
  // is NOT used because it may contain transport-library messages,
  // internal URLs, or provider details not intended for users (Target F).
  function extractSafeErrorMessage(error: Error | null): string {
    if (!error) return '';
    // Axios errors may carry a backend-provided message in response.data.
    if (typeof error === 'object' && 'response' in error) {
      const response = (
        error as { response?: { data?: { detail?: { message?: string }; message?: string } } }
      ).response;
      // FastAPI HTTPException wraps detail dict: {"detail": {"message": "..."}}
      const detail = response?.data?.detail;
      if (detail && typeof detail === 'object' && detail.message) {
        return detail.message;
      }
      // Some non-FastAPI endpoints may use top-level message.
      if (response?.data?.message) {
        return response.data.message;
      }
    }
    return 'An unexpected error occurred.';
  }

  // Loading state — only full-page while active plan or risks list are loading
  if (planLoading || risksLoading) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Loading risk...</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    );
  }

  // Active plan error
  if (planError) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Error</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">Failed to load active plan</h2>
                <p className="text-sm text-muted-foreground mt-1">{planError.message}</p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>Back to Supply Risks</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // No active plan
  if (!activePlan) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>No Active Plan</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-muted-foreground" />
              <div>
                <h2 className="text-lg font-semibold">No active production plan</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Please select a production plan from the Supply Risks page.
                </p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>Back to Supply Risks</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Risks fetch error
  if (risksError) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Error</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">Failed to load risks</h2>
                <p className="text-sm text-muted-foreground mt-1">{risksError.message}</p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>Back to Supply Risks</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Risk not found (stale/unknown risk)
  // riskFound is true only when risks have loaded and risk matched.
  // If risks loaded but no match → stale/unknown.
  if (!detailLoading && risks.length > 0 && !risk) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Risk Not Found</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">Risk not found</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Risk ID &quot;{riskId}&quot; does not exist in the current production plan,
                  or the plan data has changed.
                </p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>Back to Supply Risks</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Still loading detail (enrichment panels)
  if (detailLoading || !risk) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Loading risk...</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <div className="space-y-4">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/supply-risk">Supply Risks</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{risk.risk_id}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Page heading */}
      <h1 className="text-2xl font-bold text-white">Risk {risk.risk_id}</h1>

      {/* Risk Summary */}
      <RiskSummary risk={risk} />

      {/* Workflow AI Analysis Panel (WP-REC-03G) */}
      <Card data-testid="workflow-panel">
        <CardHeader>
          <CardTitle>AI Analysis</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Start AI Analysis button — PRODUCTION_MANAGER only */}
          {canStart && (
            <Button
              onClick={handleStart}
              disabled={workflowStart.isPending}
              data-testid="start-workflow-button"
            >
              {workflowStart.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Start AI Analysis
                </>
              )}
            </Button>
          )}

          {/* Start mutation failure — safe error display */}
          {workflowStart.isError && (
            <div
              className="flex items-start gap-3 rounded-md border border-red-600/30 bg-red-600/10 px-4 py-3"
              data-testid="workflow-start-error"
              role="alert"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" aria-hidden="true" />
              <div className="flex-1">
                <p className="text-sm font-medium text-red-300">
                  Failed to start AI analysis
                </p>
                <p className="mt-1 text-xs text-red-400">
                  {extractSafeErrorMessage(workflowStart.error)}
                </p>
              </div>
            </div>
          )}

          {/* Retry button — retry-eligible terminal failure + authorized user */}
          {canRetry && (
            <Button
              onClick={handleRetry}
              disabled={workflowRetry.isPending}
              variant="outline"
              data-testid="retry-workflow-button"
            >
              {workflowRetry.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Retrying...
                </>
              ) : (
                <>
                  <RotateCw className="h-4 w-4" />
                  Retry
                </>
              )}
            </Button>
          )}

          {/* Retry mutation failure — safe error display */}
          {workflowRetry.isError && (
            <div
              className="flex items-start gap-3 rounded-md border border-red-600/30 bg-red-600/10 px-4 py-3"
              data-testid="workflow-retry-error"
              role="alert"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" aria-hidden="true" />
              <div className="flex-1">
                <p className="text-sm font-medium text-red-300">
                  Failed to retry workflow
                </p>
                <p className="mt-1 text-xs text-red-400">
                  {extractSafeErrorMessage(workflowRetry.error)}
                </p>
              </div>
            </div>
          )}

          {/* Workflow status display — non-blocking, inline */}
          {workflowState !== undefined && (
            <div
              className="flex items-center gap-2 text-sm"
              data-testid="workflow-status"
            >
              {isWorkflowRunning && (
                <Loader2 className="h-4 w-4 animate-spin text-blue-400" aria-hidden="true" />
              )}
              <span className="text-muted-foreground">Workflow state:</span>
              <span
                className="font-medium"
                data-testid="workflow-state"
                data-state={workflowState}
              >
                {workflowState}
              </span>
              {isWorkflowRunning && (
                <span className="text-xs text-muted-foreground">
                  (updates automatically)
                </span>
              )}
            </div>
          )}

          {/* Workflow polling/detail API failure — safe error display */}
          {workflowPollingError && (
            <div
              className="flex items-start gap-3 rounded-md border border-red-600/30 bg-red-600/10 px-4 py-3"
              data-testid="workflow-polling-error"
              role="alert"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" aria-hidden="true" />
              <div className="flex-1">
                <p className="text-sm font-medium text-red-300">
                  Failed to load workflow status
                </p>
                <p className="mt-1 text-xs text-red-400">
                  {extractSafeErrorMessage(workflowPollingErrorDetail) || 'The workflow status could not be loaded. The page remains usable.'}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Evidence Panel */}
      <EvidencePanel risk={risk} />

      {/* Component Panel */}
      {component ? (
        <ComponentPanel component={component} />
      ) : componentError ? (
        <PartialFailurePlaceholder
          label="Component Details"
          error={componentError}
          onRetry={refetchComponent}
        />
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Inventory Panel */}
      {inventory ? (
        <InventoryPanel inventory={inventory} />
      ) : inventoryError ? (
        <PartialFailurePlaceholder
          label="Inventory"
          error={inventoryError}
          onRetry={refetchInventory}
        />
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-40 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Incoming Supply Panel */}
      {purchaseOrderError ? (
        <PartialFailurePlaceholder
          label="Incoming Supply"
          error={purchaseOrderError}
          onRetry={refetchPurchaseOrders}
        />
      ) : purchaseOrders.length > 0 ? (
        <IncomingSupplyPanel
          purchaseOrders={purchaseOrders}
          isPartial={purchaseOrdersPartial}
        />
      ) : !detailLoading ? (
        <Card>
          <CardHeader>
            <CardTitle>Incoming Supply</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">No incoming supply orders found for this component.</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Production Order Panel */}
      {productionOrder ? (
        <ProductionOrderPanel productionOrder={productionOrder} />
      ) : productionOrderError ? (
        <PartialFailurePlaceholder
          label="Production Order"
          error={productionOrderError}
          onRetry={refetchProductionOrder}
        />
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Plan Context Panel */}
      {productionPlan ? (
        <PlanContextPanel productionPlan={productionPlan} />
      ) : productionPlanError ? (
        <PartialFailurePlaceholder
          label="Production Plan"
          error={productionPlanError}
          onRetry={refetchProductionPlan}
        />
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
