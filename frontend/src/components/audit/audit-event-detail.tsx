/**
 * Read-only audit-event detail panel (WP-REC-04E).
 *
 * Presents the safe fields of a single audit event: timestamp, event/entity
 * types, entity ID, actor, correlation ID, workflow-run/risk linkage, and the
 * structured before/after/metadata summaries via the defensive SafeMetadata
 * renderer. It exposes NO edit, delete, retry, approve, reject, or
 * procurement-execute control — the panel is strictly read-only.
 *
 * Localized per WP-UX-UA-03: field labels, headings and actions are localized;
 * the event/entity type badges, entity IDs, actor, correlation ID and raw
 * metadata remain machine content.
 */

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Copy, X } from 'lucide-react'

import {
  formatEntityType,
  getAuditErrorKey,
} from '@/lib/audit-api'
import { useAuditEvent } from '@/hooks/use-audit-events'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import { AuditEventTypeBadge } from './audit-event-type-badge'
import { SafeMetadata } from './audit-metadata-view'
import { Button } from '@/components/ui/button'

interface AuditEventDetailProps {
  eventId: string | null;
  onClose: () => void;
}

export function AuditEventDetail({ eventId, onClose }: AuditEventDetailProps) {
  const { t } = useTranslation('audit')
  const { formatDateTime } = useLocalizedFormatters()
  const { event, isLoading, isError, error, refetch } = useAuditEvent(eventId)

  const panelRef = useRef<HTMLDivElement>(null)
  const previouslyFocusedRef = useRef<Element | null>(null)
  const onCloseRef = useRef(onClose)

  // Keep the latest onClose available to the stable keydown listener without
  // re-running the focus-management effect on every parent render.
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (eventId === null) return

    // Remember the element that opened the dialog so focus can be restored.
    previouslyFocusedRef.current = document.activeElement

    // Apply initial focus inside the dialog (the container itself, focusable
    // via tabIndex=-1 so it announces the accessible name).
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
  }, [eventId])

  if (eventId === null) {
    return null
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/50"
      data-testid="audit-detail-backdrop"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('detail.ariaLabel')}
        ref={panelRef}
        tabIndex={-1}
        className="h-full w-full max-w-xl overflow-y-auto border-l border-steel-700 bg-steel-900 p-6"
        data-testid="audit-detail-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">{t('detail.title')}</h2>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label={t('detail.closeAria')}
            data-testid="audit-detail-close"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        {isLoading ? (
          <div
            className="mt-6 space-y-3"
            data-testid="audit-detail-loading"
            role="status"
          >
            <div className="h-5 w-2/3 animate-pulse rounded bg-steel-700" />
            <div className="h-5 w-1/2 animate-pulse rounded bg-steel-700" />
            <div className="h-24 animate-pulse rounded bg-steel-700" />
          </div>
        ) : isError || !event ? (
          <div
            className="mt-6 rounded-md border border-red-600/30 bg-red-600/10 px-4 py-3"
            role="alert"
            data-testid="audit-detail-error"
          >
            <p className="text-sm font-medium text-red-300">
              {t('detail.loadFailed')}
            </p>
            <p className="mt-1 text-xs text-red-400">
              {error ? t(getAuditErrorKey(error)) : t('detail.loadFailedFallback')}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="mt-3 border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
              data-testid="audit-detail-reload"
            >
              {t('detail.reload')}
            </Button>
          </div>
        ) : (
          <dl className="mt-6 space-y-4 text-sm" data-testid="audit-detail-content">
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-steel-500">
                {t('detail.event')}
              </dt>
              <dd className="mt-1">
                <AuditEventTypeBadge eventType={event.event_type} />
              </dd>
            </div>

            <Field label={t('detail.occurredAt')}>
              <span data-testid="detail-created-at">
                {formatDateTime(event.created_at)}
              </span>
            </Field>

            <Field label={t('detail.actor')}>
              <span data-testid="detail-actor">
                {event.actor_username ?? t('system')}
              </span>
            </Field>

            <Field label={t('detail.entityType')}>
              <span data-testid="detail-entity-type">
                {formatEntityType(event.entity_type)}
              </span>
            </Field>

            <Field label={t('detail.entityId')}>
              <span className="break-all" data-testid="detail-entity-id">
                {event.entity_id}
              </span>
              <CopyButton
                value={event.entity_id}
                label={t('detail.entityId')}
                slug="entity-ID"
              />
            </Field>

            <Field label={t('detail.correlationId')}>
              <span className="break-all" data-testid="detail-correlation-id">
                {event.correlation_id}
              </span>
              <CopyButton
                value={event.correlation_id}
                label={t('detail.correlationId')}
                slug="correlation-ID"
              />
            </Field>

            {event.workflow_run_id && (
              <Field label={t('detail.workflowRunId')}>
                <span className="break-all" data-testid="detail-workflow-run-id">
                  {event.workflow_run_id}
                </span>
              </Field>
            )}

            {event.risk_id && (
              <Field label={t('detail.risk')}>
                <span data-testid="detail-risk-id">{event.risk_id}</span>
              </Field>
            )}

            <StructuredSection
              title={t('detail.before')}
              value={event.before_summary}
              testId="detail-before-summary"
            />
            <StructuredSection
              title={t('detail.after')}
              value={event.after_summary}
              testId="detail-after-summary"
            />
            <StructuredSection
              title={t('detail.metadata')}
              value={event.event_metadata}
              testId="detail-event-metadata"
            />

            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-steel-500">
                {t('detail.eventId')}
              </dt>
              <dd className="mt-1 break-all text-xs text-steel-400">
                {event.id}
              </dd>
            </div>
          </dl>
        )}
      </div>
    </div>
  )
}

interface FieldProps {
  label: string;
  children: React.ReactNode;
}

/**
 * Return the keyboard-focusable elements inside the dialog, in DOM order, so
 * the Tab trap can wrap focus between the first and last interactive control.
 */
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

function Field({ label, children }: FieldProps) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-steel-500">
        {label}
      </dt>
      <dd className="mt-1 flex items-start gap-2 text-steel-200">{children}</dd>
    </div>
  )
}

interface StructuredSectionProps {
  title: string;
  value: Record<string, unknown> | null;
  testId: string;
}

function StructuredSection({ title, value, testId }: StructuredSectionProps) {
  const { t } = useTranslation('audit')
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-steel-500">
        {title}
      </dt>
      <dd className="mt-1 rounded-md border border-steel-700 bg-steel-800/40 px-3 py-2">
        {value ? (
          <SafeMetadata value={value} testId={testId} />
        ) : (
          <span className="text-xs text-steel-500">{t('detail.none')}</span>
        )}
      </dd>
    </div>
  )
}

interface CopyButtonProps {
  value: string;
  label: string;
  slug: string;
}

function CopyButton({ value, label, slug }: CopyButtonProps) {
  const { t } = useTranslation('audit')
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    setCopied(true)
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(value).catch(() => {
        setCopied(false)
      })
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={t('detail.copyAria', { label })}
      className="inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded text-steel-400 hover:text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      data-testid={`copy-${slug}`}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-green-400" aria-hidden="true" />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
      )}
    </button>
  )
}
