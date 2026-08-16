/**
 * Audit Log route (WP-REC-04E).
 *
 * Strictly read-only chronological view over the WP-REC-04B audit-event API.
 * It renders the paginated event list, a bounded client-side page filter, and
 * a read-only detail panel. There is deliberately no create/edit/delete,
 * approve/reject, retry, or procurement-execute control anywhere on this
 * route.
 *
 * Authorization is enforced by the backend (AUDITOR / AI_ADMINISTRATOR); the
 * sidebar already limits navigation visibility to those roles. This route
 * renders whatever the backend returns and surfaces 401/403/404 safely.
 */

import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, FileText, Search } from 'lucide-react'

import { AuditEventDetail } from '@/components/audit/audit-event-detail'
import { AuditEventTypeBadge } from '@/components/audit/audit-event-type-badge'
import { filterAuditEvents } from '@/components/audit/audit-filter'
import { DataEmptyState } from '@/components/common/DataEmptyState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuditEvents } from '@/hooks/use-audit-events'
import {
  AUDIT_DEFAULT_PAGE_SIZE,
  AUDIT_PAGE_SIZE_OPTIONS,
  formatEntityType,
  formatEventType,
  formatShortId,
  formatTimestamp,
  getAuditErrorMessage,
} from '@/lib/audit-api'

export default function AuditLog() {
  const [limit, setLimit] = useState(AUDIT_DEFAULT_PAGE_SIZE)
  const [offset, setOffset] = useState(0)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const {
    events,
    total,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useAuditEvents(limit, offset)

  // When the result set shrinks while the user is on a later page (or an
  // out-of-range offset is requested directly), a page can return zero items
  // while total > 0. Normalize the offset back to the first page so the UI
  // never shows the misleading "No audit events" state, and to avoid a
  // request loop or oscillating offset. The `total > 0` guard also prevents
  // this from firing while a fresh page is still loading (total is 0 then).
  useEffect(() => {
    if (total > 0 && events.length === 0 && !isLoading && !isError && offset > 0) {
      setOffset(0)
    }
  }, [total, events.length, isLoading, isError, offset])

  const filtered = useMemo(() => filterAuditEvents(events, query), [events, query])

  const totalPages = Math.max(1, Math.ceil(total / limit))
  const currentPage = Math.floor(offset / limit)
  const canPrev = offset > 0
  const canNext = offset + limit < total
  const firstItem = total === 0 ? 0 : offset + 1
  const lastItem = Math.min(offset + limit, total)

  function handleLimitChange(nextLimit: number) {
    setLimit(nextLimit)
    setOffset(0)
  }

  function handleTrace(correlationId: string) {
    setQuery(correlationId)
  }

  const isFiltering = query.trim().length > 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Audit Log</h1>
        <p className="mt-1 text-sm text-steel-400">
          Read-only chronological trace of approval and procurement audit
          events. Events are immutable through this interface.
        </p>
      </div>

      {/* Bounded client-side page filter */}
      <div className="space-y-1">
        <label
          htmlFor="audit-filter"
          className="block text-sm font-medium text-steel-300"
        >
          Filter current page
        </label>
        <div className="relative max-w-md">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-500"
            aria-hidden="true"
          />
          <input
            id="audit-filter"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Event type, entity, actor, correlation ID, risk…"
            className="w-full rounded-md border border-steel-600 bg-steel-900 py-2 pl-9 pr-3 text-sm text-white placeholder-steel-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            data-testid="audit-filter-input"
          />
        </div>
        {isFiltering && (
          <p className="text-xs text-steel-500" data-testid="audit-filter-note">
            Filtering the current page only ({filtered.length} of {events.length}{' '}
            events on this page). It does not search the full audit history.
          </p>
        )}
      </div>

      {isLoading && events.length === 0 ? (
        <div className="space-y-3" data-testid="loading-state">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : isError ? (
        <div
          className="flex flex-col items-center gap-4 p-8"
          data-testid="error-state"
          role="alert"
        >
          <AlertCircle className="h-12 w-12 text-destructive" />
          <p className="text-lg text-destructive">
            Failed to load the audit log.
          </p>
          {error && (
            <p className="text-sm text-steel-400">
              {getAuditErrorMessage(error)}
            </p>
          )}
          <Button onClick={() => refetch()} data-testid="reload-button">
            Reload audit log
          </Button>
        </div>
      ) : total === 0 ? (
        <DataEmptyState
          primaryText="No audit events"
          secondaryText="Audit events will appear here once approval and procurement actions occur."
          icon={
            <FileText
              className="mb-3 h-10 w-10 text-steel-500"
              aria-hidden="true"
            />
          }
        />
      ) : events.length === 0 ? (
        <div
          className="flex flex-col items-center gap-4 rounded-md border border-steel-700 bg-steel-800/40 px-6 py-12 text-center"
          data-testid="out-of-range-state"
        >
          <AlertCircle className="h-10 w-10 text-steel-500" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium text-steel-300">
              No events on this page.
            </p>
            <p className="mt-1 text-xs text-steel-500">
              This page is outside the available range. Showing the first page.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setOffset(0)}
            data-testid="reset-page-button"
          >
            Go to first page
          </Button>
        </div>
      ) : filtered.length === 0 ? (
        <div
          className="flex flex-col items-center gap-4 rounded-md border border-steel-700 bg-steel-800/40 px-6 py-12 text-center"
          data-testid="filtered-empty-state"
        >
          <Search className="h-10 w-10 text-steel-500" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium text-steel-300">
              No events match your filter on this page.
            </p>
            <p className="mt-1 text-xs text-steel-500">
              The filter only searches the current page. Try a broader term or
              navigate to another page.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => setQuery('')} data-testid="clear-filter-button">
            Clear filter
          </Button>
        </div>
      ) : (
        <div data-testid="audit-list">
          <div className="flex items-center justify-between">
            <p className="text-xs text-steel-500">
              Showing {firstItem}–{lastItem} of {total} events
              {isFetching ? ' (refreshing…)' : ''}
            </p>
          </div>

          <Table>
            <caption className="sr-only">Audit events (newest first)</caption>
            <TableHeader>
              <TableRow>
                <TableHead>Occurred at</TableHead>
                <TableHead>Event</TableHead>
                <TableHead>Entity</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Correlation</TableHead>
                <TableHead>
                  <span className="sr-only">Details</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((event) => (
                <TableRow key={event.id} data-testid="audit-event-row">
                  <TableCell className="whitespace-nowrap text-steel-300">
                    {formatTimestamp(event.created_at)}
                  </TableCell>
                  <TableCell>
                    <AuditEventTypeBadge eventType={event.event_type} />
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="text-steel-300">
                        {formatEntityType(event.entity_type)}
                      </span>
                      <span
                        className="text-xs text-steel-500"
                        title={event.entity_id}
                      >
                        {formatShortId(event.entity_id)}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-steel-300">
                    {event.actor_username ?? 'System'}
                  </TableCell>
                  <TableCell className="text-steel-300">
                    {event.risk_id ?? '—'}
                  </TableCell>
                  <TableCell>
                    <button
                      type="button"
                      onClick={() => handleTrace(event.correlation_id)}
                      className="text-xs text-primary-400 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      title={`Filter current page by correlation ID ${event.correlation_id}`}
                      aria-label={`Filter by correlation ID ${event.correlation_id}`}
                      data-testid={`trace-correlation-${event.id}`}
                    >
                      {formatShortId(event.correlation_id)}
                    </button>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setSelectedId(event.id)}
                      aria-label={`View details for ${formatEventType(event.event_type)}`}
                      data-testid={`view-event-${event.id}`}
                    >
                      View
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Pagination (the only backend-supported parameters: limit/offset) */}
      {events.length > 0 && (
        <div
          className="flex flex-wrap items-center justify-between gap-3"
          data-testid="pagination"
        >
          <div className="flex items-center gap-2 text-xs text-steel-400">
            <label htmlFor="audit-page-size">Rows per page</label>
            <select
              id="audit-page-size"
              value={limit}
              onChange={(e) => handleLimitChange(Number(e.target.value))}
              className="rounded-md border border-steel-600 bg-steel-900 px-2 py-1 text-sm text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
              data-testid="audit-page-size"
            >
              {AUDIT_PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={!canPrev}
              data-testid="prev-page"
            >
              Previous
            </Button>
            <span className="text-xs text-steel-400" data-testid="page-indicator">
              Page {currentPage + 1} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOffset(offset + limit)}
              disabled={!canNext}
              data-testid="next-page"
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <AuditEventDetail
        eventId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </div>
  )
}
