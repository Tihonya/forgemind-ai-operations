/**
 * Approval-request detail route (WP-UX-UA-05).
 *
 * Read-only single-request view reached from the guided-creation success
 * state and the decision trail. Renders the full request card (safe action
 * snapshot, end-to-end decision trail, decision/task surfaces) against the
 * existing GET /approval-requests/{request_id} endpoint.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'

import { ApprovalRequestCard } from '@/components/approval/approval-request-card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/contexts/auth.context'
import { useApprovalDecision, type ApprovalDecisionKind } from '@/hooks/use-approval-decision'
import { useProcurementCreate, useProcurementTasks } from '@/hooks/use-procurement-tasks'
import { fetchApprovalRequest, getApprovalErrorKey } from '@/lib/approval-api'
import type { ProcurementTaskResponse } from '@/lib/procurement-api'

const ROLE_SPECIALIST = 'PROCUREMENT_SPECIALIST'
const ROLE_AUDITOR = 'AUDITOR'
const ROLE_ADMIN = 'AI_ADMINISTRATOR'

function hasRole(roles: string[], roleCode: string): boolean {
  return roles.some(
    (role) => typeof role === 'string' && role.trim().toUpperCase() === roleCode,
  )
}

export default function ApprovalRequestDetail() {
  const { t } = useTranslation('approval')
  const { requestId } = useParams<{ requestId: string }>()
  const { user } = useAuth()
  const roles = user?.roles ?? []
  const queryClient = useQueryClient()

  const canDecide = hasRole(roles, ROLE_SPECIALIST)
  const canViewAudit = hasRole(roles, ROLE_AUDITOR) || hasRole(roles, ROLE_ADMIN)
  const canReadTasks = hasRole(roles, ROLE_SPECIALIST) || hasRole(roles, 'PRODUCTION_MANAGER') || hasRole(roles, ROLE_ADMIN)

  const decisionMutation = useApprovalDecision()
  const createTaskMutation = useProcurementCreate()
  const { tasks, refetch: refetchTasks } = useProcurementTasks(canReadTasks)

  const {
    data: request,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['approval-request', requestId],
    queryFn: () => fetchApprovalRequest(requestId ?? ''),
    enabled: !!requestId,
    retry: 1,
  })

  async function handleDecide(
    id: string,
    kind: ApprovalDecisionKind,
    comment: string,
  ) {
    try {
      await decisionMutation.mutateAsync({ requestId: id, kind, comment })
    } finally {
      await queryClient.invalidateQueries({ queryKey: ['approval-request', id] })
      await queryClient.invalidateQueries({ queryKey: ['approval-requests'] })
    }
  }

  async function handleCreateTask(approvalRequestId: string) {
    const task = await createTaskMutation.mutateAsync(approvalRequestId)
    await queryClient.invalidateQueries({ queryKey: ['procurement-tasks'] })
    void refetchTasks()
    return task
  }

  if (isLoading) {
    return (
      <div className="space-y-3" data-testid="loading-state">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (isError || !request) {
    return (
      <div className="flex flex-col items-center gap-4 p-8" data-testid="error-state">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-lg text-destructive">{t('loadFailed')}</p>
        {error && <p className="text-sm text-steel-400">{t(getApprovalErrorKey(error))}</p>}
        <Button asChild variant="outline">
          <Link to="/approval-center">{t('confirm.openCenter')}</Link>
        </Button>
      </div>
    )
  }

  let matchedTask: ProcurementTaskResponse | null = null
  for (const task of tasks) {
    if (task.approval_request_id === request.id) {
      matchedTask = task
      break
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="mb-2">
          <Link to="/approval-center">{`← ${t('confirm.openCenter')}`}</Link>
        </Button>
        <h1 className="text-2xl font-semibold text-white">{request.risk_id}</h1>
      </div>

      <ApprovalRequestCard
        request={request}
        canDecide={canDecide && request.requested_by !== user?.id}
        onDecide={(kind, comment) => handleDecide(request.id, kind, comment)}
        procurementTask={matchedTask}
        canCreateTask={
          canDecide && request.decided_by === user?.id && request.status === 'APPROVED'
        }
        onCreateTask={() => handleCreateTask(request.id)}
        canViewAudit={canViewAudit}
      />
    </div>
  )
}
