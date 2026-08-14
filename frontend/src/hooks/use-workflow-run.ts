/**
 * TanStack Query hook for fetching a workflow run with DEC-012 polling.
 *
 * Polling contract (DEC-012):
 * - Interval: 3000 ms
 * - Polls only when successfully returned data has a non-terminal state:
 *   PENDING, RUNNING, AWAITING_VALIDATION
 * - Stops at terminal states:
 *   COMPLETED, FAILED_VALIDATION, FAILED_PROVIDER, FAILED_INTERNAL,
 *   FAILED_RETRIEVAL
 * - Does NOT poll on 404, 500, network error, undefined state,
 *   or absent runId (query disabled)
 */

import { useQuery } from '@tanstack/react-query';
import { fetchWorkflowRun, type WorkflowRunDetail } from '@/lib/workflow-api';

const NON_TERMINAL_STATES = new Set<string>([
  'PENDING',
  'RUNNING',
  'AWAITING_VALIDATION',
]);

export interface UseWorkflowRunResult {
  run: WorkflowRunDetail | undefined;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Fetch a workflow run by ID with polling for non-terminal states.
 *
 * @param runId - The workflow run UUID. When undefined/empty, the query
 *   is disabled and no request is made.
 */
export function useWorkflowRun(runId: string | undefined): UseWorkflowRunResult {
  const { data, isLoading, isError, error, refetch } = useQuery<
    WorkflowRunDetail,
    Error
  >({
    queryKey: ['workflow-run', runId],
    queryFn: () => fetchWorkflowRun(runId!),
    enabled: !!runId,
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state && NON_TERMINAL_STATES.has(state) ? 3000 : false;
    },
    retry: 1,
  });

  return {
    run: data,
    isLoading,
    isError,
    error,
    refetch,
  };
}
