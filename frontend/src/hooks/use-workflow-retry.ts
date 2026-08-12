/**
 * TanStack Query mutation hook for retrying a failed workflow run (WP-REC-03G).
 *
 * Calls POST /api/v1/workflow-runs/{run_id}/retry with no request body.
 * The backend performs the D1 atomic conditional FAILED_* → PENDING
 * transition and enqueues an ARQ retry job. Returns run_id, state, and
 * location.
 *
 * Authorization: run creator OR PRODUCTION_MANAGER (enforced by backend).
 * The frontend hides the Retry button for unauthorized users, but
 * backend authorization remains the authoritative enforcement boundary.
 *
 * Retry-eligible terminal failure states (canonical, from
 * backend/app/ai/workflow/state_machine.py):
 *   FAILED_PROVIDER, FAILED_VALIDATION, FAILED_INTERNAL
 */

import { useMutation, type MutateOptions } from '@tanstack/react-query';
import api from '@/lib/api';

/** Response body for POST /workflow-runs/{run_id}/retry (202 Accepted). */
export interface WorkflowRetryResponse {
  run_id: string;
  state: string;
  location: string;
}

/**
 * Retry a failed workflow run.
 *
 * @param runId - The workflow run UUID to retry.
 * @returns The backend response with run_id, state, and location.
 */
export async function retryWorkflowRun(
  runId: string,
): Promise<WorkflowRetryResponse> {
  const response = await api.post<WorkflowRetryResponse>(
    `/workflow-runs/${runId}/retry`,
  );
  return response.data;
}

export interface UseWorkflowRetryResult {
  mutate: (
    runId: string,
    options?: MutateOptions<WorkflowRetryResponse, Error, string>,
  ) => void;
  mutateAsync: (runId: string) => Promise<WorkflowRetryResponse>;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  data: WorkflowRetryResponse | undefined;
  reset: () => void;
}

/**
 * Mutation hook to retry a failed workflow run.
 *
 * Exposes pending, success, and failure states. The caller is responsible
 * for resuming the existing useWorkflowRun polling hook after success.
 */
export function useWorkflowRetry(): UseWorkflowRetryResult {
  const mutation = useMutation<WorkflowRetryResponse, Error, string>({
    mutationFn: retryWorkflowRun,
  });

  return {
    mutate: mutation.mutate,
    mutateAsync: mutation.mutateAsync,
    isPending: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error,
    data: mutation.data,
    reset: mutation.reset,
  };
}
