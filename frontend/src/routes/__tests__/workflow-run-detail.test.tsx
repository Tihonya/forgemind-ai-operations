import i18n from '@/i18n'
import { render, screen, act, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import axios from 'axios';
import WorkflowRunDetail from '../workflow-run-detail';
import { useWorkflowRun } from '@/hooks/use-workflow-run';
import * as workflowApi from '@/lib/workflow-api';
import type { WorkflowRunDetail as WorkflowRunDetailType } from '@/lib/workflow-api';

// WP-UX-UA-03: pin the active locale to English so behavior assertions
// against English copy stay stable after the Ukrainian-first migration.
beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})


// Module-level mock — vitest hoists this to the top
vi.mock('@/lib/workflow-api', async () => {
  const actual = await vi.importActual<typeof workflowApi>('@/lib/workflow-api');
  return {
    ...actual,
    fetchWorkflowRun: vi.fn(),
    fetchWorkflowRuns: vi.fn(),
  };
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRun(overrides: Partial<WorkflowRunDetailType> = {}): WorkflowRunDetailType {
  return {
    id: 'run-001',
    correlation_id: 'corr-001',
    state: 'COMPLETED',
    plan_id: 'plan-001',
    triggered_by: 'test-user',
    error_code: null,
    error_detail: null,
    started_at: '2026-01-01T10:00:00Z',
    completed_at: '2026-01-01T10:01:00Z',
    created_at: '2026-01-01T10:00:00Z',
    updated_at: '2026-01-01T10:01:00Z',
    steps: [],
    recommendation: null,
    ...overrides,
  };
}

function makeStepWithRetry() {
  return {
    id: 'step-001',
    run_id: 'run-001',
    correlation_id: 'corr-001',
    seq: 0,
    step_name: 'provider_call',
    status: 'completed',
    model_name: 'gpt-4o-mini',
    latency_ms: 1500,
    token_usage: { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 },
    step_metadata: {
      retry_count: 2,
      attempt_history: [
        {
          attempt_number: 0,
          outcome: 'retrying',
          error_type: 'TransientChatProviderError',
          backoff_delay_seconds: 1.0,
        },
        {
          attempt_number: 1,
          outcome: 'retrying',
          error_type: 'TransientChatProviderError',
          backoff_delay_seconds: 2.0,
        },
        {
          attempt_number: 2,
          outcome: 'success',
          error_type: '',
          backoff_delay_seconds: 0.0,
        },
      ],
    },
    error_code: null,
    error_detail: null,
    started_at: '2026-01-01T10:00:00Z',
    completed_at: '2026-01-01T10:00:30Z',
    created_at: '2026-01-01T10:00:00Z',
  };
}

function makeRecommendationContent() {
  return {
    schema_version: '1.0',
    run_id: 'run-001',
    plan_id: 'PLAN-2026-W31',
    risks: [
      {
        risk_id: 'RISK-001',
        summary: 'Test risk summary',
        business_impact: 'Test business impact',
        recommended_actions: [
          {
            action_type: 'CREATE_PROCUREMENT_TASK',
            title: 'Test action',
            rationale: 'Test rationale',
            requires_approval: true,
          },
        ],
        sources: [
          {
            document_id: 'DOC-001',
            version: '1.0',
            chunk_id: 'chunk-001',
          },
        ],
      },
    ],
  };
}

function makeAxiosError(status: number): unknown {
  const error = new axios.AxiosError(
    'Request failed',
    undefined,
    undefined,
    undefined,
    {
      status,
      data: {},
      statusText: '',
      headers: {},
      config: {} as never,
    },
  );
  return error;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
      },
    },
  });
}

function renderWithRouter(
  ui: React.ReactElement,
  queryClient: QueryClient,
  route: string = '/workflow-runs/run-001',
) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/workflow-runs/:runId" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Route rendering tests
// ---------------------------------------------------------------------------

describe('WorkflowRunDetail — route rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(
      () => new Promise<WorkflowRunDetailType>(() => {}),
    );

    const queryClient = createQueryClient();
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
  });

  it('renders not-found state for 404', async () => {
    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => {
      throw makeAxiosError(404);
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 } },
    });
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    const notFound = await screen.findByTestId('not-found-state', {}, { timeout: 3000 });
    expect(notFound).toBeInTheDocument();
    expect(screen.getByText('Workflow run not found')).toBeInTheDocument();
  });

  it('renders error state for 500 with reload button', async () => {
    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => {
      throw makeAxiosError(500);
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 } },
    });
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    const errorState = await screen.findByTestId('error-state', {}, { timeout: 3000 });
    expect(errorState).toBeInTheDocument();
    expect(screen.getByTestId('reload-button')).toBeInTheDocument();
    expect(screen.getByText('Reload details')).toBeInTheDocument();
  });

  it('renders run with steps', async () => {
    const run = makeRun({
      steps: [
        {
          id: 'step-001',
          run_id: 'run-001',
          correlation_id: 'corr-001',
          seq: 0,
          step_name: 'provider_call',
          status: 'completed',
          model_name: 'gpt-4o-mini',
          latency_ms: 1500,
          token_usage: null,
          step_metadata: null,
          error_code: null,
          error_detail: null,
          started_at: '2026-01-01T10:00:00Z',
          completed_at: '2026-01-01T10:00:30Z',
          created_at: '2026-01-01T10:00:00Z',
        },
      ],
    });

    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    await waitFor(() => {
      expect(screen.getByTestId('run-detail')).toBeInTheDocument();
    });
    expect(screen.getByText('provider_call')).toBeInTheDocument();
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument();
    expect(screen.getByText(/1500ms/)).toBeInTheDocument();
  });

  it('renders FAILED_VALIDATION state with error visible in steps', async () => {
    const run = makeRun({
      state: 'FAILED_VALIDATION',
      error_code: 'VALIDATION_ERROR',
      error_detail: 'StructuredOutputValidationError',
      steps: [
        {
          id: 'step-001',
          run_id: 'run-001',
          correlation_id: 'corr-001',
          seq: 0,
          step_name: 'provider_call',
          status: 'failed',
          model_name: null,
          latency_ms: null,
          token_usage: null,
          step_metadata: null,
          error_code: 'VALIDATION_ERROR',
          error_detail: 'INVALID_SCHEMA',
          started_at: '2026-01-01T10:00:00Z',
          completed_at: '2026-01-01T10:00:30Z',
          created_at: '2026-01-01T10:00:00Z',
        },
      ],
    });

    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    await waitFor(() => {
      expect(screen.getByTestId('run-detail')).toBeInTheDocument();
    });
    expect(screen.getByTestId('run-state-badge').getAttribute('data-code')).toBe(
      'FAILED_VALIDATION',
    );
    expect(screen.getByTestId('run-state-badge')).toHaveTextContent('Validation failed');
    expect(screen.getByTestId('step-error-code').textContent).toBe(
      'VALIDATION_ERROR',
    );
    expect(screen.getByTestId('step-error-detail').textContent).toBe(
      'INVALID_SCHEMA',
    );
  });

  it('renders FAILED_RETRIEVAL state with failed presentation', async () => {
    const run = makeRun({
      state: 'FAILED_RETRIEVAL',
      error_code: 'RETRIEVAL_FAILED',
      error_detail: 'RETRIEVAL_FAILED',
      steps: [
        {
          id: 'step-001',
          run_id: 'run-001',
          correlation_id: 'corr-001',
          seq: 0,
          step_name: 'retrieval',
          status: 'failed',
          model_name: null,
          latency_ms: null,
          token_usage: null,
          step_metadata: null,
          error_code: 'RETRIEVAL_FAILED',
          error_detail: 'RETRIEVAL_FAILED',
          started_at: '2026-01-01T10:00:00Z',
          completed_at: '2026-01-01T10:00:30Z',
          created_at: '2026-01-01T10:00:00Z',
        },
      ],
    });

    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    await waitFor(() => {
      expect(screen.getByTestId('run-detail')).toBeInTheDocument();
    });
    expect(screen.getByTestId('run-state-badge').getAttribute('data-code')).toBe(
      'FAILED_RETRIEVAL',
    );
    expect(screen.getByTestId('run-state-badge')).toHaveTextContent(
      'Evidence retrieval failed',
    );
    expect(screen.getByTestId('step-error-code').textContent).toBe(
      'RETRIEVAL_FAILED',
    );
    expect(screen.getByTestId('step-error-detail').textContent).toBe(
      'RETRIEVAL_FAILED',
    );
  });

  it('renders recommendation with content', async () => {
    const run = makeRun({
      recommendation: {
        id: 'rec-001',
        status: 'VALIDATED',
        schema_version: '1.0',
        content: makeRecommendationContent(),
        created_at: '2026-01-01T10:01:00Z',
        updated_at: '2026-01-01T10:01:00Z',
      },
    });

    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    await waitFor(() => {
      expect(screen.getByTestId('risk-RISK-001')).toBeInTheDocument();
    });
    expect(screen.getByText('Test risk summary')).toBeInTheDocument();
    expect(screen.getByText('Test business impact')).toBeInTheDocument();
    expect(screen.getByText('Test action')).toBeInTheDocument();
    expect(screen.getByText('DOC-001 (v1.0)')).toBeInTheDocument();
  });

  it('renders recommendation with content=null', async () => {
    const run = makeRun({
      recommendation: {
        id: 'rec-001',
        status: 'VALIDATED',
        schema_version: null,
        content: null,
        created_at: '2026-01-01T10:01:00Z',
        updated_at: '2026-01-01T10:01:00Z',
      },
    });

    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    await waitFor(() => {
      expect(screen.getByTestId('no-validated-content')).toBeInTheDocument();
    });
  });

  it('renders null recommendation placeholder', async () => {
    const run = makeRun({ recommendation: null });

    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    await waitFor(() => {
      expect(screen.getByTestId('no-recommendation')).toBeInTheDocument();
    });
  });

  it('renders retry visibility — retry_count and attempt_history', async () => {
    const run = makeRun({
      steps: [makeStepWithRetry()],
    });

    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderWithRouter(<WorkflowRunDetail />, queryClient);

    await waitFor(() => {
      expect(screen.getByTestId('retry-info')).toBeInTheDocument();
    });
    expect(screen.getByTestId('retry-count').textContent).toBe('2');
    expect(screen.getByTestId('attempt-0')).toBeInTheDocument();
    expect(screen.getByTestId('attempt-1')).toBeInTheDocument();
    expect(screen.getByTestId('attempt-2')).toBeInTheDocument();
    expect(screen.getAllByTestId('attempt-number')[0].textContent).toBe('0');
    expect(screen.getAllByTestId('attempt-outcome')[0].textContent).toBe(
      'retrying',
    );
    expect(screen.getAllByTestId('attempt-error-type')[0].textContent).toBe(
      'TransientChatProviderError',
    );
    expect(screen.getAllByTestId('attempt-backoff')[0].textContent).toBe('1s');
  });
});

// ---------------------------------------------------------------------------
// Polling behavior tests (real hook, mocked API, fake timers)
// ---------------------------------------------------------------------------

describe('useWorkflowRun — polling behavior', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  function createWrapper(queryClient: QueryClient) {
    return function Wrapper({ children }: { children: React.ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );
    };
  }

  async function settleQuery() {
    // Allow pending microtasks and query state to settle
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
  }

  it('PENDING activates polling — fetch at t=0, t=3000, t=6000', async () => {
    const mockedApi = vi.mocked(workflowApi);
    const run = makeRun({ state: 'PENDING' });
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(3);
  });

  it('RUNNING polls every 3000 ms', async () => {
    const mockedApi = vi.mocked(workflowApi);
    const run = makeRun({ state: 'RUNNING' });
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(2);
  });

  it('AWAITING_VALIDATION polls every 3000 ms', async () => {
    const mockedApi = vi.mocked(workflowApi);
    const run = makeRun({ state: 'AWAITING_VALIDATION' });
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(2);
  });

  it('COMPLETED stops polling', async () => {
    const mockedApi = vi.mocked(workflowApi);
    const run = makeRun({ state: 'COMPLETED' });
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);
  });

  it('FAILED_VALIDATION stops polling', async () => {
    const mockedApi = vi.mocked(workflowApi);
    const run = makeRun({ state: 'FAILED_VALIDATION' });
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);
  });

  it('FAILED_PROVIDER stops polling', async () => {
    const mockedApi = vi.mocked(workflowApi);
    const run = makeRun({ state: 'FAILED_PROVIDER' });
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);
  });

  it('FAILED_INTERNAL stops polling', async () => {
    const mockedApi = vi.mocked(workflowApi);
    const run = makeRun({ state: 'FAILED_INTERNAL' });
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);
  });

  it('FAILED_RETRIEVAL stops polling', async () => {
    const mockedApi = vi.mocked(workflowApi);
    const run = makeRun({ state: 'FAILED_RETRIEVAL' });
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => run);

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);
  });

  it('transition to terminal stops polling', async () => {
    const mockedApi = vi.mocked(workflowApi);
    let callCount = 0;
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => {
      callCount++;
      return callCount === 1
        ? makeRun({ state: 'RUNNING' })
        : makeRun({ state: 'COMPLETED' });
    });

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(2);

    // Now COMPLETED — polling should stop
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).toHaveBeenCalledTimes(2);
  });

  it('404 does not continue polling', async () => {
    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => {
      throw makeAxiosError(404);
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 } },
    });
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    // Wait for initial fetch + retry to settle (hook has retry: 1)
    await settleQuery();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await settleQuery();
    // After error + retry, record call count
    const callsAfterError = mockedApi.fetchWorkflowRun.mock.calls.length;
    expect(callsAfterError).toBeGreaterThanOrEqual(1);

    // Advance time significantly — no polling should occur for errors
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun.mock.calls.length).toBe(callsAfterError);
  });

  it('500 does not continue polling', async () => {
    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => {
      throw makeAxiosError(500);
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 } },
    });
    renderHook(() => useWorkflowRun('run-001'), {
      wrapper: createWrapper(queryClient),
    });

    // Wait for initial fetch + retry to settle (hook has retry: 1)
    await settleQuery();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await settleQuery();
    const callsAfterError = mockedApi.fetchWorkflowRun.mock.calls.length;
    expect(callsAfterError).toBeGreaterThanOrEqual(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun.mock.calls.length).toBe(callsAfterError);
  });

  it('absent runId makes no request', async () => {
    const mockedApi = vi.mocked(workflowApi);
    mockedApi.fetchWorkflowRun = vi.fn<(runId: string) => Promise<WorkflowRunDetailType>>(async () => makeRun());

    const queryClient = createQueryClient();
    renderHook(() => useWorkflowRun(undefined), {
      wrapper: createWrapper(queryClient),
    });

    await settleQuery();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    await settleQuery();
    expect(mockedApi.fetchWorkflowRun).not.toHaveBeenCalled();
  });
});
