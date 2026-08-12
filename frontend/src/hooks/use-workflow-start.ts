/**
 * TanStack Query mutation hook for starting a workflow run (WP-REC-03G).
 *
 * Calls POST /api/v1/workflow-runs with the plan code as plan_id.
 * The backend resolves the plan code to a UUID, creates a PENDING run,
 * and enqueues an ARQ job. Returns run_id, state, and location.
 *
 * Authorization: PRODUCTION_MANAGER role (enforced by backend).
 * The frontend hides the Start button for unauthorized users, but
 * backend authorization remains the authoritative enforcement boundary.
 */

import { useMutation, type MutateOptions } from '@tanstack/react-query';
import api from '@/lib/api';

/** Response body for POST /workflow-runs (202 Accepted). */
export interface WorkflowStartResponse {
  run_id: string;
  state: string;
  location: string;
}

/** Request body for POST /workflow-runs. */
export interface WorkflowStartRequest {
  plan_id: string;
}

/**
 * Start a new workflow run.
 *
 * @param payload - Contains plan_id (the external production plan code).
 * @returns The backend response with run_id, state, and location.
 */
export async function startWorkflowRun(
  payload: WorkflowStartRequest,
): Promise<WorkflowStartResponse> {
  const response = await api.post<WorkflowStartResponse>(
    '/workflow-runs',
    payload,
  );
  return response.data;
}

export interface UseWorkflowStartResult {
  mutate: (
    payload: WorkflowStartRequest,
    options?: MutateOptions<WorkflowStartResponse, Error, WorkflowStartRequest>,
  ) => void;
  mutateAsync: (payload: WorkflowStartRequest) => Promise<WorkflowStartResponse>;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  data: WorkflowStartResponse | undefined;
  reset: () => void;
}

/**
 * Mutation hook to start a workflow run.
 *
 * Exposes pending, success, and failure states. The caller is responsible
 * for feeding the returned run_id into the existing useWorkflowRun polling
 * hook after success.
 */
export function useWorkflowStart(): UseWorkflowStartResult {
  const mutation = useMutation<WorkflowStartResponse, Error, WorkflowStartRequest>({
    mutationFn: startWorkflowRun,
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
