/**
 * Approval Center route (WP-REC-04D, remediated WP-UX-UA-05).
 *
 * Orchestrates the caller-scoped approval-request list and the
 * PROCUREMENT_SPECIALIST approve/reject controls. The manual UUID creation
 * form has been removed; the normal creation path now begins from a
 * completed AI recommendation (see ApprovalCreateGuidance). Role visibility
 * is a usability mirror of the backend authorization boundary — the backend
 * remains authoritative.
 */

import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AlertCircle, CheckCircle2 } from 'lucide-react'

import { ApprovalRequestCard } from '@/components/approval/approval-request-card'
import { ApprovalCreateGuidance } from '@/components/approval/approval-create-guidance'
import { DataEmptyState } from '@/components/common/DataEmptyState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/contexts/auth.context'
import { useApprovalDecision, type ApprovalDecisionKind } from '@/hooks/use-approval-decision'
import { useApprovalRequests } from '@/hooks/use-approval-requests'
import { useProcurementCreate, useProcurementTasks } from '@/hooks/use-procurement-tasks'
import type { ProcurementTaskResponse } from '@/lib/procurement-api'

const ROLE_MANAGER = 'PRODUCTION_MANAGER'
const ROLE_SPECIALIST = 'PROCUREMENT_SPECIALIST'
const ROLE_AUDITOR = 'AUDITOR'
const ROLE_ADMIN = 'AI_ADMINISTRATOR'

/** Roles with procurement-task read authority (backend _READ_ROLES). */
const PROCUREMENT_READ_ROLES = new Set([
  ROLE_MANAGER,
  ROLE_SPECIALIST,
  ROLE_ADMIN,
])

/**
 * Case-insensitive role membership check.
 */
function hasRole(roles: string[], roleCode: string): boolean {
  return roles.some(
    (role) => typeof role === 'string' && role.trim().toUpperCase() === roleCode,
  )
}

export default function ApprovalCenter() {
  const { t } = useTranslation('approval')
  const { user } = useAuth()
  const roles = user?.roles ?? []

  const { requests, total, isLoading, isError, refetch } = useApprovalRequests()
  const decisionMutation = useApprovalDecision()
  const queryClient = useQueryClient()

  const canCreate = hasRole(roles, ROLE_MANAGER)
  const canDecide = hasRole(roles, ROLE_SPECIALIST)
  const canViewAudit = hasRole(roles, ROLE_AUDITOR) || hasRole(roles, ROLE_ADMIN)
  const canReadTasks = roles.some((r) => PROCUREMENT_READ_ROLES.has(r.trim().toUpperCase()))

  const { tasks, refetch: refetchTasks } = useProcurementTasks(canReadTasks)
  const createTaskMutation = useProcurementCreate()

  const taskByApproval = new Map<string, ProcurementTaskResponse>()
  for (const task of tasks) {
    taskByApproval.set(task.approval_request_id, task)
  }

  async function handleDecide(
    requestId: string,
    kind: ApprovalDecisionKind,
    comment: string,
  ) {
    try {
      await decisionMutation.mutateAsync({ requestId, kind, comment })
    } finally {
      await queryClient.invalidateQueries({ queryKey: ['approval-requests'] })
    }
  }

  async function handleCreateTask(approvalRequestId: string) {
    const task = await createTaskMutation.mutateAsync(approvalRequestId)
    await queryClient.invalidateQueries({ queryKey: ['procurement-tasks'] })
    void refetchTasks()
    return task
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">{t('title')}</h1>
        <p className="mt-1 text-sm text-steel-400">{t('subtitle')}</p>
      </div>

      {canCreate && <ApprovalCreateGuidance />}

      {isLoading && requests.length === 0 ? (
        <div className="space-y-3" data-testid="loading-state">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : isError ? (
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
      ) : requests.length === 0 ? (
        <DataEmptyState
          primaryText={t('emptyTitle')}
          secondaryText={t('emptyDescription')}
          icon={
            <CheckCircle2
              className="mb-3 h-10 w-10 text-steel-500"
              aria-hidden="true"
            />
          }
        />
      ) : (
        <div className="space-y-3" data-testid="approval-list">
          <p className="text-xs text-steel-500">
            {t('requestCount', { count: total })}
          </p>
          {requests.map((request) => (
            <ApprovalRequestCard
              key={request.id}
              request={request}
              canDecide={canDecide && request.requested_by !== user?.id}
              onDecide={(kind, comment) => handleDecide(request.id, kind, comment)}
              procurementTask={taskByApproval.get(request.id) ?? null}
              canCreateTask={
                canDecide && request.decided_by === user?.id && request.status === 'APPROVED'
              }
              onCreateTask={() => handleCreateTask(request.id)}
              canViewAudit={canViewAudit}
            />
          ))}
        </div>
      )}
    </div>
  )
}
