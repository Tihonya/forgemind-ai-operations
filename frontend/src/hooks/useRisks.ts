/**
 * TanStack Query hook for fetching risks for a production plan.
 *
 * Reuses the existing getProductionPlanRisks API client from WP-3.4.
 * Query is enabled only when planCode is non-empty.
 */

import { useQuery } from '@tanstack/react-query';
import {
  getProductionPlanRisks,
  type RiskRecordWithId,
} from '@/lib/risks-api';

export interface UseRisksResult {
  risks: RiskRecordWithId[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Fetch supply risks for the active production plan.
 *
 * @param planCode - production plan code; query is disabled if empty/null
 */
export function useRisks(planCode: string | null): UseRisksResult {
  const { data, isLoading, isError, error, refetch } = useQuery<
    RiskRecordWithId[],
    Error
  >({
    queryKey: ['risks', planCode],
    queryFn: () => getProductionPlanRisks(planCode!),
    enabled: !!planCode,
    staleTime: 30_000, // 30 seconds
    retry: 1,
  });

  return {
    risks: data ?? [],
    isLoading,
    isError,
    error,
    refetch,
  };
}
