import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RiskSummaryWidget from '../RiskSummaryWidget';
import { useRiskSummary } from '@/hooks/useRiskSummary';

vi.mock('@/hooks/useRiskSummary');

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

describe('RiskSummaryWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    vi.mocked(useRiskSummary).mockReturnValue({
      summary: { total: 0, critical: 0, high: 0, medium: 0, low: 0 },
      isLoading: true,
      isError: false,
      error: null,
    });

    renderWithQuery(<RiskSummaryWidget planCode="PLAN-001" />);
    expect(screen.getByTestId('risk-summary-widget')).toBeInTheDocument();
    expect(screen.getByTestId('risk-summary-loading')).toBeInTheDocument();
  });

  it('renders error state', () => {
    vi.mocked(useRiskSummary).mockReturnValue({
      summary: { total: 0, critical: 0, high: 0, medium: 0, low: 0 },
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
    });

    renderWithQuery(<RiskSummaryWidget planCode="PLAN-001" />);
    expect(screen.getByTestId('risk-summary-error')).toBeInTheDocument();
    expect(screen.getByText('Unable to load risk summary')).toBeInTheDocument();
  });

  it('renders no risks state', () => {
    vi.mocked(useRiskSummary).mockReturnValue({
      summary: { total: 0, critical: 0, high: 0, medium: 0, low: 0 },
      isLoading: false,
      isError: false,
      error: null,
    });

    renderWithQuery(<RiskSummaryWidget planCode="PLAN-001" />);
    expect(screen.getByText('No active risks for this plan')).toBeInTheDocument();
  });

  it('renders risk summary with severities', () => {
    vi.mocked(useRiskSummary).mockReturnValue({
      summary: { total: 5, critical: 2, high: 1, medium: 1, low: 1 },
      isLoading: false,
      isError: false,
      error: null,
    });

    renderWithQuery(<RiskSummaryWidget planCode="PLAN-001" />);
    expect(screen.getByTestId('risk-summary-content')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument(); // total
    expect(screen.getByTestId('severity-critical-count')).toHaveTextContent('2');
    expect(screen.getByTestId('severity-high-count')).toHaveTextContent('1');
    expect(screen.getByTestId('severity-medium-count')).toHaveTextContent('1');
    expect(screen.getByTestId('severity-low-count')).toHaveTextContent('1');
  });

  it('does not fetch risks when planCode is null', () => {
    vi.mocked(useRiskSummary).mockReturnValue({
      summary: { total: 0, critical: 0, high: 0, medium: 0, low: 0 },
      isLoading: false,
      isError: false,
      error: null,
    });

    renderWithQuery(<RiskSummaryWidget planCode={null} />);
    expect(useRiskSummary).toHaveBeenCalledWith(null);
  });
});
