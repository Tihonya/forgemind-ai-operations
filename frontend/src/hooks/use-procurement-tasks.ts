/**
 * TanStack Query hooks for the procurement-task API (WP-UX-UA-05).
 *
 * List is caller-scoped (backend enforces read scope per role); creation is
 * permitted only for the specialist who approved the request (backend is the
 * authoritative boundary — the frontend only hides controls as a usability
 * mirror).
 */

import { useMutation, useQuery } from '@tanstack/react-query'
import {
  createProcurementTask,
  fetchProcurementTasks,
  type ProcurementTaskResponse,
} from '@/lib/procurement-api'

export interface UseProcurementTasksResult {
  tasks: ProcurementTaskResponse[]
  total: number
  isLoading: boolean
  isError: boolean
  error: Error | null
  refetch: () => void
}

/**
 * Fetch the caller-scoped procurement-task list.
 *
 * @param enabled when false, the query is disabled (no request is issued).
 *   Callers use this to avoid issuing a request known to be forbidden for
 *   the active role (e.g. AUDITOR has no procurement read authority).
 */
export function useProcurementTasks(enabled = true): UseProcurementTasksResult {
  const { data, isLoading, isError, error, refetch } = useQuery<
    { items: ProcurementTaskResponse[]; total: number },
    Error
  >({
    queryKey: ['procurement-tasks'],
    queryFn: async () => {
      const result = await fetchProcurementTasks()
      return { items: result.items, total: result.total }
    },
    staleTime: 30_000,
    retry: 1,
    enabled,
  })

  return {
    tasks: data?.items ?? [],
    total: data?.total ?? 0,
    isLoading,
    isError,
    error,
    refetch,
  }
}

export interface UseProcurementCreateResult {
  mutateAsync: (approvalRequestId: string) => Promise<ProcurementTaskResponse>
  isPending: boolean
}

/**
 * Mutation hook to create a procurement task from an APPROVED approval
 * request. Duplicate execution is idempotent on the backend (returns the
 * already-created task).
 */
export function useProcurementCreate(): UseProcurementCreateResult {
  const mutation = useMutation<ProcurementTaskResponse, Error, string>({
    mutationFn: createProcurementTask,
  })

  return {
    mutateAsync: mutation.mutateAsync,
    isPending: mutation.isPending,
  }
}
