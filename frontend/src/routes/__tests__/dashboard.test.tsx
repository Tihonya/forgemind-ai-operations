import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Dashboard from '@/routes/dashboard';
import i18n from '@/i18n';

vi.mock('@/hooks/useActivePlan');
vi.mock('@/hooks/use-workflow-runs');
vi.mock('@/hooks/use-approval-requests');
vi.mock('@/hooks/useHealth');
vi.mock('@/hooks/useDatasetStatus');
vi.mock('@/hooks/useRiskSummary');

import * as useActivePlanModule from '@/hooks/useActivePlan';
import * as useWorkflowRunsModule from '@/hooks/use-workflow-runs';
import * as useApprovalRequestsModule from '@/hooks/use-approval-requests';
import * as useHealthModule from '@/hooks/useHealth';
import * as useDatasetStatusModule from '@/hooks/useDatasetStatus';
import * as useRiskSummaryModule from '@/hooks/useRiskSummary';

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Dashboard — WP-UX-01', () => {
  afterEach(() => {
    act(() => {
      void i18n.changeLanguage('uk');
    });
  });

  beforeEach(() => {
    vi.clearAllMocks();

    // Default: all hooks return safe empty/loading-false states
    vi.mocked(useActivePlanModule.useActivePlan).mockReturnValue({
      plans: [],
      activePlan: null,
      hasMultipleActive: false,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [],
      total: 0,
      isLoading: false,
      isError: false,
      error: null,
      queriedPlanCode: null,
      isDisabled: false,
      refetch: vi.fn(),
    });
    vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
      requests: [],
      total: 0,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    vi.mocked(useHealthModule.useHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useHealthModule.useHealth>);
    vi.mocked(useDatasetStatusModule.useDatasetStatus).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useDatasetStatusModule.useDatasetStatus>);
    vi.mocked(useRiskSummaryModule.useRiskSummary).mockReturnValue({
      risks: [],
      summary: { total: 0, critical: 0, high: 0, medium: 0, low: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  describe('no stale text', () => {
    it('does not render "Unavailable"', () => {
      renderDashboard();
      expect(screen.queryByText(/Unavailable/i)).not.toBeInTheDocument();
    });

    it('does not render "Phase 5"', () => {
      renderDashboard();
      expect(screen.queryByText(/Phase 5/i)).not.toBeInTheDocument();
    });

    it('does not render "Phase 6"', () => {
      renderDashboard();
      expect(screen.queryByText(/Phase 6/i)).not.toBeInTheDocument();
    });

    it('does not render "Estimated Time Saved"', () => {
      renderDashboard();
      expect(
        screen.queryByText(/Estimated Time Saved/i),
      ).not.toBeInTheDocument();
    });

    it('does not render "Metric available in Phase 5"', () => {
      renderDashboard();
      expect(
        screen.queryByText(/Metric available/i),
      ).not.toBeInTheDocument();
    });

    it('does not render "Latest Agent Runs"', () => {
      renderDashboard();
      expect(
        screen.queryByText(/Latest Agent Runs/i),
      ).not.toBeInTheDocument();
    });

    it('does not render "Pending Approvals"', () => {
      renderDashboard();
      expect(
        screen.queryByText(/Pending Approvals/i),
      ).not.toBeInTheDocument();
    });
  });

  describe('live widgets render', () => {
    it('renders Latest AI Analysis widget', () => {
      renderDashboard();
      expect(
        screen.getByTestId('latest-ai-analysis-widget'),
      ).toBeInTheDocument();
      expect(screen.getByText('Latest AI Analysis')).toBeInTheDocument();
    });

    it('renders Awaiting Decision widget', () => {
      renderDashboard();
      expect(
        screen.getByTestId('awaiting-decision-widget'),
      ).toBeInTheDocument();
      expect(screen.getByText('Awaiting Decision')).toBeInTheDocument();
    });
  });

  describe('existing core widgets still render', () => {
    it('renders Active Plan widget', () => {
      renderDashboard();
      expect(
        screen.getByTestId('active-plan-widget'),
      ).toBeInTheDocument();
    });

    it('renders Risk Summary widget', () => {
      renderDashboard();
      expect(
        screen.getByTestId('risk-summary-widget'),
      ).toBeInTheDocument();
    });

    it('renders Health widget', () => {
      renderDashboard();
      expect(screen.getByTestId('health-widget')).toBeInTheDocument();
    });

    it('renders Dataset Status widget', () => {
      renderDashboard();
      expect(
        screen.getByTestId('dataset-status-widget'),
      ).toBeInTheDocument();
    });
  });

  describe('page heading', () => {
    it('renders Ukrainian Operations Dashboard heading by default', () => {
      renderDashboard();
      expect(
        screen.getByRole('heading', { name: 'Операційний огляд', level: 1 }),
      ).toBeInTheDocument();
    });

    it('renders Ukrainian purpose text by default', () => {
      renderDashboard();
      expect(
        screen.getByText(
          'Активний план, ризики постачання та рішення за участю ШІ — в одному місці.',
        ),
      ).toBeInTheDocument();
    });

    it('renders English heading and purpose after switching to en', () => {
      act(() => {
        void i18n.changeLanguage('en');
      });
      renderDashboard();
      expect(
        screen.getByRole('heading', { name: 'Operations Dashboard', level: 1 }),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          'Active plan, supply risks, and AI-assisted decisions — in one place',
        ),
      ).toBeInTheDocument();
    });
  });
});
