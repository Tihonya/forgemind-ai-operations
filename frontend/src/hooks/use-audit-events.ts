/**
 * TanStack Query hooks for the read-only Audit Log (WP-REC-04E).
 *
 * The list hook produces canonical query keys keyed by ``limit``/``offset``
 * (the only backend-supported parameters), so changing pagination issues a
 * new, deduplicated request and stale responses are superseded by key. The
 * detail hook is enabled only when an event is selected, so no detail request
 * is issued for an absent selection.
 */

import { useQuery } from '@tanstack/react-query'
import {
  fetchAuditEvent,
  fetchAuditEvents,
  type AuditEventListResponse,
  type AuditEventResponse,
} from '@/lib/audit-api'

export interface UseAuditEventsResult {
  events: AuditEventResponse[]
  total: number
  limit: number
  offset: number
  isLoading: boolean
  isFetching: boolean
  isError: boolean
  error: Error | null
  refetch: () => void
}

/**
 * Fetch one page of audit events. The query key is canonical
 * (``['audit-events', { limit, offset }]``) so pagination changes produce
 * distinct cache entries and no duplicate in-flight requests.
 */
export function useAuditEvents(
  limit: number,
  offset: number,
): UseAuditEventsResult {
  const { data, isLoading, isFetching, isError, error, refetch } = useQuery<
    AuditEventListResponse,
    Error
  >({
    queryKey: ['audit-events', { limit, offset }],
    queryFn: () => fetchAuditEvents(limit, offset),
    staleTime: 30_000,
    retry: 1,
  })

  return {
    events: data?.items ?? [],
    total: data?.total ?? 0,
    limit: data?.limit ?? limit,
    offset: data?.offset ?? offset,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  }
}

export interface UseAuditEventResult {
  event: AuditEventResponse | undefined
  isLoading: boolean
  isError: boolean
  error: Error | null
  refetch: () => void
}

/**
 * Fetch a single audit event by ID. ``enabled`` is false until an event is
 * selected, so no detail request is made for a null/absent selection.
 */
export function useAuditEvent(eventId: string | null): UseAuditEventResult {
  const { data, isLoading, isError, error, refetch } = useQuery<
    AuditEventResponse,
    Error
  >({
    queryKey: ['audit-event', eventId],
    queryFn: () => fetchAuditEvent(eventId as string),
    enabled: eventId !== null,
    staleTime: 60_000,
    retry: false,
  })

  return {
    event: data,
    isLoading,
    isError,
    error,
    refetch,
  }
}
