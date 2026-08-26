/**
 * Decision trail ("Ланцюжок рішення") — WP-UX-UA-05.
 *
 * A compact, reusable linear component that connects the business records of
 * one end-to-end decision:
 *
 *   Ризик → Аналіз → Рекомендація → Погодження → Завдання → Аудит
 *
 * This is a focused linear trail, NOT the future full interactive Trace Map.
 * Every relationship it renders is backed by an existing persisted link:
 *
 *   - risk_id            → /supply-risk/:riskId
 *   - workflow_run_id    → /workflow-runs/:workflowRunId
 *   - recommendation_id  → shown inside the workflow-run detail (no separate route)
 *   - approval request   → the object this trail is rendered against
 *   - approved request   → procurement task (matched by approval_request_id)
 *   - correlation_id     → filtered Audit Log
 *
 * Technical UUIDs are shown only as short presentation-only references
 * (REC-… / APR-… / TASK-…); the full values remain available elsewhere.
 * No relationship is fabricated: a stage with no backing record renders an
 * honest "not created / unavailable" state.
 */

import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'

import StatusBadge from '@/components/status/StatusBadge'
import type { ApprovalStatus } from '@/lib/approval-api'
import type { ProcurementTaskResponse } from '@/lib/procurement-api'
import { shortRef } from '@/lib/references'

export interface DecisionTrailProps {
  riskId: string
  workflowRunId: string
  recommendationId: string
  correlationId: string
  approvalStatus?: ApprovalStatus
  approvalRequestId?: string
  /** Matched procurement task for this approval request, or null when none. */
  procurementTask?: ProcurementTaskResponse | null
  /** Whether the current role may open the Audit Log. */
  canViewAudit?: boolean
}

interface StageDef {
  key: string
  labelKey: string
  reference: string
  status?: { domain: 'approval' | 'procurementTask'; code: string }
  href?: string
  current?: boolean
  pending?: boolean
  unavailable?: boolean
}

export function DecisionTrail({
  riskId,
  workflowRunId,
  recommendationId,
  correlationId,
  approvalStatus,
  approvalRequestId,
  procurementTask,
  canViewAudit = false,
}: DecisionTrailProps) {
  const { t } = useTranslation('approval')

  const stages: StageDef[] = [
    {
      key: 'risk',
      labelKey: 'trail.stage.risk',
      reference: riskId,
      href: `/supply-risk/${riskId}`,
    },
    {
      key: 'analysis',
      labelKey: 'trail.stage.analysis',
      reference: shortRef('RUN', workflowRunId),
      href: `/workflow-runs/${workflowRunId}`,
    },
    {
      key: 'recommendation',
      labelKey: 'trail.stage.recommendation',
      reference: shortRef('REC', recommendationId),
      href: `/workflow-runs/${workflowRunId}`,
    },
    {
      key: 'approval',
      labelKey: 'trail.stage.approval',
      reference: shortRef('APR', approvalRequestId),
      status: approvalStatus
        ? { domain: 'approval', code: approvalStatus }
        : undefined,
      current: true,
      pending: approvalStatus === 'PENDING',
    },
    {
      key: 'task',
      labelKey: 'trail.stage.task',
      reference: procurementTask ? shortRef('TASK', procurementTask.id) : t('trail.notCreated'),
      status: procurementTask
        ? { domain: 'procurementTask', code: procurementTask.task_state }
        : undefined,
      unavailable: !procurementTask,
      pending: approvalStatus === 'APPROVED' && !procurementTask,
    },
    {
      key: 'audit',
      labelKey: 'trail.stage.audit',
      reference: shortRef('', correlationId),
      href: canViewAudit ? `/audit-log?correlation_id=${correlationId}` : undefined,
      unavailable: !canViewAudit,
    },
  ]

  const nextActorLabel = t('shell:roleLabels.procurementSpecialist')

  return (
    <div className="rounded-xl border border-steel-700 bg-steel-900/40 p-4" data-testid="decision-trail">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-steel-400">
        {t('trail.title')}
      </h3>
      <ol className="space-y-2">
        {stages.map((stage) => {
          const label = t(stage.labelKey)
          const content = (
            <div className="flex min-h-[44px] flex-wrap items-center gap-x-3 gap-y-1 py-1">
              <span
                className={`h-2 w-2 flex-shrink-0 rounded-full ${
                  stage.current ? 'bg-primary' : 'bg-steel-600'
                }`}
                aria-hidden="true"
              />
              <span className="text-sm font-medium text-steel-200">
                {label}
              </span>
              <span className="text-sm text-steel-400" data-testid={`trail-ref-${stage.key}`}>
                {stage.reference}
              </span>
              {stage.status && (
                <StatusBadge
                  domain={stage.status.domain}
                  code={stage.status.code}
                  testId={`trail-status-${stage.key}`}
                />
              )}
              {stage.current && (
                <span
                  className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-xs text-primary-300"
                  data-testid={`trail-current-${stage.key}`}
                >
                  {t('trail.current')}
                </span>
              )}
              {stage.unavailable && (
                <span
                  className="inline-flex items-center gap-1 text-xs text-steel-500"
                  data-testid={`trail-unavailable-${stage.key}`}
                >
                  <AlertCircle className="h-3 w-3" aria-hidden="true" />
                  {t('trail.unavailable')}
                </span>
              )}
              {stage.pending && (
                <span
                  className="text-xs text-amber-300"
                  data-testid={`trail-next-${stage.key}`}
                >
                  {t('trail.nextAction', { role: nextActorLabel })}
                </span>
              )}
            </div>
          )

          if (!stage.href) {
            return <li key={stage.key}>{content}</li>
          }

          return (
            <li key={stage.key}>
              <Link
                to={stage.href}
                className="block rounded-md transition-colors hover:bg-steel-800/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                data-testid={`trail-link-${stage.key}`}
              >
                {content}
              </Link>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
