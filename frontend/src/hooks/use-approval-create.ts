/**
 * TanStack Query mutation hook for creating an approval request
 * (WP-REC-04D). Creation is permitted for PRODUCTION_MANAGER only; the
 * backend is the authoritative enforcement boundary.
 */

import { useMutation, type MutateOptions } from '@tanstack/react-query'
import {
  createApprovalRequest,
  type ApprovalRequestCreate,
  type ApprovalRequestResponse,
} from '@/lib/approval-api'

export interface UseApprovalCreateResult {
  mutate: (
    payload: ApprovalRequestCreate,
    options?: MutateOptions<
      ApprovalRequestResponse,
      Error,
      ApprovalRequestCreate
    >,
  ) => void
  mutateAsync: (
    payload: ApprovalRequestCreate,
  ) => Promise<ApprovalRequestResponse>
  isPending: boolean
  isError: boolean
  error: Error | null
  data: ApprovalRequestResponse | undefined
  reset: () => void
}

/**
 * Mutation hook to create a PENDING approval request.
 */
export function useApprovalCreate(): UseApprovalCreateResult {
  const mutation = useMutation<
    ApprovalRequestResponse,
    Error,
    ApprovalRequestCreate
  >({
    mutationFn: createApprovalRequest,
  })

  return {
    mutate: mutation.mutate,
    mutateAsync: mutation.mutateAsync,
    isPending: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error,
    data: mutation.data,
    reset: mutation.reset,
  }
}
