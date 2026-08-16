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
} from '@/lib/approval-api'

export interface UseApprovalRequestsResult {
  requests: ApprovalRequestResponse[]
  total: number
  isLoading: boolean
  isError: boolean
  error: Error | null
  refetch: () => void
}

/**
 * Fetch the caller-scoped approval requests.
 */
export function useApprovalRequests(): UseApprovalRequestsResult {
  const { data, isLoading, isError, error, refetch } = useQuery<
    { items: ApprovalRequestResponse[]; total: number },
    Error
  >({
    queryKey: ['approval-requests'],
    queryFn: async () => {
      const result = await fetchApprovalRequests()
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
