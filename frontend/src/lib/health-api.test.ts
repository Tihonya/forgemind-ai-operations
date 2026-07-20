import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getHealth, type HealthCheckResponse } from '@/lib/health-api';

describe('getHealth', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches health data from /health endpoint', async () => {
    const mockResponse: HealthCheckResponse = {
      status: 'healthy',
      timestamp: '2025-01-20T10:00:00Z',
      correlation_id: 'test-correlation-id',
      checks: {
        backend: 'ok',
        postgresql: 'ok',
        redis: 'ok',
        alembic_revision: 'abc123',
        worker: 'ok',
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    const result = await getHealth();
    expect(result).toEqual(mockResponse);
    expect(global.fetch).toHaveBeenCalledWith(
      '/health',
      expect.objectContaining({ method: 'GET' })
    );
  });

  it('throws error on non-ok response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    });

    await expect(getHealth()).rejects.toThrow('Health check failed: 500 Internal Server Error');
  });

  it('uses default /health path when VITE_HEALTH_URL is not set', async () => {
    const mockResponse: HealthCheckResponse = {
      status: 'healthy',
      timestamp: '2025-01-20T10:00:00Z',
      correlation_id: 'test-correlation-id',
      checks: {
        backend: 'ok',
        postgresql: 'ok',
        redis: 'ok',
        alembic_revision: 'abc123',
        worker: 'ok',
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    await getHealth();
    // The URL is captured at module load time; default is /health
    expect(global.fetch).toHaveBeenCalledWith(
      '/health',
      expect.any(Object)
    );
  });
});
