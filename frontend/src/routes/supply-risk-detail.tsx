import { useState, useCallback, useEffect, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Loader2, RotateCw, Sparkles } from 'lucide-react'

import { useActivePlan } from '@/hooks/useActivePlan'
import { useRisks } from '@/hooks/useRisks'
import { useRiskDetail } from '@/hooks/useRiskDetail'
import { useAuth } from '@/contexts/auth.context'
import { useWorkflowRun } from '@/hooks/use-workflow-run'
import { useWorkflowStart } from '@/hooks/use-workflow-start'
import { useWorkflowRetry } from '@/hooks/use-workflow-retry'
import { useWorkflowRuns } from '@/hooks/use-workflow-runs'
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
import { RiskSummary } from '@/components/supply-risk/RiskSummary'
import { EvidencePanel } from '@/components/supply-risk/EvidencePanel'
import { ComponentPanel } from '@/components/supply-risk/ComponentPanel'
import { InventoryPanel } from '@/components/supply-risk/InventoryPanel'
import { IncomingSupplyPanel } from '@/components/supply-risk/IncomingSupplyPanel'
import { ProductionOrderPanel } from '@/components/supply-risk/ProductionOrderPanel'
import { PlanContextPanel } from '@/components/supply-risk/PlanContextPanel'
import { PartialFailurePlaceholder } from '@/components/supply-risk/PartialFailurePlaceholder'
import RecommendationForRisk from '@/components/supply-risk/RecommendationForRisk'
import WorkflowStateBadge from '@/components/dashboard/WorkflowStateBadge'
import { ApprovalRequestConfirmation } from '@/components/approval/approval-request-confirmation'
import { useApprovalCreate } from '@/hooks/use-approval-create'
import { Skeleton } from '@/components/ui/skeleton'
import {
  isNonterminalState,
  isFailedState,
} from '@/lib/workflow-state-labels'
import type { RecommendedAction } from '@/lib/workflow-api'

export default function SupplyRiskDetail() {
  const { t } = useTranslation('riskDetail')
  const { riskId } = useParams<{ riskId: string }>()
  const navigate = useNavigate()

  // Fetch active plan
  const { activePlan, isLoading: planLoading, error: planError } = useActivePlan()

  // Fetch risks for the active plan
  const { risks, isLoading: risksLoading, error: risksError } = useRisks(activePlan?.code ?? null)

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
  } = useRiskDetail({ risks, riskId: riskId ?? '' })

  // -----------------------------------------------------------------------
  // WP-UX-02: Plan-scoped latest-run restoration
  // -----------------------------------------------------------------------
  const currentPlanCode = activePlan?.code

  const {
    runs: planRuns,
    total: planRunTotal,
    isLoading: restorationLoading,
    isError: restorationError,
    queriedPlanCode,
    isDisabled: restorationDisabled,
    refetch: refetchRestoration,
  } = useWorkflowRuns(
    currentPlanCode
      ? { planCode: currentPlanCode, limit: 1, offset: 0, enabled: true }
      : { limit: 1, offset: 0, enabled: false },
  )

  // The latest run for this plan (first item due to created_at DESC ordering).
  const restoredRun = planRuns.length > 0 ? planRuns[0] : undefined
  const hasExistingRun = planRunTotal > 0 && restoredRun !== undefined

  const [activeRunId, setActiveRunId] = useState<string | undefined>(undefined)

  useEffect(() => {
    if (
      hasExistingRun &&
      restoredRun &&
      !activeRunId &&
      !restorationDisabled &&
      queriedPlanCode !== null &&
      queriedPlanCode === currentPlanCode
    ) {
      setActiveRunId(restoredRun.id)
    }
  }, [hasExistingRun, restoredRun, activeRunId, restorationDisabled, queriedPlanCode, currentPlanCode])

  const { user } = useAuth()

  // Role normalization: backend returns UPPERCASE, frontend uses lowercase.
  const isProductionManager = (user?.roles ?? []).some(
    (r) => r.trim().toLowerCase() === 'production_manager',
  )

  // Guided approval creation (WP-UX-UA-05): the selected eligible action
  // drives a prefilled confirmation dialog; no UUID is entered manually.
  const approvalCreate = useApprovalCreate()
  const [approvalAction, setApprovalAction] = useState<RecommendedAction | null>(null)
  const approvalTriggerRef = useRef<HTMLElement | null>(null)

  // Capture the element that opened the dialog so focus can be returned to
  // it on close (WP-UX-UA-05-R1 F3).
  function openApprovalDialog(action: RecommendedAction) {
    const active = document.activeElement
    approvalTriggerRef.current = active instanceof HTMLElement ? active : null
    setApprovalAction(action)
  }

  function closeApprovalDialog() {
    setApprovalAction(null)
    const trigger = approvalTriggerRef.current
    approvalTriggerRef.current = null
    // Return focus to the trigger when it is still in the document.
    if (trigger && trigger.isConnected) {
      trigger.focus()
    }
  }

  // Plan-change guard (E1): Reset activeRunId when the active plan changes.
  const currentPlanCodeRef = useRef<string | undefined>(currentPlanCode)
  currentPlanCodeRef.current = currentPlanCode
  const prevPlanCodeRef = useRef<string | null>(null)
  useEffect(() => {
    if (
      prevPlanCodeRef.current !== null &&
      prevPlanCodeRef.current !== currentPlanCode
    ) {
      setActiveRunId(undefined)
    }
    prevPlanCodeRef.current = currentPlanCode ?? null
  }, [currentPlanCode])

  const workflowStart = useWorkflowStart()
  const workflowRetry = useWorkflowRetry()
  const queryClient = useQueryClient()
  const { run: workflowRun, isError: workflowPollingError, error: workflowPollingErrorDetail } =
    useWorkflowRun(activeRunId)

  // Retry-eligible terminal failure states (canonical, from
  // backend/app/ai/workflow/state_machine.py).
  const RETRY_ELIGIBLE_STATES = new Set<string>([
    'FAILED_PROVIDER',
    'FAILED_VALIDATION',
    'FAILED_INTERNAL',
    'FAILED_RETRIEVAL',
  ])

  // Terminal states (no outgoing transitions except user-initiated retry).
  const TERMINAL_STATES = new Set<string>([
    'COMPLETED',
    'FAILED_VALIDATION',
    'FAILED_PROVIDER',
    'FAILED_INTERNAL',
    'FAILED_RETRIEVAL',
  ])

  const workflowState = workflowRun?.state
  const isRetryEligible =
    workflowState !== undefined && RETRY_ELIGIBLE_STATES.has(workflowState)
  const isWorkflowRunning =
    workflowState !== undefined && !TERMINAL_STATES.has(workflowState)

  const restorationPending =
    (restorationLoading || restorationDisabled) && currentPlanCode !== undefined
  const restorationFailed =
    restorationError && !restorationDisabled && !restorationLoading
  const canStart =
    isProductionManager &&
    !restorationPending &&
    !restorationFailed &&
    activeRunId === undefined &&
    (workflowState === undefined || workflowState === 'COMPLETED') &&
    !hasExistingRun

  const isRunCreator =
    workflowRun?.triggered_by !== null &&
    workflowRun?.triggered_by !== undefined &&
    user?.username !== undefined &&
    workflowRun.triggered_by === user.username
  const canRetry = (isProductionManager || isRunCreator) && isRetryEligible

  const handleStart = useCallback(() => {
    if (!activePlan) return
    const startedPlanCode = activePlan.code
    workflowStart.mutate(
      { plan_id: startedPlanCode },
      {
        onSuccess: (data) => {
          if (currentPlanCodeRef.current !== startedPlanCode) return
          setActiveRunId(data.run_id)
          void queryClient.invalidateQueries({
            queryKey: ['workflow-runs', startedPlanCode],
          })
        },
      },
    )
  }, [activePlan, workflowStart, queryClient])

  const handleRetry = useCallback(() => {
    if (!activeRunId) return
    const retryPlanCode = activePlan?.code
    workflowRetry.mutate(activeRunId, {
      onSuccess: (data) => {
        if (retryPlanCode !== undefined && currentPlanCodeRef.current !== retryPlanCode) return
        void queryClient.invalidateQueries({
          queryKey: ['workflow-run', data.run_id],
        })
        setActiveRunId(data.run_id)
      },
    })
  }, [activeRunId, activePlan, workflowRetry, queryClient])

  // Safe error message extraction — no raw stack traces or internal details.
  // Returns the backend ``detail.message`` verbatim when present (a safe
  // secondary diagnostic already supported by the wire contract), otherwise
  // null so the caller can substitute a localized fallback.
  function extractSafeErrorMessage(error: Error | null): string | null {
    if (!error) return null
    if (typeof error === 'object' && 'response' in error) {
      const response = (
        error as { response?: { data?: { detail?: { message?: string }; message?: string } } }
      ).response
      const detail = response?.data?.detail
      if (detail && typeof detail === 'object' && detail.message) {
        return detail.message
      }
      if (response?.data?.message) {
        return response.data.message
      }
    }
    return null
  }

  // Loading state — only full-page while active plan or risks list are loading
  if (planLoading || risksLoading) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">{t('breadcrumb.supplyRisks')}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{t('breadcrumb.loading')}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    )
  }

  // Active plan error
  if (planError) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">{t('breadcrumb.supplyRisks')}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{t('breadcrumb.error')}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">{t('errors.planLoadFailed')}</h2>
                <p className="text-sm text-muted-foreground mt-1">{planError.message}</p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>{t('backToRisks')}</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // No active plan
  if (!activePlan) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">{t('breadcrumb.supplyRisks')}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{t('breadcrumb.noActivePlan')}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-muted-foreground" />
              <div>
                <h2 className="text-lg font-semibold">{t('errors.noActivePlan')}</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  {t('errors.noActivePlanBody')}
                </p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>{t('backToRisks')}</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Risks fetch error
  if (risksError) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">{t('breadcrumb.supplyRisks')}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{t('breadcrumb.error')}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">{t('errors.risksLoadFailed')}</h2>
                <p className="text-sm text-muted-foreground mt-1">{risksError.message}</p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>{t('backToRisks')}</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Risk not found (stale/unknown risk)
  if (!detailLoading && risks.length > 0 && !risk) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">{t('breadcrumb.supplyRisks')}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{t('breadcrumb.notFound')}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">{t('errors.notFoundTitle')}</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  {t('errors.notFoundBody', { riskId })}
                </p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>{t('backToRisks')}</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Still loading detail (enrichment panels)
  if (detailLoading || !risk) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">{t('breadcrumb.supplyRisks')}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{t('breadcrumb.loading')}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <div className="space-y-4">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/supply-risk">{t('breadcrumb.supplyRisks')}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{risk.risk_id}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Page heading */}
      <h1 className="text-2xl font-bold text-white">{t('heading', { riskId: risk.risk_id })}</h1>

      {/* Risk Summary */}
      <RiskSummary risk={risk} />

      {/* Workflow AI Analysis Panel (WP-REC-03G + WP-UX-02) */}
      <Card data-testid="workflow-panel">
        <CardHeader>
          <CardTitle>{t('workflow.title')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Business-facing workflow state badge (WP-UX-02 §12) */}
          {workflowState !== undefined && (
            <div
              className="flex items-center gap-2"
              data-testid="workflow-status"
            >
              <WorkflowStateBadge state={workflowState} testId="workflow-state-badge" />
              {isWorkflowRunning && (
                <>
                  <Loader2 className="h-4 w-4 animate-spin text-blue-400" aria-hidden="true" />
                  <span className="text-xs text-muted-foreground">
                    {t('workflow.updatesAutomatically')}
                  </span>
                </>
              )}
              {/* Preserve raw enum for technical context only */}
              <span
                className="sr-only"
                data-testid="workflow-state"
                data-state={workflowState}
              >
                {workflowState}
              </span>
            </div>
          )}

          {/* Restoration loading indicator */}
          {restorationPending && activeRunId === undefined && (
            <div
              className="flex items-center gap-2 text-sm text-muted-foreground"
              data-testid="restoration-loading"
            >
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              {t('workflow.checkingExisting')}
            </div>
          )}

          {/* F-5: Restoration error — fail closed */}
          {restorationFailed && activeRunId === undefined && (
            <div
              className="flex items-start gap-3 rounded-md border border-red-600/30 bg-red-600/10 px-4 py-3"
              data-testid="restoration-error"
              role="alert"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" aria-hidden="true" />
              <div className="flex-1">
                <p className="text-sm font-medium text-red-300">
                  {t('workflow.checkFailedTitle')}
                </p>
                <p className="mt-1 text-xs text-red-400">
                  {t('workflow.checkFailedBody')}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    void refetchRestoration()
                  }}
                  data-testid="restoration-retry"
                  className="mt-2 border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
                >
                  <RotateCw className="h-3.5 w-3.5" />
                  {t('workflow.tryAgain')}
                </Button>
              </div>
            </div>
          )}

          {/* Progress copy for nonterminal states */}
          {workflowState !== undefined && isNonterminalState(workflowState) && (
            <p className="text-sm text-muted-foreground" data-testid="workflow-progress-copy">
              {workflowState === 'PENDING' && t('workflow.progress.pending')}
              {workflowState === 'RUNNING' && t('workflow.progress.running')}
              {workflowState === 'AWAITING_VALIDATION' && t('workflow.progress.awaitingValidation')}
            </p>
          )}

          {/* Start AI Analysis button — PRODUCTION_MANAGER only, plan-scoped copy */}
          {canStart && (
            <>
              <Button
                onClick={handleStart}
                disabled={workflowStart.isPending}
                data-testid="start-workflow-button"
              >
                {workflowStart.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('workflow.starting')}
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    {t('workflow.start')}
                  </>
                )}
              </Button>
              <p className="text-xs text-muted-foreground" data-testid="start-workflow-scope-copy">
                {t('workflow.startScope', { planCode: activePlan.code })}
              </p>
            </>
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
                  {t('workflow.startFailed')}
                </p>
                <p className="mt-1 text-xs text-red-400">
                  {extractSafeErrorMessage(workflowStart.error) ?? t('common:errors.unexpected')}
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
                  {t('workflow.retrying')}
                </>
              ) : (
                <>
                  <RotateCw className="h-4 w-4" />
                  {t('workflow.retry')}
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
                  {t('workflow.retryFailed')}
                </p>
                <p className="mt-1 text-xs text-red-400">
                  {extractSafeErrorMessage(workflowRetry.error) ?? t('common:errors.unexpected')}
                </p>
              </div>
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
                  {t('workflow.statusLoadFailed')}
                </p>
                <p className="mt-1 text-xs text-red-400">
                  {extractSafeErrorMessage(workflowPollingErrorDetail) ?? t('workflow.statusLoadFailedBody')}
                </p>
              </div>
            </div>
          )}

          {/* Failed state — business-facing failure copy */}
          {workflowState !== undefined && isFailedState(workflowState) && (
            <p className="text-sm text-red-300" data-testid="workflow-failure-copy">
              {workflowState === 'FAILED_PROVIDER' && t('workflow.failure.provider')}
              {workflowState === 'FAILED_VALIDATION' && t('workflow.failure.validation')}
              {workflowState === 'FAILED_RETRIEVAL' && t('workflow.failure.retrieval')}
              {workflowState === 'FAILED_INTERNAL' && t('workflow.failure.internal')}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Completed Moment — AI Recommendation for the current risk (WP-UX-02 §13) */}
      {workflowState === 'COMPLETED' && activeRunId && workflowRun && (
        <RecommendationForRisk
          recommendation={workflowRun.recommendation}
          riskId={risk.risk_id}
          runId={activeRunId}
          onSubmitForApproval={isProductionManager ? openApprovalDialog : undefined}
        />
      )}

      {/* Evidence Panel */}
      <EvidencePanel risk={risk} />

      {/* Component Panel */}
      {component ? (
        <ComponentPanel component={component} />
      ) : componentError ? (
        <PartialFailurePlaceholder
          label={t('panels.component')}
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
          label={t('panels.inventory')}
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
          label={t('panels.incomingSupply')}
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
            <CardTitle>{t('incomingSupply.title')}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">{t('incomingSupply.empty')}</p>
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
          label={t('panels.productionOrder')}
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
          label={t('panels.productionPlan')}
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

      {/* Guided approval confirmation (WP-UX-UA-05) */}
      {approvalAction && workflowRun && workflowRun.recommendation && (
        <ApprovalRequestConfirmation
          prefill={{
            riskId: risk.risk_id,
            componentCode: risk.component_code,
            quantity: risk.shortage,
            actionTitle: approvalAction.title,
            actionRationale: approvalAction.rationale,
            recommendationId: workflowRun.recommendation.id,
            workflowRunId: activeRunId ?? '',
            correlationId: workflowRun.correlation_id,
          }}
          requester={user?.username ?? ''}
          onCreate={async (payload) => {
            const result = await approvalCreate.mutateAsync(payload)
            await queryClient.invalidateQueries({ queryKey: ['approval-requests'] })
            return result
          }}
          onCancel={closeApprovalDialog}
        />
      )}
    </div>
  )
}
