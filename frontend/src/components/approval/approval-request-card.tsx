/**
 * Single approval-request card (WP-REC-04D, extended WP-UX-UA-05).
 *
 * Renders status, the safe action snapshot, requester/timestamps, the
 * terminal decision metadata, and (new) the end-to-end decision trail plus
 * the procurement-task creation/read surface. Decision controls are shown
 * only when the current user may decide this request.
 *
 * Localized per WP-UX-UA-03; statuses resolve through the WP-UX-UA-04
 * registry. Machine codes (risk id, component code, UUIDs) remain untranslated.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/status/StatusBadge'
import {
  getApprovalErrorKey,
  type ApprovalRequestResponse,
} from '@/lib/approval-api'
import {
  getProcurementErrorKey,
  type ProcurementTaskResponse,
} from '@/lib/procurement-api'
import type { ApprovalDecisionKind } from '@/hooks/use-approval-decision'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import { shortRef } from '@/lib/references'
import { ApprovalActionSnapshot } from './approval-action-snapshot'
import { ApprovalStatusBadge } from './approval-status-badge'
import { DecisionTrail } from './decision-trail'

const COMMENT_MAX_LENGTH = 2000

interface ApprovalRequestCardProps {
  request: ApprovalRequestResponse;
  canDecide: boolean;
  onDecide: (kind: ApprovalDecisionKind, comment: string) => Promise<void>;
  /** Matched procurement task for this request (null when none exists). */
  procurementTask?: ProcurementTaskResponse | null;
  /** Whether the current user may create a procurement task for this request. */
  canCreateTask?: boolean;
  onCreateTask?: () => Promise<ProcurementTaskResponse>;
  /** Whether the current role may open the Audit Log. */
  canViewAudit?: boolean;
}

export function ApprovalRequestCard({
  request,
  canDecide,
  onDecide,
  procurementTask = null,
  canCreateTask = false,
  onCreateTask,
  canViewAudit = false,
}: ApprovalRequestCardProps) {
  const { t } = useTranslation('approval')
  const [mode, setMode] = useState<ApprovalDecisionKind | null>(null)
  const [comment, setComment] = useState('')
  const [pending, setPending] = useState(false)
  const [errorKey, setErrorKey] = useState<string | null>(null)

  // Procurement-task creation state.
  const [taskPending, setTaskPending] = useState(false)
  const [taskErrorKey, setTaskErrorKey] = useState<string | null>(null)
  const [localTask, setLocalTask] = useState<ProcurementTaskResponse | null>(null)

  const { formatDate } = useLocalizedFormatters()

  const isPendingRequest = request.status === 'PENDING'
  const canAct = canDecide && isPendingRequest
  const activeTask = localTask ?? procurementTask

  async function submit() {
    if (!mode || !comment.trim() || pending) return
    setPending(true)
    setErrorKey(null)
    try {
      await onDecide(mode, comment.trim())
      setMode(null)
      setComment('')
    } catch (err) {
      setErrorKey(getApprovalErrorKey(err))
    } finally {
      setPending(false)
    }
  }

  function cancel() {
    setMode(null)
    setComment('')
    setErrorKey(null)
  }

  async function handleCreateTask() {
    if (!onCreateTask || taskPending) return
    setTaskPending(true)
    setTaskErrorKey(null)
    try {
      const task = await onCreateTask()
      setLocalTask(task)
    } catch (err) {
      setTaskErrorKey(getProcurementErrorKey(err))
    } finally {
      setTaskPending(false)
    }
  }

  return (
    <div
      className="rounded-xl border border-steel-700 bg-steel-900/60 p-5"
      data-testid="approval-request-card"
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-white" data-testid="request-risk-id">
          {request.risk_id}
        </h3>
        <ApprovalStatusBadge status={request.status} />
      </div>

      <div className="mt-3">
        <ApprovalActionSnapshot request={request} />
      </div>

      {/* End-to-end decision trail (WP-UX-UA-05) */}
      <div className="mt-4">
        <DecisionTrail
          riskId={request.risk_id}
          workflowRunId={request.workflow_run_id}
          recommendationId={request.recommendation_id}
          correlationId={request.correlation_id}
          approvalStatus={request.status}
          approvalRequestId={request.id}
          procurementTask={activeTask}
          canViewAudit={canViewAudit}
        />
      </div>

      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-steel-400">
        <span>
          <span className="font-medium text-steel-300">{t('card.requester')}</span>{' '}
          <span data-testid="requester">{request.requested_by_username}</span>
        </span>
        <span>
          <span className="font-medium text-steel-300">{t('card.requested')}</span>{' '}
          <span data-testid="requested-at">{formatDate(request.requested_at)}</span>
        </span>
      </div>

      {!isPendingRequest && (
        <div className="mt-3 rounded-md border border-steel-700 bg-steel-800/40 px-3 py-2 text-xs text-steel-300">
          {/* Previous → new status transition (WP-UX-UA-05) */}
          <div
            className="flex flex-wrap items-center gap-1.5"
            data-testid="status-transition"
          >
            <StatusBadge domain="approval" code="PENDING" testId="transition-from" />
            <span className="text-steel-500" aria-hidden="true">→</span>
            <StatusBadge domain="approval" code={request.status} testId="transition-to" />
          </div>
          <span className="mt-2 block">
            <span className="font-medium">{t('card.decidedBy')}</span>{' '}
            <span data-testid="decided-by">
              {request.decided_by_username ?? '—'}
            </span>
          </span>
          {request.decided_at && (
            <span className="ml-2 text-steel-400">
              {t('card.on', { date: formatDate(request.decided_at) })}
            </span>
          )}
          {request.decision_comment && (
            <p className="mt-1 text-steel-400" data-testid="decision-comment">
              {request.decision_comment}
            </p>
          )}
        </div>
      )}

      {canAct && !mode && (
        <div className="mt-4 flex gap-2">
          <Button
            size="sm"
            onClick={() => setMode('approve')}
            data-testid="approve-button"
          >
            {t('card.approve')}
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => setMode('reject')}
            data-testid="reject-button"
          >
            {t('card.reject')}
          </Button>
        </div>
      )}

      {canAct && mode && (
        <div className="mt-4 space-y-3" data-testid="decision-form">
          <div>
            <label
              htmlFor={`decision-comment-${request.id}`}
              className="block text-sm font-medium text-steel-300"
            >
              {mode === 'approve' ? t('card.approvalComment') : t('card.rejectionReason')}
            </label>
            <textarea
              id={`decision-comment-${request.id}`}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              maxLength={COMMENT_MAX_LENGTH}
              rows={3}
              placeholder={
                mode === 'approve'
                  ? t('card.reasonForApproval')
                  : t('card.reasonForRejection')
              }
              className="mt-1 w-full bg-steel-900 border border-steel-600 rounded-md px-3 py-2 text-sm text-white placeholder-steel-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
              data-testid="decision-comment"
              disabled={pending}
            />
            {comment.length >= COMMENT_MAX_LENGTH && (
              <p className="mt-1 text-xs text-steel-500">
                {t('card.maxCharacters', { count: COMMENT_MAX_LENGTH })}
              </p>
            )}
          </div>

          {errorKey && (
            <div
              role="alert"
              className="rounded-md border border-red-600/30 bg-red-600/10 px-3 py-2 text-sm text-red-300"
              data-testid="decision-error"
            >
              {t(errorKey)}
            </div>
          )}

          <div className="flex gap-2">
            <Button
              size="sm"
              variant={mode === 'approve' ? 'default' : 'destructive'}
              onClick={submit}
              disabled={pending || !comment.trim()}
              data-testid="decision-submit"
            >
              {pending
                ? t('card.submitting')
                : mode === 'approve'
                  ? t('card.confirmApproval')
                  : t('card.confirmRejection')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={cancel}
              disabled={pending}
              data-testid="decision-cancel"
            >
              {t('card.cancel')}
            </Button>
          </div>
        </div>
      )}

      {/* Procurement task (WP-UX-UA-05): read + create */ }
      {activeTask && (
        <div
          className="mt-4 flex items-center gap-2 rounded-md border border-steel-700 bg-steel-800/40 px-3 py-2 text-xs text-steel-300"
          data-testid="procurement-task-present"
        >
          <span className="font-medium">{t('trail.stage.task')}:</span>
          <span data-testid="task-reference">{shortRef('TASK', activeTask.id)}</span>
          <StatusBadge
            domain="procurementTask"
            code={activeTask.task_state}
            testId="task-state-badge"
          />
        </div>
      )}

      {canCreateTask && request.status === 'APPROVED' && !activeTask && (
        <div className="mt-4 space-y-2" data-testid="procurement-task-create">
          {taskErrorKey && (
            <div
              role="alert"
              className="rounded-md border border-red-600/30 bg-red-600/10 px-3 py-2 text-sm text-red-300"
              data-testid="task-error"
            >
              {t(taskErrorKey)}
            </div>
          )}
          <Button
            size="sm"
            onClick={handleCreateTask}
            disabled={taskPending}
            data-testid="create-task-button"
          >
            {taskPending ? t('task.creating') : t('task.create')}
          </Button>
        </div>
      )}
    </div>
  )
}
