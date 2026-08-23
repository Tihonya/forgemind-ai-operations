/**
 * TanStack Query hook for fetching a paginated list of workflow run summaries.
 *
 * Wraps the existing `fetchWorkflowRuns` API client (workflow-api.ts).
 * Designed for reuse by WP-UX-02 and WP-UX-03.
 *
 * No polling — the dashboard and future list pages can refetch on user action
 * or via React Query's staleTime/refetchOnWindowFocus defaults.
 */

import { useQuery } from '@tanstack/react-query';
import {
  fetchWorkflowRuns,
  type WorkflowRunSummary,
  type WorkflowRunListResponse,
} from '@/lib/workflow-api';

export interface UseWorkflowRunsResult {
  runs: WorkflowRunSummary[];
  total: number;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Fetch a paginated list of workflow run summaries.
 *
 * @param limit  - page size (default 10)
 * @param offset - page offset (default 0)
 */
export function useWorkflowRuns(
  limit = 10,
  offset = 0,
): UseWorkflowRunsResult {
  const { data, isLoading, isError, error, refetch } = useQuery<
    WorkflowRunListResponse,
    Error
  >({
    queryKey: ['workflow-runs', limit, offset],
    queryFn: () => fetchWorkflowRuns(limit, offset),
    staleTime: 30_000,
    retry: 1,
  });

  return {
    runs: data?.items ?? [],
    total: data?.total ?? 0,
    isLoading,
    isError,
    error,
    refetch,
  };
}
