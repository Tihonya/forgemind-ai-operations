/**
 * React hook for fetching system health status.
 */

import { useQuery } from '@tanstack/react-query';
import { getHealth, type HealthCheckResponse } from '@/lib/health-api';

export function useHealth() {
  return useQuery<HealthCheckResponse, Error>({
    queryKey: ['health'],
    queryFn: getHealth,
    staleTime: 30_000, // 30 seconds
    retry: 2,
  });
}
