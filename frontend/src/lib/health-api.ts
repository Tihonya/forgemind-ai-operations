/**
 * Health check API client for WP-3.4.
 *
 * The /health endpoint is public and NOT under /api/v1, so we cannot use
 * the existing api.ts instance (which has baseURL /api/v1). We use a
 * separate axios instance or fetch directly.
 */

const healthUrl = import.meta.env.VITE_HEALTH_URL ?? '/health';

export interface HealthCheckResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  correlation_id: string;
  checks: {
    backend: 'ok';
    postgresql: string;
    redis: string;
    alembic_revision: string;
    worker: string;
  };
}

/**
 * Fetch system health status.
 * Public endpoint, no authentication required.
 */
export async function getHealth(): Promise<HealthCheckResponse> {
  const response = await fetch(healthUrl, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status} ${response.statusText}`);
  }

  return response.json();
}
