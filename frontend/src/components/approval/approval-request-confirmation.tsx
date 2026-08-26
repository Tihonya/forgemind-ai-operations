/**
 * Guided approval confirmation dialog (WP-UX-UA-05).
 *
 * Renders a prefilled, human-readable confirmation before an approval request
 * is created. The main journey shows business values only — no blank UUID
 * input. Technical identifiers (recommendation/run/correlation) live under an
 * expandable "Технічні деталі" section.
 *
 * Duplicate protection: the submit control is disabled while a submission is
 * in flight; backend idempotency/duplicate protection is preserved untouched.
 */

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { AlertCircle, CheckCircle2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  getApprovalErrorKey,
  SUPPORTED_ACTION_TYPE,
  type ApprovalRequestCreate,
  type ApprovalRequestResponse,
} from '@/lib/approval-api'
import { shortRef } from '@/lib/references'

export interface ApprovalPrefill {
  riskId: string
  componentCode: string
  quantity: string
  actionTitle: string
  actionRationale: string
  recommendationId: string
  workflowRunId: string
  correlationId: string
}

interface ApprovalRequestConfirmationProps {
  prefill: ApprovalPrefill
  requester: string
  onCreate: (payload: ApprovalRequestCreate) => Promise<ApprovalRequestResponse>
  onCancel: () => void
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium text-steel-500">{label}</dt>
      <dd className="text-sm text-steel-200">{children}</dd>
    </div>
  )
}

export function ApprovalRequestConfirmation({
  prefill,
  requester,
  onCreate,
  onCancel,
}: ApprovalRequestConfirmationProps) {
  const { t } = useTranslation('approval')
  const [pending, setPending] = useState(false)
  const [errorKey, setErrorKey] = useState<string | null>(null)
  const [created, setCreated] = useState<ApprovalRequestResponse | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const nextRoleLabel = t('shell:roleLabels.procurementSpecialist')

  const missing = !prefill.recommendationId || !prefill.componentCode || !prefill.quantity

  // Focus the dialog panel on open; return focus is handled by the parent
  // unmounting the dialog (the trigger button regains focus).
  useEffect(() => {
    panelRef.current?.focus()
  }, [])

  // Close on Escape for keyboard users.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && !pending) onCancel()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [pending, onCancel])

  async function handleSubmit() {
    if (pending || missing || created) return
    setPending(true)
    setErrorKey(null)
    try {
      const result = await onCreate({
        recommendation_id: prefill.recommendationId,
        risk_id: prefill.riskId,
        action_type: SUPPORTED_ACTION_TYPE,
        component_code: prefill.componentCode,
        quantity: prefill.quantity,
      })
      setCreated(result)
    } catch (err) {
      setErrorKey(getApprovalErrorKey(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !pending) onCancel()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="approval-confirm-title"
        tabIndex={-1}
        className="w-full max-h-[90vh] overflow-y-auto rounded-t-xl border border-steel-700 bg-steel-900 p-5 outline-none sm:rounded-xl sm:max-w-lg"
        data-testid="approval-confirmation"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id="approval-confirm-title" className="text-lg font-semibold text-white">
            {t('confirm.title')}
          </h2>
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            aria-label={t('confirm.cancel')}
            className="flex h-11 w-11 items-center justify-center rounded-md text-steel-400 hover:bg-steel-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            data-testid="confirm-close"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {created ? (
          <div className="mt-4 space-y-4" data-testid="confirm-success">
            <div className="flex items-start gap-3 rounded-md border border-green-600/30 bg-green-600/10 px-3 py-2">
              <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-400" aria-hidden="true" />
              <div>
                <p className="text-sm font-medium text-green-300">{t('confirm.created')}</p>
                <p className="mt-1 text-xs text-green-400/80">{t('confirm.whatHappened')}</p>
                <p className="mt-0.5 text-xs text-green-400/80">{t('confirm.whoActsNext')}</p>
              </div>
            </div>
            <dl className="space-y-2">
              <Field label={t('snapshot.risk')}>{created.risk_id}</Field>
              <Field label={t('trail.stage.approval')}>
                {shortRef('APR', created.id)}
              </Field>
              <Field label={t('snapshot.component')}>
                {created.action_snapshot.component_code}
              </Field>
            </dl>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button asChild data-testid="confirm-open-request">
                <Link to={`/approval-requests/${created.id}`}>
                  {t('confirm.openRequest')}
                </Link>
              </Button>
              <Button asChild variant="outline" data-testid="confirm-open-center">
                <Link to="/approval-center">{t('confirm.openCenter')}</Link>
              </Button>
            </div>
          </div>
        ) : (
          <>
            <p className="mt-2 text-sm text-steel-400">{t('confirm.subtitle')}</p>

            {missing ? (
              <div
                className="mt-4 flex items-start gap-3 rounded-md border border-amber-600/30 bg-amber-600/10 px-3 py-2"
                data-testid="confirm-missing"
                role="alert"
              >
                <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400" aria-hidden="true" />
                <div>
                  <p className="text-sm font-medium text-amber-300">{t('confirm.missingTitle')}</p>
                  <p className="mt-0.5 text-xs text-amber-400/80">{t('confirm.missingBody')}</p>
                </div>
              </div>
            ) : (
              <dl className="mt-4 space-y-3">
                <Field label={t('confirm.risk')}>{prefill.riskId}</Field>
                <Field label={t('confirm.component')}>{prefill.componentCode}</Field>
                <Field label={t('confirm.action')}>{prefill.actionTitle}</Field>
                <Field label={t('confirm.quantity')}>{prefill.quantity}</Field>
                <Field label={t('confirm.recommendation')}>{prefill.actionRationale}</Field>
                <Field label={t('confirm.requester')}>{requester}</Field>
                <Field label={t('confirm.nextRole')}>{nextRoleLabel}</Field>
              </dl>
            )}

            {!missing && (
              <details className="mt-4 rounded-md border border-steel-700 bg-steel-800/40 px-3 py-2" data-testid="confirm-technical">
                <summary className="cursor-pointer text-xs font-medium text-steel-400">
                  {t('confirm.technicalDetails')}
                </summary>
                <dl className="mt-2 space-y-1 text-xs text-steel-500">
                  <div className="flex justify-between gap-3">
                    <dt>recommendation_id</dt>
                    <dd className="break-all text-right" data-testid="technical-recommendation-id">{prefill.recommendationId}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>workflow_run_id</dt>
                    <dd className="break-all text-right" data-testid="technical-workflow-run-id">{prefill.workflowRunId}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>correlation_id</dt>
                    <dd className="break-all text-right" data-testid="technical-correlation-id">{prefill.correlationId}</dd>
                  </div>
                </dl>
              </details>
            )}

            {errorKey && (
              <div
                role="alert"
                className="mt-4 rounded-md border border-red-600/30 bg-red-600/10 px-3 py-2 text-sm text-red-300"
                data-testid="confirm-error"
              >
                {t(errorKey)}
              </div>
            )}

            <div className="mt-5 flex gap-2">
              <Button
                onClick={handleSubmit}
                disabled={pending || missing}
                data-testid="confirm-submit"
              >
                {pending ? t('confirm.submitting') : t('confirm.submit')}
              </Button>
              <Button
                variant="ghost"
                onClick={onCancel}
                disabled={pending}
                data-testid="confirm-cancel"
              >
                {t('confirm.cancel')}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
