import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ActivePlanWidget from '../ActivePlanWidget';
import * as useActivePlanModule from '@/hooks/useActivePlan';
import type { ProductionPlanSummary } from '@/lib/production-plans-api';

vi.mock('@/hooks/useActivePlan');

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('ActivePlanWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    vi.mocked(useActivePlanModule.useActivePlan).mockReturnValue({
      plans: [],
      activePlan: null,
      hasMultipleActive: false,
      isLoading: true,
      isError: false,
      error: null,
    });

    renderWithQuery(<ActivePlanWidget />);
    expect(screen.getByTestId('active-plan-widget')).toBeInTheDocument();
    expect(screen.getByTestId('plan-loading')).toBeInTheDocument();
  });

  it('renders error state', () => {
    vi.mocked(useActivePlanModule.useActivePlan).mockReturnValue({
      plans: [],
      activePlan: null,
      hasMultipleActive: false,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
    });

    renderWithQuery(<ActivePlanWidget />);
    expect(screen.getByTestId('plan-error')).toBeInTheDocument();
    expect(screen.getByText('Unable to load production plans')).toBeInTheDocument();
  });

  it('renders empty state when no active plan', () => {
    vi.mocked(useActivePlanModule.useActivePlan).mockReturnValue({
      plans: [],
      activePlan: null,
      hasMultipleActive: false,
      isLoading: false,
      isError: false,
      error: null,
    });

    renderWithQuery(<ActivePlanWidget />);
    expect(screen.getByTestId('no-active-plan')).toBeInTheDocument();
    expect(screen.getByText('No active production plan')).toBeInTheDocument();
  });

  it('renders active plan with correct data', () => {
    const plan: ProductionPlanSummary = {
      code: 'PLAN-2026-W31',
      status: 'EXECUTING',
      period_start: '2026-07-27',
      period_end: '2026-08-02',
    };

    vi.mocked(useActivePlanModule.useActivePlan).mockReturnValue({
      plans: [plan],
      activePlan: plan,
      hasMultipleActive: false,
      isLoading: false,
      isError: false,
      error: null,
    });

    renderWithQuery(<ActivePlanWidget />);
    expect(screen.getByTestId('plan-code')).toHaveTextContent('PLAN-2026-W31');
    expect(screen.getByTestId('plan-status')).toHaveTextContent('EXECUTING');
    expect(screen.getByTestId('plan-period')).toBeInTheDocument();
  });

  it('renders warning when multiple active plans exist', () => {
    const plan1: ProductionPlanSummary = {
      code: 'PLAN-2026-W31',
      status: 'EXECUTING',
      period_start: '2026-07-27',
      period_end: '2026-08-02',
    };
    const plan2: ProductionPlanSummary = {
      code: 'PLAN-2026-W32',
      status: 'EXECUTING',
      period_start: '2026-08-03',
      period_end: '2026-08-09',
    };

    vi.mocked(useActivePlanModule.useActivePlan).mockReturnValue({
      plans: [plan1, plan2],
      activePlan: plan2, // Later period_start
      hasMultipleActive: true,
      isLoading: false,
      isError: false,
      error: null,
    });

    renderWithQuery(<ActivePlanWidget />);
    expect(screen.getByTestId('plan-code')).toHaveTextContent('PLAN-2026-W32');
    expect(screen.getByTestId('multiple-active-warning')).toBeInTheDocument();
    expect(
      screen.getByText(/Multiple active plans detected/i)
    ).toBeInTheDocument();
  });

  it('does not render warning when single active plan', () => {
    const plan: ProductionPlanSummary = {
      code: 'PLAN-2026-W31',
      status: 'EXECUTING',
      period_start: '2026-07-27',
      period_end: '2026-08-02',
    };

    vi.mocked(useActivePlanModule.useActivePlan).mockReturnValue({
      plans: [plan],
      activePlan: plan,
      hasMultipleActive: false,
      isLoading: false,
      isError: false,
      error: null,
    });

    renderWithQuery(<ActivePlanWidget />);
    expect(screen.queryByTestId('multiple-active-warning')).not.toBeInTheDocument();
  });
});
