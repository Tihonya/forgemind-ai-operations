/**
 * TanStack Query hook for fetching a paginated list of workflow run summaries.
 *
 * Wraps the existing `fetchWorkflowRuns` API client (workflow-api.ts).
 * Designed for reuse by WP-UX-02 (risk-detail plan-scoped latest run)
 * and WP-UX-03 (archive list).
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
  /** The planCode used for this query, or null if unfiltered. */
  queriedPlanCode: string | null;
  /** True when the query is deliberately disabled (not yet authoritative). */
  isDisabled: boolean;
  refetch: () => void;
}

export interface UseWorkflowRunsOptions {
  /** Page size (default 10). */
  limit?: number;
  /** Page offset (default 0). */
  offset?: number;
  /**
   * Optional production plan code filter (e.g. PLAN-2026-W31).
   * When provided, only runs for that plan are returned.
   * Undefined means no filter (all plans).
   */
  planCode?: string;
  /**
   * Explicit execution gate. When false, the queryFn MUST NOT execute
   * and no network request is issued. Default: true (enabled).
   *
   * Use this to prevent an unfiltered/global query from firing before
   * a required parameter (e.g. planCode) is resolved. When disabled:
   * - isLoading is false (not pending);
   * - runs is [] and total is 0 (no data);
   * - isDisabled is true (callers can distinguish "not yet
   *   authoritative / disabled" from "authoritative query completed
   *   with zero runs").
   */
  enabled?: boolean;
}

/**
 * Fetch a paginated list of workflow run summaries.
 *
 * The React Query key includes every parameter that changes the result
 * (planCode, limit, offset) to prevent cache collisions between:
 * - the Dashboard's global latest-run query (no planCode);
 * - the Risk Detail's plan-scoped latest-run query (planCode set).
 *
 * @param options - Optional filter/pagination options.
 */
export function useWorkflowRuns(
  options?: UseWorkflowRunsOptions,
): UseWorkflowRunsResult {
  const limit = options?.limit ?? 10;
  const offset = options?.offset ?? 0;
  const planCode = options?.planCode;
  const enabled = options?.enabled ?? true;

  const { data, isLoading, isError, error, refetch } = useQuery<
    WorkflowRunListResponse,
    Error
  >({
    queryKey: ['workflow-runs', planCode ?? null, limit, offset],
    queryFn: () => fetchWorkflowRuns(limit, offset, planCode),
    staleTime: 30_000,
    retry: 1,
    enabled,
  });

  return {
    runs: data?.items ?? [],
    total: data?.total ?? 0,
    isLoading,
    isError,
    error,
    queriedPlanCode: planCode ?? null,
    isDisabled: !enabled,
    refetch,
  };
}
