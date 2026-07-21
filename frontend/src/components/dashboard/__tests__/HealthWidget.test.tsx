import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import HealthWidget from '../HealthWidget';
import { useHealth } from '@/hooks/useHealth';

const user = userEvent.setup();

vi.mock('@/hooks/useHealth');

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('HealthWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    vi.mocked(useHealth).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useHealth>);

    renderWithQuery(<HealthWidget />);
    expect(screen.getByTestId('health-widget')).toBeInTheDocument();
    expect(screen.getByTestId('health-loading')).toBeInTheDocument();
  });

  it('renders error state', () => {
    vi.mocked(useHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
    } as ReturnType<typeof useHealth>);

    renderWithQuery(<HealthWidget />);
    expect(screen.getByTestId('health-error')).toBeInTheDocument();
    expect(screen.getByText('Health check unavailable')).toBeInTheDocument();
  });

  it('renders healthy status', () => {
    vi.mocked(useHealth).mockReturnValue({
      data: {
        status: 'healthy',
        timestamp: '2026-01-15T10:00:00Z',
        correlation_id: 'test-id',
        checks: {
          backend: 'ok',
          postgresql: 'ok',
          redis: 'ok',
          alembic_revision: 'abc123',
          worker: 'ok',
        },
      },
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useHealth>);

    renderWithQuery(<HealthWidget />);
    expect(screen.getByTestId('health-content')).toBeInTheDocument();
    expect(screen.getByText('Healthy')).toBeInTheDocument();
    expect(screen.getByTestId('health-icon-healthy')).toBeInTheDocument();
  });

  it('renders degraded status', () => {
    vi.mocked(useHealth).mockReturnValue({
      data: {
        status: 'degraded',
        timestamp: '2026-01-15T10:00:00Z',
        correlation_id: 'test-id',
        checks: {
          backend: 'ok',
          postgresql: 'ok',
          redis: 'error: connection refused',
          alembic_revision: 'abc123',
          worker: 'ok',
        },
      },
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useHealth>);

    renderWithQuery(<HealthWidget />);
    expect(screen.getByText('Degraded')).toBeInTheDocument();
    expect(screen.getByTestId('health-icon-degraded')).toBeInTheDocument();
  });

  it('renders unhealthy status', () => {
    vi.mocked(useHealth).mockReturnValue({
      data: {
        status: 'unhealthy',
        timestamp: '2026-01-15T10:00:00Z',
        correlation_id: 'test-id',
        checks: {
          backend: 'error',
          postgresql: 'error',
          redis: 'error',
          alembic_revision: 'unknown',
          worker: 'unavailable',
        },
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useHealth>);

    renderWithQuery(<HealthWidget />);
    expect(screen.getByText('Unhealthy')).toBeInTheDocument();
    expect(screen.getByTestId('health-icon-unhealthy')).toBeInTheDocument();
  });

  it('calls refetch when retry button is clicked', async () => {
    const refetchSpy = vi.fn();
    vi.mocked(useHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
      refetch: refetchSpy,
    } as unknown as ReturnType<typeof useHealth>);

    renderWithQuery(<HealthWidget />);
    const retryButton = screen.getByTestId('health-retry');
    await user.click(retryButton);
    expect(refetchSpy).toHaveBeenCalledTimes(1);
  });
});
