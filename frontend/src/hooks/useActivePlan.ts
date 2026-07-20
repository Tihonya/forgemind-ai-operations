/**
 * React hook for fetching and selecting the active production plan.
 */

import { useQuery } from '@tanstack/react-query';
import {
  getProductionPlans,
  selectActivePlan,
  type ProductionPlanSummary,
  type ProductionPlanListResponse,
} from '@/lib/production-plans-api';

export interface UseActivePlanResult {
  plans: ProductionPlanSummary[];
  activePlan: ProductionPlanSummary | null;
  hasMultipleActive: boolean;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

export function useActivePlan(): UseActivePlanResult {
  const { data, isLoading, isError, error } = useQuery<
    ProductionPlanListResponse,
    Error
  >({
    queryKey: ['production-plans'],
    queryFn: () => getProductionPlans(200, 0),
    staleTime: 60_000, // 1 minute
    retry: 1,
  });

  const plans = data?.items ?? [];
  const activePlan = data ? selectActivePlan(plans) : null;
  const activeCount = plans.filter((p) => p.status === 'EXECUTING').length;
  const hasMultipleActive = activeCount > 1;

  return {
    plans,
    activePlan,
    hasMultipleActive,
    isLoading,
    isError,
    error,
  };
}
