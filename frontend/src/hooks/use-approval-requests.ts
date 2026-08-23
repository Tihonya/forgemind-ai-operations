/**
 * TanStack Query hook for the caller-scoped approval-request list.
 *
 * Reuses the typed approval API client (WP-REC-04D). The backend enforces
 * read scope per role; the frontend only renders what the list returns.
 */

import { useQuery } from '@tanstack/react-query'
import {
  fetchApprovalRequests,
  type ApprovalRequestResponse,
  type ApprovalStatus,
} from '@/lib/approval-api'

export interface UseApprovalRequestsResult {
  requests: ApprovalRequestResponse[]
  total: number
  isLoading: boolean
  isError: boolean
  error: Error | null
  refetch: () => void
}

export interface UseApprovalRequestsOptions {
  /** Optional status filter forwarded to the backend. */
  status?: ApprovalStatus
  /** Page size (default 50). */
  limit?: number
  /** Page offset (default 0). */
  offset?: number
}

/**
 * Fetch the caller-scoped approval requests.
 *
 * When `status` is provided, the backend filters results and `total` to
 * that status (composing with the caller's RBAC read scope). When omitted,
 * behavior is unchanged from the original unfiltered list.
 */
export function useApprovalRequests(
  options?: UseApprovalRequestsOptions,
): UseApprovalRequestsResult {
  const status = options?.status
  const limit = options?.limit ?? 50
  const offset = options?.offset ?? 0

  const { data, isLoading, isError, error, refetch } = useQuery<
    { items: ApprovalRequestResponse[]; total: number },
    Error
  >({
    queryKey: ['approval-requests', status, limit, offset],
    queryFn: async () => {
      const result = await fetchApprovalRequests(limit, offset, status)
      return { items: result.items, total: result.total }
    },
    staleTime: 30_000,
    retry: 1,
  })

  return {
    requests: data?.items ?? [],
    total: data?.total ?? 0,
    isLoading,
    isError,
    error,
    refetch,
  }
}
