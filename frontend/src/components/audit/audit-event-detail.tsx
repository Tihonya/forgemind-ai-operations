/**
 * Read-only audit-event detail panel (WP-REC-04E).
 *
 * Presents the safe fields of a single audit event: timestamp, event/entity
 * types, entity ID, actor, correlation ID, workflow-run/risk linkage, and the
 * structured before/after/metadata summaries via the defensive SafeMetadata
 * renderer. It exposes NO edit, delete, retry, approve, reject, or
 * procurement-execute control — the panel is strictly read-only.
 *
 * The backend ``[REDACTED]`` sentinel is preserved verbatim (rendered by
 * SafeMetadata), and no binding hash, prompt, token, or raw provider payload
 * is ever rendered because the audit wire schema carries none.
 */

import { useEffect, useState } from 'react'
import { Check, Copy, X } from 'lucide-react'

import {
  formatEntityType,
  formatTimestamp,
  getAuditErrorMessage,
} from '@/lib/audit-api'
import { useAuditEvent } from '@/hooks/use-audit-events'
import { AuditEventTypeBadge } from './audit-event-type-badge'
import { SafeMetadata } from './audit-metadata-view'
import { Button } from '@/components/ui/button'

interface AuditEventDetailProps {
  eventId: string | null
  onClose: () => void
}

export function AuditEventDetail({ eventId, onClose }: AuditEventDetailProps) {
  const { event, isLoading, isError, error, refetch } = useAuditEvent(eventId)

  useEffect(() => {
    if (!eventId) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [eventId, onClose])

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
        aria-label="Audit event detail"
        className="h-full w-full max-w-xl overflow-y-auto border-l border-steel-700 bg-steel-900 p-6"
        data-testid="audit-detail-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Event detail</h2>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Close event detail"
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
              Unable to load event details.
            </p>
            <p className="mt-1 text-xs text-red-400">
              {error ? getAuditErrorMessage(error) : 'The event could not be loaded.'}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="mt-3 border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
              data-testid="audit-detail-reload"
            >
              Reload details
            </Button>
          </div>
        ) : (
          <dl className="mt-6 space-y-4 text-sm" data-testid="audit-detail-content">
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-steel-500">
                Event
              </dt>
              <dd className="mt-1">
                <AuditEventTypeBadge eventType={event.event_type} />
              </dd>
            </div>

            <Field label="Occurred at">
              <span data-testid="detail-created-at">
                {formatTimestamp(event.created_at)}
              </span>
            </Field>

            <Field label="Actor">
              <span data-testid="detail-actor">
                {event.actor_username ?? 'System'}
              </span>
            </Field>

            <Field label="Entity type">
              <span data-testid="detail-entity-type">
                {formatEntityType(event.entity_type)}
              </span>
            </Field>

            <Field label="Entity ID">
              <span className="break-all" data-testid="detail-entity-id">
                {event.entity_id}
              </span>
              <CopyButton value={event.entity_id} label="entity ID" />
            </Field>

            <Field label="Correlation ID">
              <span className="break-all" data-testid="detail-correlation-id">
                {event.correlation_id}
              </span>
              <CopyButton value={event.correlation_id} label="correlation ID" />
            </Field>

            {event.workflow_run_id && (
              <Field label="Workflow run ID">
                <span className="break-all" data-testid="detail-workflow-run-id">
                  {event.workflow_run_id}
                </span>
              </Field>
            )}

            {event.risk_id && (
              <Field label="Risk">
                <span data-testid="detail-risk-id">{event.risk_id}</span>
              </Field>
            )}

            <StructuredSection
              title="Before"
              value={event.before_summary}
              testId="detail-before-summary"
            />
            <StructuredSection
              title="After"
              value={event.after_summary}
              testId="detail-after-summary"
            />
            <StructuredSection
              title="Metadata"
              value={event.event_metadata}
              testId="detail-event-metadata"
            />

            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-steel-500">
                Event ID
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
  label: string
  children: React.ReactNode
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
  title: string
  value: Record<string, unknown> | null
  testId: string
}

function StructuredSection({ title, value, testId }: StructuredSectionProps) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-steel-500">
        {title}
      </dt>
      <dd className="mt-1 rounded-md border border-steel-700 bg-steel-800/40 px-3 py-2">
        {value ? (
          <SafeMetadata value={value} testId={testId} />
        ) : (
          <span className="text-xs text-steel-500">None</span>
        )}
      </dd>
    </div>
  )
}

interface CopyButtonProps {
  value: string
  label: string
}

function CopyButton({ value, label }: CopyButtonProps) {
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
      aria-label={`Copy ${label}`}
      className="inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded text-steel-400 hover:text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      data-testid={`copy-${label.replace(/\s+/g, '-')}`}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-green-400" aria-hidden="true" />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
      )}
    </button>
  )
}
