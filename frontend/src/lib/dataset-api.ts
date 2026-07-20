/**
 * Dataset status API client for WP-3.4.
 *
 * Endpoint: GET /api/v1/system/dataset/status
 * Requires authentication.
 */

import api from './api';

export interface DatasetStatusResponse {
  status: 'valid' | 'invalid' | 'not_loaded';
  dataset_version: string;
  checksum_algorithm: string;
  expected_checksum: string;
  actual_checksum: string | null;
}

/**
 * Fetch dataset integrity status.
 * Requires Bearer token authentication.
 */
export async function getDatasetStatus(): Promise<DatasetStatusResponse> {
  const response = await api.get<DatasetStatusResponse>('/system/dataset/status');
  return response.data;
}
