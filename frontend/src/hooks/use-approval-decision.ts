/**
 * TanStack Query mutation hook for the approval decision endpoints
 * (WP-REC-04D). Approve and reject share one mutation; the ``kind``
 * discriminator selects the endpoint. Authorization is enforced by the
 * backend; the frontend hides controls as a usability mirror only.
 */

import { useMutation, type MutateOptions } from '@tanstack/react-query'
import {
  approveApprovalRequest,
  rejectApprovalRequest,
  type ApprovalRequestResponse,
} from '@/lib/approval-api'

export type ApprovalDecisionKind = 'approve' | 'reject'

export interface ApprovalDecisionInput {
  requestId: string
  kind: ApprovalDecisionKind
  comment: string
}

export interface UseApprovalDecisionResult {
  mutate: (
    input: ApprovalDecisionInput,
    options?: MutateOptions<
      ApprovalRequestResponse,
      Error,
      ApprovalDecisionInput
    >,
  ) => void
  mutateAsync: (
    input: ApprovalDecisionInput,
  ) => Promise<ApprovalRequestResponse>
  isPending: boolean
  isError: boolean
  error: Error | null
  data: ApprovalRequestResponse | undefined
  reset: () => void
}

function decideApprovalRequest(
  input: ApprovalDecisionInput,
): Promise<ApprovalRequestResponse> {
  if (input.kind === 'approve') {
    return approveApprovalRequest(input.requestId, input.comment)
  }
  return rejectApprovalRequest(input.requestId, input.comment)
}

/**
 * Mutation hook for approve/reject. Exposes pending, success, and failure
 * states. The caller invalidates the list query after the mutation settles.
 */
export function useApprovalDecision(): UseApprovalDecisionResult {
  const mutation = useMutation<
    ApprovalRequestResponse,
    Error,
    ApprovalDecisionInput
  >({
    mutationFn: decideApprovalRequest,
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
