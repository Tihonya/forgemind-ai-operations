import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import LatestAIAnalysisWidget from '../LatestAIAnalysisWidget';
import * as useWorkflowRunsModule from '@/hooks/use-workflow-runs';
import type { WorkflowRunSummary } from '@/lib/workflow-api';

vi.mock('@/hooks/use-workflow-runs');

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={ui} />
          <Route
            path="/workflow-runs/:runId"
            element={<div>Run Detail Page</div>}
          />
          <Route path="/supply-risk" element={<div>Supply Risk Page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function createRunSummary(
  overrides: Partial<WorkflowRunSummary> = {},
): WorkflowRunSummary {
  return {
    id: 'run-001',
    correlation_id: 'corr-001',
    state: 'COMPLETED',
    plan_id: 'PLAN-2026-W31',
    triggered_by: 'manager.demo',
    error_code: null,
    error_detail: null,
    started_at: '2026-08-23T14:30:00Z',
    completed_at: '2026-08-23T14:32:00Z',
    created_at: '2026-08-23T14:30:00Z',
    updated_at: '2026-08-23T14:32:00Z',
    ...overrides,
  };
}

describe('LatestAIAnalysisWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [],
      total: 0,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('latest-ai-analysis-loading')).toBeInTheDocument();
  });

  it('renders error state', () => {
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [],
      total: 0,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('latest-ai-analysis-error')).toBeInTheDocument();
    expect(screen.getByText('Unable to load AI analysis')).toBeInTheDocument();
    expect(screen.getByTestId('latest-ai-analysis-retry')).toBeInTheDocument();
  });

  it('renders empty/no-run state with Review supply risks CTA', () => {
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [],
      total: 0,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('latest-ai-analysis-empty')).toBeInTheDocument();
    expect(screen.getByText('No AI analysis yet')).toBeInTheDocument();
    const cta = screen.getByTestId('latest-ai-analysis-cta');
    expect(cta).toHaveTextContent('Review supply risks');
    expect(cta.closest('a')).toHaveAttribute('href', '/supply-risk');
  });

  it('renders COMPLETED state with View recommendation CTA', () => {
    const run = createRunSummary({ state: 'COMPLETED' });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('latest-ai-analysis-content')).toBeInTheDocument();
    expect(screen.getByTestId('latest-ai-analysis-plan')).toHaveTextContent(
      'PLAN-2026-W31',
    );
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Completed',
    );
    const cta = screen.getByTestId('latest-ai-analysis-cta');
    expect(cta).toHaveTextContent('View recommendation');
    expect(cta.closest('a')).toHaveAttribute('href', '/workflow-runs/run-001');
  });

  it('renders nonterminal (RUNNING) state with View progress CTA', () => {
    const run = createRunSummary({ state: 'RUNNING' });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Analysis in progress',
    );
    const cta = screen.getByTestId('latest-ai-analysis-cta');
    expect(cta).toHaveTextContent('View progress');
  });

  it('renders PENDING state with View progress CTA', () => {
    const run = createRunSummary({ state: 'PENDING' });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Queued',
    );
    expect(screen.getByTestId('latest-ai-analysis-cta')).toHaveTextContent(
      'View progress',
    );
  });

  it('renders AWAITING_VALIDATION state with View progress CTA', () => {
    const run = createRunSummary({ state: 'AWAITING_VALIDATION' });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Validating result',
    );
    expect(screen.getByTestId('latest-ai-analysis-cta')).toHaveTextContent(
      'View progress',
    );
  });

  it('renders FAILED_PROVIDER state with Review failure CTA', () => {
    const run = createRunSummary({ state: 'FAILED_PROVIDER' });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'AI service unavailable',
    );
    const cta = screen.getByTestId('latest-ai-analysis-cta');
    expect(cta).toHaveTextContent('Review failure');
    expect(cta.closest('a')).toHaveAttribute('href', '/workflow-runs/run-001');
  });

  it('renders FAILED_VALIDATION state with Review failure CTA', () => {
    const run = createRunSummary({ state: 'FAILED_VALIDATION' });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Validation failed',
    );
    expect(screen.getByTestId('latest-ai-analysis-cta')).toHaveTextContent(
      'Review failure',
    );
  });

  it('renders FAILED_INTERNAL state with Review failure CTA', () => {
    const run = createRunSummary({ state: 'FAILED_INTERNAL' });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Analysis failed',
    );
    expect(screen.getByTestId('latest-ai-analysis-cta')).toHaveTextContent(
      'Review failure',
    );
  });

  it('renders FAILED_RETRIEVAL state with Review failure CTA', () => {
    const run = createRunSummary({ state: 'FAILED_RETRIEVAL' });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Evidence retrieval failed',
    );
    expect(screen.getByTestId('latest-ai-analysis-cta')).toHaveTextContent(
      'Review failure',
    );
  });

  it('shows triggered_by and timestamp when available', () => {
    const run = createRunSummary({
      triggered_by: 'manager.demo',
      created_at: '2026-08-23T14:30:00Z',
    });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    expect(screen.getByTestId('latest-ai-analysis-triggered-by')).toHaveTextContent(
      'manager.demo',
    );
    expect(screen.getByTestId('latest-ai-analysis-timestamp')).toBeInTheDocument();
  });

  it('CTA for existing run links to /workflow-runs/{run_id}', () => {
    const run = createRunSummary({
      id: 'run-abc-123',
      state: 'COMPLETED',
    });
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [run],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    const cta = screen.getByTestId('latest-ai-analysis-cta');
    expect(cta.closest('a')).toHaveAttribute(
      'href',
      '/workflow-runs/run-abc-123',
    );
  });

  it('CTA for no run links to /supply-risk', () => {
    vi.mocked(useWorkflowRunsModule.useWorkflowRuns).mockReturnValue({
      runs: [],
      total: 0,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<LatestAIAnalysisWidget />);
    const cta = screen.getByTestId('latest-ai-analysis-cta');
    expect(cta.closest('a')).toHaveAttribute('href', '/supply-risk');
  });
});
