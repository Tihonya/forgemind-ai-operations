/**
 * React hook for fetching and aggregating risk severity counts.
 */

import { useQuery } from '@tanstack/react-query';
import {
  getProductionPlanRisks,
  aggregateRiskSummary,
  type RiskRecordWithId,
  type RiskSummary,
} from '@/lib/risks-api';

export interface UseRiskSummaryResult {
  risks: RiskRecordWithId[];
  summary: RiskSummary;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

export function useRiskSummary(planCode: string | null): UseRiskSummaryResult {
  const { data, isLoading, isError, error } = useQuery<
    RiskRecordWithId[],
    Error
  >({
    queryKey: ['risks', planCode],
    queryFn: () => getProductionPlanRisks(planCode!),
    enabled: planCode !== null,
    staleTime: 60_000, // 1 minute
    retry: 1,
  });

  const risks = data ?? [];
  const summary = aggregateRiskSummary(risks);

  return {
    risks,
    summary,
    isLoading,
    isError,
    error,
  };
}
