/**
 * Read-only audit trace dialog (AT-012 complete-trace remediation).
 *
 * Presents the normalized nine-item trace for a single correlation lineage:
 * the header summary (correlation/run/initiator/final state), a completeness
 * indicator, and the canonical items in stable 1-9 order. Three truthful
 * states are rendered: complete (all nine categories), legacy-incomplete
 * (``is_legacy=true`` — pre-remediation capture), and current-incomplete
 * (neutral wording, never described as pre-remediation). Missing categories
 * are listed for every incomplete trace, using the backend-supplied set in
 * canonical order; no placeholder item is fabricated.
 *
 * Strictly read-only: no create/edit/delete, approve/reject, retry, or
 * procurement-execute control. Structured summaries render through the shared
 * ``SafeMetadata`` renderer, which already suppresses ``binding_hash`` at
 * every nesting depth, so neither the key nor its value reaches the DOM.
 */

import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

import {
  formatShortId,
  formatTimestamp,
  formatTraceCategory,
  getAuditErrorMessage,
} from '@/lib/audit-api'
import { useAuditTrace } from '@/hooks/use-audit-events'
import { TraceCategoryBadge } from './trace-category-badge'
import { SafeMetadata } from './audit-metadata-view'
import { Button } from '@/components/ui/button'

interface AuditTraceDialogProps {
  correlationId: string | null
  onClose: () => void
}

export function AuditTraceDialog({
  correlationId,
  onClose,
}: AuditTraceDialogProps) {
  const { trace, isLoading, isError, error, refetch } =
    useAuditTrace(correlationId)

  const panelRef = useRef<HTMLDivElement>(null)
  const previouslyFocusedRef = useRef<Element | null>(null)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (correlationId === null) return

    previouslyFocusedRef.current = document.activeElement
    panelRef.current?.focus()

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCloseRef.current()
        return
      }
      if (e.key !== 'Tab') return

      const container = panelRef.current
      if (!container) return
      const focusable = getFocusableElements(container)
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement

      if (e.shiftKey) {
        if (active === first || !container.contains(active)) {
          e.preventDefault()
          last.focus()
        }
      } else if (active === last || !container.contains(active)) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      const prev = previouslyFocusedRef.current
      if (prev instanceof HTMLElement) {
        prev.focus()
      }
    }
  }, [correlationId])

  if (correlationId === null) {
    return null
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/50"
      data-testid="audit-trace-backdrop"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Audit trace"
        ref={panelRef}
        tabIndex={-1}
        className="h-full w-full max-w-2xl overflow-y-auto border-l border-steel-700 bg-steel-900 p-6"
        data-testid="audit-trace-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Audit trace</h2>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Close audit trace"
            data-testid="audit-trace-close"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        {isLoading ? (
          <div
            className="mt-6 space-y-3"
            data-testid="audit-trace-loading"
            role="status"
          >
            <div className="h-5 w-2/3 animate-pulse rounded bg-steel-700" />
            <div className="h-5 w-1/2 animate-pulse rounded bg-steel-700" />
            <div className="h-24 animate-pulse rounded bg-steel-700" />
          </div>
        ) : isError || !trace ? (
          <div
            className="mt-6 rounded-md border border-red-600/30 bg-red-600/10 px-4 py-3"
            role="alert"
            data-testid="audit-trace-error"
          >
            <p className="text-sm font-medium text-red-300">
              Unable to load the audit trace.
            </p>
            <p className="mt-1 text-xs text-red-400">
              {error ? getAuditErrorMessage(error) : 'The trace could not be loaded.'}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="mt-3 border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
              data-testid="audit-trace-reload"
            >
              Reload trace
            </Button>
          </div>
        ) : (
          <div className="mt-6 space-y-5" data-testid="audit-trace-content">
            <dl className="space-y-2 text-sm">
              <SummaryField
                label="Correlation ID"
                value={trace.correlation_id}
                testId="trace-correlation-id"
              />
              <SummaryField
                label="Workflow run ID"
                value={trace.workflow_run_id}
                testId="trace-workflow-run-id"
              />
              <div className="flex items-center gap-2">
                <dt className="text-xs font-medium uppercase tracking-wide text-steel-500">
                  Final state
                </dt>
                <dd className="text-steel-200" data-testid="trace-final-state">
                  {trace.final_state}
                </dd>
              </div>
            </dl>

            {trace.complete ? (
              <div
                className="rounded-md border border-green-600/30 bg-green-600/10 px-4 py-2 text-sm text-green-300"
                data-testid="trace-complete-label"
              >
                Complete trace — all nine categories captured.
              </div>
            ) : trace.is_legacy ? (
              <div
                className="rounded-md border border-amber-600/30 bg-amber-600/10 px-4 py-2 text-sm text-amber-300"
                data-testid="trace-incomplete-label"
              >
                Legacy incomplete trace — created before complete trace capture
                was introduced.
              </div>
            ) : (
              <div
                className="rounded-md border border-amber-600/30 bg-amber-600/10 px-4 py-2 text-sm text-amber-300"
                data-testid="trace-incomplete-label"
              >
                Incomplete trace — {trace.items.length} of 9 categories captured.
              </div>
            )}

            {!trace.complete && trace.missing_categories.length > 0 && (
              <div
                className="rounded-md border border-steel-700 bg-steel-800/40 px-4 py-3"
                data-testid="trace-missing-categories"
              >
                <h3 className="text-xs font-semibold uppercase tracking-wide text-steel-400">
                  Missing categories
                </h3>
                <ul className="mt-2 space-y-1 text-sm text-steel-300">
                  {trace.missing_categories.map((category) => (
                    <li
                      key={category}
                      data-testid="trace-missing-category"
                      data-category={category}
                    >
                      {formatTraceCategory(category)}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <ol className="space-y-3" data-testid="trace-item-list">
              {trace.items.map((item) => (
                <li
                  key={item.source_id}
                  className="rounded-md border border-steel-700 bg-steel-800/40 p-3"
                  data-testid="trace-item"
                  data-category={item.category}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-steel-500">
                        {item.category_order}
                      </span>
                      <TraceCategoryBadge category={item.category} />
                    </div>
                    <span className="text-xs text-steel-500">
                      {formatTimestamp(item.occurred_at)}
                    </span>
                  </div>

                  <dl className="mt-2 space-y-1 text-xs text-steel-400">
                    {item.actor && (
                      <div>
                        <dt className="sr-only">Actor</dt>
                        <dd data-testid="trace-item-actor">
                          Actor: {item.actor}
                        </dd>
                      </div>
                    )}
                    {item.risk_id && (
                      <div>
                        <dt className="sr-only">Risk</dt>
                        <dd>Risk: {item.risk_id}</dd>
                      </div>
                    )}
                  </dl>

                  {item.summary ? (
                    <div className="mt-2 rounded-md border border-steel-700 bg-steel-900/50 px-3 py-2">
                      <SafeMetadata
                        value={item.summary}
                        testId={`trace-summary-${item.category}`}
                      />
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  )
}

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  const selector = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(',')
  return Array.from(container.querySelectorAll<HTMLElement>(selector))
}

interface SummaryFieldProps {
  label: string
  value: string
  testId: string
}

function SummaryField({ label, value, testId }: SummaryFieldProps) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-steel-500">
        {label}
      </dt>
      <dd
        className="mt-1 break-all text-steel-200"
        title={value}
        data-testid={testId}
      >
        {formatShortId(value)}
      </dd>
    </div>
  )
}
