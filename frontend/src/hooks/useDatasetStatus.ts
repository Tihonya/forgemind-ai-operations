/**
 * React hook for fetching dataset integrity status.
 */

import { useQuery } from '@tanstack/react-query';
import { getDatasetStatus, type DatasetStatusResponse } from '@/lib/dataset-api';

export function useDatasetStatus() {
  return useQuery<DatasetStatusResponse, Error>({
    queryKey: ['dataset-status'],
    queryFn: getDatasetStatus,
    staleTime: 60_000, // 1 minute
    retry: 1,
  });
}
