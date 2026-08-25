/**
 * Audit Log route (WP-REC-04E).
 *
 * Strictly read-only chronological view over the WP-REC-04B audit-event API.
 * It renders the paginated event list, a bounded client-side page filter, and
 * a read-only detail panel. There is deliberately no create/edit/delete,
 * approve/reject, retry, or procurement-execute control anywhere on this
 * route.
 *
 * Localized per WP-UX-UA-03; event/entity type badges, entity IDs, actor,
 * correlation IDs and timestamps remain machine content (timestamps format
 * with the active locale).
 */

import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertCircle, FileText, Search } from 'lucide-react'

import { AuditEventDetail } from '@/components/audit/audit-event-detail'
import { AuditEventTypeBadge } from '@/components/audit/audit-event-type-badge'
import { AuditTraceDialog } from '@/components/audit/audit-trace-dialog'
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
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import {
  AUDIT_DEFAULT_PAGE_SIZE,
  AUDIT_PAGE_SIZE_OPTIONS,
  formatEntityType,
  formatEventType,
  formatShortId,
  getAuditErrorKey,
} from '@/lib/audit-api'

export default function AuditLog() {
  const { t } = useTranslation('audit')
  const { formatDateTime } = useLocalizedFormatters()
  const [limit, setLimit] = useState(AUDIT_DEFAULT_PAGE_SIZE)
  const [offset, setOffset] = useState(0)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [traceCorrelationId, setTraceCorrelationId] = useState<string | null>(null)

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
        <h1 className="text-2xl font-semibold text-white">{t('title')}</h1>
        <p className="mt-1 text-sm text-steel-400">{t('subtitle')}</p>
      </div>

      {/* Bounded client-side page filter */}
      <div className="space-y-1">
        <label
          htmlFor="audit-filter"
          className="block text-sm font-medium text-steel-300"
        >
          {t('filter.label')}
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
            placeholder={t('filter.placeholder')}
            className="w-full rounded-md border border-steel-600 bg-steel-900 py-2 pl-9 pr-3 text-sm text-white placeholder-steel-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            data-testid="audit-filter-input"
          />
        </div>
        {isFiltering && (
          <p className="text-xs text-steel-500" data-testid="audit-filter-note">
            {t('filter.note', { filtered: filtered.length, total: events.length })}
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
          <p className="text-lg text-destructive">{t('loadFailed')}</p>
          {error && (
            <p className="text-sm text-steel-400">{t(getAuditErrorKey(error))}</p>
          )}
          <Button onClick={() => refetch()} data-testid="reload-button">
            {t('reload')}
          </Button>
        </div>
      ) : total === 0 ? (
        <DataEmptyState
          primaryText={t('emptyTitle')}
          secondaryText={t('emptyDescription')}
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
              {t('outOfRangeTitle')}
            </p>
            <p className="mt-1 text-xs text-steel-500">
              {t('outOfRangeDescription')}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setOffset(0)}
            data-testid="reset-page-button"
          >
            {t('goToFirstPage')}
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
              {t('filteredEmptyTitle')}
            </p>
            <p className="mt-1 text-xs text-steel-500">
              {t('filteredEmptyDescription')}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => setQuery('')} data-testid="clear-filter-button">
            {t('filter.clear')}
          </Button>
        </div>
      ) : (
        <div data-testid="audit-list">
          <div className="flex items-center justify-between">
            <p className="text-xs text-steel-500">
              {t('showingCount', { first: firstItem, last: lastItem, total })}
              {isFetching ? t('refreshing') : ''}
            </p>
          </div>

          <Table>
            <caption className="sr-only">{t('caption')}</caption>
            <TableHeader>
              <TableRow>
                <TableHead>{t('columns.occurredAt')}</TableHead>
                <TableHead>{t('columns.event')}</TableHead>
                <TableHead>{t('columns.entity')}</TableHead>
                <TableHead>{t('columns.actor')}</TableHead>
                <TableHead>{t('columns.risk')}</TableHead>
                <TableHead>{t('columns.correlation')}</TableHead>
                <TableHead>
                  <span className="sr-only">{t('columns.details')}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((event) => (
                <TableRow key={event.id} data-testid="audit-event-row">
                  <TableCell className="whitespace-nowrap text-steel-300">
                    {formatDateTime(event.created_at)}
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
                    {event.actor_username ?? t('system')}
                  </TableCell>
                  <TableCell className="text-steel-300">
                    {event.risk_id ?? '—'}
                  </TableCell>
                  <TableCell>
                    <button
                      type="button"
                      onClick={() => handleTrace(event.correlation_id)}
                      className="text-xs text-primary-400 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      title={t('filter.byCorrelationTitle', { correlationId: event.correlation_id })}
                      aria-label={t('filter.byCorrelationAria', { correlationId: event.correlation_id })}
                      data-testid={`trace-correlation-${event.id}`}
                    >
                      {formatShortId(event.correlation_id)}
                    </button>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setTraceCorrelationId(event.correlation_id)}
                        aria-label={t('viewTraceAria', { eventType: formatEventType(event.event_type) })}
                        data-testid={`trace-event-${event.id}`}
                      >
                        {t('trace')}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setSelectedId(event.id)}
                        aria-label={t('viewDetailsAria', { eventType: formatEventType(event.event_type) })}
                        data-testid={`view-event-${event.id}`}
                      >
                        {t('view')}
                      </Button>
                    </div>
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
            <label htmlFor="audit-page-size">{t('pagination.rowsPerPage')}</label>
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
              {t('pagination.previous')}
            </Button>
            <span className="text-xs text-steel-400" data-testid="page-indicator">
              {t('pagination.pageIndicator', { current: currentPage + 1, total: totalPages })}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOffset(offset + limit)}
              disabled={!canNext}
              data-testid="next-page"
            >
              {t('pagination.next')}
            </Button>
          </div>
        </div>
      )}

      <AuditEventDetail
        eventId={selectedId}
        onClose={() => setSelectedId(null)}
      />

      <AuditTraceDialog
        correlationId={traceCorrelationId}
        onClose={() => setTraceCorrelationId(null)}
      />
    </div>
  )
}
