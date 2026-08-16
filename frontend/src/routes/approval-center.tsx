/**
 * Approval Center route (WP-REC-04D).
 *
 * Orchestrates the caller-scoped approval-request list, the
 * PRODUCTION_MANAGER create form, and the PROCUREMENT_SPECIALIST
 * approve/reject controls. Role visibility is a usability mirror of the
 * backend authorization boundary — the backend remains authoritative.
 *
 * Procurement-task execution UI is intentionally absent: it is owned by
 * WP-REC-04C backend / WP-REC-04-VFY acceptance, not by this package.
 */

import { useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2 } from 'lucide-react'

import { ApprovalRequestCard } from '@/components/approval/approval-request-card'
import { CreateApprovalRequestForm } from '@/components/approval/create-approval-request-form'
import { DataEmptyState } from '@/components/common/DataEmptyState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/contexts/auth.context'
import { useApprovalCreate } from '@/hooks/use-approval-create'
import {
  useApprovalDecision,
  type ApprovalDecisionKind,
} from '@/hooks/use-approval-decision'
import { useApprovalRequests } from '@/hooks/use-approval-requests'
import type { ApprovalRequestCreate } from '@/lib/approval-api'

const ROLE_MANAGER = 'PRODUCTION_MANAGER'
const ROLE_SPECIALIST = 'PROCUREMENT_SPECIALIST'

/**
 * Case-insensitive role membership check. Backend role codes are UPPERCASE;
 * this tolerates lowercase/whitespace variance defensively.
 */
function hasRole(roles: string[], roleCode: string): boolean {
  return roles.some(
    (role) => typeof role === 'string' && role.trim().toUpperCase() === roleCode,
  )
}

export default function ApprovalCenter() {
  const { user } = useAuth()
  const roles = user?.roles ?? []

  const { requests, total, isLoading, isError, refetch } = useApprovalRequests()
  const createMutation = useApprovalCreate()
  const decisionMutation = useApprovalDecision()
  const queryClient = useQueryClient()

  const canCreate = hasRole(roles, ROLE_MANAGER)
  const canDecide = hasRole(roles, ROLE_SPECIALIST)

  async function handleCreate(payload: ApprovalRequestCreate) {
    try {
      await createMutation.mutateAsync(payload)
    } finally {
      await queryClient.invalidateQueries({ queryKey: ['approval-requests'] })
    }
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Approval Center</h1>
        <p className="mt-1 text-sm text-steel-400">
          Review and decide human-approval requests for controlled procurement
          actions.
        </p>
      </div>

      {canCreate && <CreateApprovalRequestForm onCreate={handleCreate} />}

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
          <p className="text-lg text-destructive">
            Failed to load approval requests.
          </p>
          <Button onClick={() => refetch()} data-testid="reload-button">
            Reload requests
          </Button>
        </div>
      ) : requests.length === 0 ? (
        <DataEmptyState
          primaryText="No approval requests"
          secondaryText="Approval requests you create or can decide will appear here."
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
            {total} approval request{total === 1 ? '' : 's'}
          </p>
          {requests.map((request) => (
            <ApprovalRequestCard
              key={request.id}
              request={request}
              canDecide={canDecide && request.requested_by !== user?.id}
              onDecide={(kind, comment) => handleDecide(request.id, kind, comment)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
