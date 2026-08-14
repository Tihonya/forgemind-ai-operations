/**
 * WP-REC-03G — Supply Risk Detail Workflow Start/Retry UI Tests
 *
 * Tests the frontend workflow start/retry interaction on the supply-risk
 * detail page:
 * - "Start AI Analysis" button visibility (role-gated)
 * - "Start AI Analysis" invokes the exact endpoint with exact method/payload
 * - Start is disabled while pending
 * - Successful start feeds run_id into polling
 * - "Retry" button visibility (state-gated + role-gated)
 * - Retry is hidden for non-retryable states
 * - Retry sends the exact backend request
 * - Retry is disabled while pending
 * - Successful retry resumes polling
 * - Start/retry/polling failures produce safe visible errors
 * - Long-running workflow does not block unrelated detail content
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';
import SupplyRiskDetail from '../supply-risk-detail';
import { createRisk } from '@/test/fixtures/risk-contract';
import type { WorkflowRunDetail as WorkflowRunDetailType } from '@/lib/workflow-api';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock the axios API client to intercept start/retry POST calls.
const apiPostMock = vi.fn();
vi.mock('@/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: (...args: unknown[]) => apiPostMock(...args),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

// Mock workflow-api to control fetchWorkflowRun behavior.
vi.mock('@/lib/workflow-api', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/workflow-api')>('@/lib/workflow-api');
  return {
    ...actual,
    fetchWorkflowRun: vi.fn(),
  };
});

// Mock data hooks with fixture data.
vi.mock('@/hooks/useActivePlan', () => ({
  useActivePlan: () => ({
    activePlan: activePlanMock,
    isLoading: false,
    error: null,
  }),
}));

vi.mock('@/hooks/useRisks', () => ({
  useRisks: () => ({
    risks: [
      createRisk({
        risk_id: 'RISK-001',
        component_name: 'Widget A',
        plan_code: 'PLAN-2026-W31',
      }),
    ],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/hooks/useRiskDetail', () => ({
  useRiskDetail: () => ({
    risk: createRisk({
      risk_id: 'RISK-001',
      component_name: 'Widget A',
      plan_code: 'PLAN-2026-W31',
    }),
    riskFound: true,
    component: {
      code: 'COMP-001',
      name: 'Widget A',
      unit: 'EA',
      alternatives: [],
    },
    inventory: {
      component_code: 'COMP-001',
      component_name: 'Widget A',
      unit: 'EA',
      balances: [],
      reservations: [],
    },
    purchaseOrders: [],
    purchaseOrdersPartial: false,
    productionOrder: null,
    productionPlan: null,
    isLoading: false,
    componentError: null,
    inventoryError: null,
    purchaseOrderError: null,
    productionOrderError: null,
    productionPlanError: null,
    refetchComponent: vi.fn(),
    refetchInventory: vi.fn(),
    refetchPurchaseOrders: vi.fn(),
    refetchProductionOrder: vi.fn(),
    refetchProductionPlan: vi.fn(),
  }),
}));

// Import the mocked workflow-api for controlling fetchWorkflowRun.
import * as workflowApi from '@/lib/workflow-api';

// ---------------------------------------------------------------------------
// Auth context mock — controllable per-test via authUser variable.
// ---------------------------------------------------------------------------

let authUser: {
  id: string;
  username: string;
  roles: string[];
} | null = {
  id: 'u1',
  username: 'pm-user',
  roles: ['production_manager'],
};

// ---------------------------------------------------------------------------
// Active plan mock — controllable per-test via activePlanMock variable.
// ---------------------------------------------------------------------------

let activePlanMock: { code: string; status: string } = {
  code: 'PLAN-2026-W31',
  status: 'ACTIVE',
};

vi.mock('@/contexts/auth.context', () => ({
  useAuth: () => ({
    user: authUser,
    isAuthenticated: authUser !== null,
    isLoading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  }),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRun(
  overrides: Partial<WorkflowRunDetailType> = {},
): WorkflowRunDetailType {
  return {
    id: 'run-abc-123',
    correlation_id: 'corr-001',
    state: 'PENDING',
    plan_id: 'plan-001',
    triggered_by: 'pm-user',
    error_code: null,
    error_detail: null,
    started_at: null,
    completed_at: null,
    created_at: '2026-01-01T10:00:00Z',
    updated_at: '2026-01-01T10:00:00Z',
    steps: [],
    recommendation: null,
    ...overrides,
  };
}

function makeAxiosError(
  status: number,
  data: { message?: string; error?: string } = {},
): unknown {
  // FastAPI wraps HTTPException detail as: {"detail": {"error": "...", "message": "..."}}
  return new axios.AxiosError(
    'Request failed',
    undefined,
    undefined,
    undefined,
    {
      status,
      data: { detail: data },
      statusText: '',
      headers: {},
      config: {} as never,
    },
  );
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
      mutations: {
        retry: false,
      },
    },
  });
}

function renderDetail(riskId = 'RISK-001') {
  const queryClient = createQueryClient();
  const user = userEvent.setup();
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/supply-risk/${riskId}`]}>
        <Routes>
          <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, user, queryClient };
}

function setStartResponse(
  runId = 'run-abc-123',
  state = 'PENDING',
): void {
  apiPostMock.mockImplementation(async (url: string) => {
    if (url === '/workflow-runs') {
      return {
        data: {
          run_id: runId,
          state,
          location: `/api/v1/workflow-runs/${runId}`,
        },
      };
    }
    if (url.startsWith('/workflow-runs/') && url.endsWith('/retry')) {
      return {
        data: {
          run_id: runId,
          state,
          location: `/api/v1/workflow-runs/${runId}`,
        },
      };
    }
    return { data: {} };
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SupplyRiskDetail — WP-REC-03G Start/Retry UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authUser = {
      id: 'u1',
      username: 'pm-user',
      roles: ['production_manager'],
    };
    activePlanMock = {
      code: 'PLAN-2026-W31',
      status: 'ACTIVE',
    };
    // Default: fetchWorkflowRun returns a PENDING run (for polling tests).
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ state: 'PENDING' }),
    );
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // -----------------------------------------------------------------------
  // Start AI Analysis — visibility
  // -----------------------------------------------------------------------

  it('authorized user (production_manager) can see "Start AI Analysis"', () => {
    renderDetail();
    expect(screen.getByTestId('start-workflow-button')).toBeInTheDocument();
    expect(screen.getByText('Start AI Analysis')).toBeInTheDocument();
  });

  it('unauthorized frontend role does not see the Start action', () => {
    authUser = {
      id: 'u2',
      username: 'auditor-user',
      roles: ['auditor'],
    };
    renderDetail();
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
  });

  it('user with no roles does not see the Start action', () => {
    authUser = {
      id: 'u3',
      username: 'no-role-user',
      roles: [],
    };
    renderDetail();
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Start AI Analysis — invocation
  // -----------------------------------------------------------------------

  it('Start invokes the exact endpoint with exact method and payload', async () => {
    setStartResponse();
    const { user } = renderDetail();

    const startButton = screen.getByTestId('start-workflow-button');
    await user.click(startButton);

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith(
        '/workflow-runs',
        { plan_id: 'PLAN-2026-W31' },
      );
    });
  });

  it('repeated Start interaction is disabled while the mutation is pending', async () => {
    // Make the API call hang to keep mutation pending.
    apiPostMock.mockImplementation(
      () => new Promise(() => {}),
    );
    const { user } = renderDetail();

    const startButton = screen.getByTestId('start-workflow-button');
    expect(startButton).not.toBeDisabled();
    await user.click(startButton);

    await waitFor(() => {
      expect(screen.getByTestId('start-workflow-button')).toBeDisabled();
    });
  });

  it('successful Start uses the backend-returned run_id', async () => {
    setStartResponse('run-xyz-789', 'PENDING');
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    // The run_id from the start response should feed into fetchWorkflowRun.
    await waitFor(() => {
      expect(workflowApi.fetchWorkflowRun).toHaveBeenCalledWith('run-xyz-789');
    });
  });

  it('successful Start transitions to polling-driven workflow presentation', async () => {
    setStartResponse('run-poll-001', 'PENDING');
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    await waitFor(() => {
      expect(screen.getByTestId('workflow-status')).toBeInTheDocument();
    });
    expect(screen.getByTestId('workflow-state').getAttribute('data-state')).toBe(
      'PENDING',
    );
  });

  // -----------------------------------------------------------------------
  // Non-freezing UI
  // -----------------------------------------------------------------------

  it('a long-running workflow does not remove or block unrelated supply-risk detail content', async () => {
    setStartResponse('run-long-001', 'RUNNING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ state: 'RUNNING' }),
    );
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    // Workflow status appears.
    await waitFor(() => {
      expect(screen.getByTestId('workflow-status')).toBeInTheDocument();
    });

    // Risk detail content is still present (Risk heading, Evidence, etc.)
    expect(screen.getByText('Risk RISK-001')).toBeInTheDocument();
    // Evidence panel heading text should be visible.
    // The EvidencePanel is rendered — check for its content.
    expect(screen.getByTestId('workflow-panel')).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Retry — visibility for each retry-eligible terminal state
  // -----------------------------------------------------------------------

  it.each([
    'FAILED_PROVIDER',
    'FAILED_VALIDATION',
    'FAILED_INTERNAL',
    'FAILED_RETRIEVAL',
  ])(
    'retry-eligible terminal state %s exposes Retry',
    async (state) => {
      // Set up: start a workflow, then make polling return the failed state.
      setStartResponse('run-failed-001', 'PENDING');
      vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
        makeRun({ id: 'run-failed-001', state }),
      );
      const { user } = renderDetail();

      await user.click(screen.getByTestId('start-workflow-button'));

      await waitFor(() => {
        expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
      });
    },
  );

  // -----------------------------------------------------------------------
  // FAILED_RETRIEVAL — terminal presentation (WP-REC-05 frontend scope)
  // -----------------------------------------------------------------------

  it('FAILED_RETRIEVAL is terminal — no perpetual running spinner', async () => {
    setStartResponse('run-fr-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-fr-001', state: 'FAILED_RETRIEVAL' }),
    );
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    await waitFor(() => {
      expect(
        screen.getByTestId('workflow-state').getAttribute('data-state'),
      ).toBe('FAILED_RETRIEVAL');
    });

    // Terminal state must not render the "updates automatically" running
    // indicator (no perpetual spinner).
    expect(screen.queryByText('(updates automatically)')).not.toBeInTheDocument();
  });

  it('non-manager non-creator does not see Retry for FAILED_RETRIEVAL', async () => {
    setStartResponse('run-fr-nc-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({
        id: 'run-fr-nc-001',
        state: 'FAILED_RETRIEVAL',
        triggered_by: 'someone-else',
      }),
    );
    const { user, rerender, queryClient } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });

    // Re-render as a non-manager non-creator.
    authUser = {
      id: 'u-fr-other',
      username: 'other-user',
      roles: ['engineer'],
    };
    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
          <Routes>
            <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Retry — hidden for non-retryable states
  // -----------------------------------------------------------------------

  it('Retry is hidden for PENDING', async () => {
    setStartResponse('run-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-001', state: 'PENDING' }),
    );
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    await waitFor(() => {
      expect(screen.getByTestId('workflow-state')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
  });

  it('Retry is hidden for RUNNING', async () => {
    setStartResponse('run-002', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-002', state: 'RUNNING' }),
    );
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    await waitFor(() => {
      expect(screen.getByTestId('workflow-state')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
  });

  it('Retry is hidden for AWAITING_VALIDATION', async () => {
    setStartResponse('run-003', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-003', state: 'AWAITING_VALIDATION' }),
    );
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    await waitFor(() => {
      expect(screen.getByTestId('workflow-state')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
  });

  it('Retry is hidden for COMPLETED', async () => {
    setStartResponse('run-004', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-004', state: 'COMPLETED' }),
    );
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    await waitFor(() => {
      expect(screen.getByTestId('workflow-state')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
  });

  it('Retry is hidden for absent and unknown state', () => {
    // No workflow run started — no active run_id, no state.
    renderDetail();
    expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Retry — authorization
  // -----------------------------------------------------------------------

  it('unauthorized frontend role does not see Retry', async () => {
    authUser = {
      id: 'u2',
      username: 'auditor-user',
      roles: ['auditor'],
    };
    // Even though auditor can see the page, they can't start.
    // No Start button → no workflow run → no Retry.
    renderDetail();
    expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Retry — invocation
  // -----------------------------------------------------------------------

  it('Retry sends the exact backend request', async () => {
    setStartResponse('run-retry-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-retry-001', state: 'FAILED_PROVIDER' }),
    );
    const { user } = renderDetail();

    // Start the workflow first.
    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });

    apiPostMock.mockClear();
    vi.mocked(workflowApi.fetchWorkflowRun).mockClear();

    // Make retry return PENDING state.
    apiPostMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/workflow-runs/') && url.endsWith('/retry')) {
        return {
          data: {
            run_id: 'run-retry-001',
            state: 'PENDING',
            location: '/api/v1/workflow-runs/run-retry-001',
          },
        };
      }
      return { data: {} };
    });

    await user.click(screen.getByTestId('retry-workflow-button'));

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith(
        '/workflow-runs/run-retry-001/retry',
      );
    });
  });

  it('duplicate Retry is disabled while pending', async () => {
    setStartResponse('run-retry-002', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-retry-002', state: 'FAILED_VALIDATION' }),
    );
    const { user } = renderDetail();

    // Start first.
    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });

    // Make retry call hang to keep it pending.
    apiPostMock.mockImplementation(
      () => new Promise(() => {}),
    );

    const retryButton = screen.getByTestId('retry-workflow-button');
    expect(retryButton).not.toBeDisabled();
    await user.click(retryButton);

    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeDisabled();
    });
  });

  it('successful Retry resumes polling', async () => {
    setStartResponse('run-resume-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-resume-001', state: 'FAILED_INTERNAL' }),
    );
    const { user } = renderDetail();

    // Start first.
    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });

    // Clear polling calls from the start phase.
    vi.mocked(workflowApi.fetchWorkflowRun).mockClear();

    // Make retry succeed and return PENDING.
    apiPostMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/workflow-runs/') && url.endsWith('/retry')) {
        return {
          data: {
            run_id: 'run-resume-001',
            state: 'PENDING',
            location: '/api/v1/workflow-runs/run-resume-001',
          },
        };
      }
      return { data: {} };
    });

    // After retry, polling should resume for the same run_id.
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-resume-001', state: 'PENDING' }),
    );

    await user.click(screen.getByTestId('retry-workflow-button'));

    await waitFor(() => {
      expect(workflowApi.fetchWorkflowRun).toHaveBeenCalledWith('run-resume-001');
    });
  });

  // -----------------------------------------------------------------------
  // Error states
  // -----------------------------------------------------------------------

  it('Start API failure produces a safe visible error', async () => {
    apiPostMock.mockRejectedValue(
      makeAxiosError(503, {
        error: 'workflow_enqueue_failed',
        message: 'The workflow job could not be enqueued. Please retry.',
      }),
    );
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    await waitFor(() => {
      expect(screen.getByTestId('workflow-start-error')).toBeInTheDocument();
    });
    // Safe message — no raw stack trace.
    expect(screen.getByText(/Failed to start AI analysis/i)).toBeInTheDocument();
    // Should show the backend-provided message.
    expect(
      screen.getByText(/The workflow job could not be enqueued/i),
    ).toBeInTheDocument();
  });

  it('Retry API failure produces a safe visible error', async () => {
    setStartResponse('run-err-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-err-001', state: 'FAILED_PROVIDER' }),
    );
    const { user } = renderDetail();

    // Start first to get to retry-eligible state.
    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });

    // Make retry fail.
    apiPostMock.mockRejectedValue(
      makeAxiosError(409, {
        error: 'workflow_run_not_retryable',
        message: 'The run is not in a retryable state.',
      }),
    );

    await user.click(screen.getByTestId('retry-workflow-button'));

    await waitFor(() => {
      expect(screen.getByTestId('workflow-retry-error')).toBeInTheDocument();
    });
    expect(screen.getByText(/Failed to retry workflow/i)).toBeInTheDocument();
  });

  it('polling/detail API failure preserves usable page content and produces the expected safe state', async () => {
    setStartResponse('run-poll-err-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockRejectedValue(
      makeAxiosError(500),
    );
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    // Page content remains visible.
    await waitFor(() => {
      expect(screen.getByText('Risk RISK-001')).toBeInTheDocument();
    });
    // Risk detail panels are still present.
    expect(screen.getByTestId('workflow-panel')).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Safe error — non-backend error does not expose transport messages (G1)
  // -----------------------------------------------------------------------

  it('network error without backend response shows generic safe message', async () => {
    // A raw Error without response.data.message should NOT expose
    // error.message (which could contain transport-library internals).
    apiPostMock.mockRejectedValue(new Error('Network Error: ECONNREFUSED 127.0.0.1:5432'));
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    await waitFor(() => {
      expect(screen.getByTestId('workflow-start-error')).toBeInTheDocument();
    });
    // The generic fallback should be shown, NOT the raw error.message.
    expect(screen.getByText(/An unexpected error occurred/i)).toBeInTheDocument();
    // The raw transport message must NOT be visible.
    expect(screen.queryByText(/ECONNREFUSED/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/127\.0\.0\.1/i)).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Target A: Start must NOT reappear when polling fails for an active run
  // -----------------------------------------------------------------------

  it('polling failure for an active run does not re-expose Start (Target A)', async () => {
    // Make the start succeed, but polling always fails.
    setStartResponse('run-active-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockRejectedValue(
      makeAxiosError(500),
    );
    const { user } = renderDetail();

    // Start a workflow — this sets activeRunId and begins polling.
    await user.click(screen.getByTestId('start-workflow-button'));

    // Wait for the polling error to surface (retry: 1 means 2 attempts).
    await waitFor(
      () => {
        expect(screen.getByTestId('workflow-polling-error')).toBeInTheDocument();
      },
      { timeout: 5000 },
    );

    // Supply-risk content remains usable.
    expect(screen.getByText('Risk RISK-001')).toBeInTheDocument();

    // CRITICAL: Start must NOT reappear for the unresolved active run.
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Target B: Creator-based Retry visibility
  // The test starts as PM, reaches a FAILED state, then re-renders as a
  // non-manager user whose username matches triggered_by.
  // -----------------------------------------------------------------------

  it.each([
    'FAILED_PROVIDER',
    'FAILED_VALIDATION',
    'FAILED_INTERNAL',
    'FAILED_RETRIEVAL',
  ])(
    'non-manager creator sees Retry for %s (Target B)',
    async (state) => {
      setStartResponse('run-creator-001', 'PENDING');
      vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
        makeRun({
          id: 'run-creator-001',
          state,
          triggered_by: 'creator-user',
        }),
      );
      const { user, rerender, queryClient } = renderDetail();

      // Start as PM to establish the active run.
      await user.click(screen.getByTestId('start-workflow-button'));
      await waitFor(() => {
        expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
      });

      // Re-render as a non-manager who is the creator.
      authUser = {
        id: 'u-creator',
        username: 'creator-user',
        roles: ['engineer'],
      };
      rerender(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
            <Routes>
              <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Creator still sees Retry for this failed state.
      await waitFor(() => {
        expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
      });
      // Non-manager does NOT see Start.
      expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
    },
  );

  it('non-manager non-creator does not see Retry (Target B)', async () => {
    setStartResponse('run-not-creator-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({
        id: 'run-not-creator-001',
        state: 'FAILED_PROVIDER',
        triggered_by: 'someone-else',
      }),
    );
    const { user, rerender, queryClient } = renderDetail();

    // Start as PM.
    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });

    // Re-render as a non-manager non-creator.
    authUser = {
      id: 'u-other',
      username: 'other-user',
      roles: ['engineer'],
    };
    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
          <Routes>
            <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Non-creator non-manager does NOT see Retry.
    await waitFor(() => {
      expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
    });
  });

  it('triggered_by null: non-manager cannot retry (Target B, D2 §5)', async () => {
    setStartResponse('run-null-trigger-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({
        id: 'run-null-trigger-001',
        state: 'FAILED_PROVIDER',
        triggered_by: null,
      }),
    );
    const { user, rerender, queryClient } = renderDetail();

    // Start as PM (triggered_by would actually be set by backend, but
    // we simulate a null triggered_by to test D2 §5).
    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });

    // Re-render as a non-manager.
    authUser = {
      id: 'u-null',
      username: 'some-user',
      roles: ['engineer'],
    };
    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
          <Routes>
            <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
    });
  });

  it('Retry hidden for COMPLETED even when user is creator (Target B)', async () => {
    setStartResponse('run-completed-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({
        id: 'run-completed-001',
        state: 'COMPLETED',
        triggered_by: 'creator-user',
      }),
    );
    const { user, rerender, queryClient } = renderDetail();

    // Start as PM.
    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('workflow-status')).toBeInTheDocument();
    });
    // No Retry for COMPLETED.
    expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();

    // Re-render as creator (non-manager).
    authUser = {
      id: 'u-creator',
      username: 'creator-user',
      roles: ['engineer'],
    };
    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
          <Routes>
            <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Still no Retry for COMPLETED, even as creator.
    await waitFor(() => {
      expect(screen.queryByTestId('retry-workflow-button')).not.toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Target C: Stale mutation responses after plan change are discarded
  // -----------------------------------------------------------------------

  it('stale start response arriving after plan change is discarded (Target C)', async () => {
    // Phase 1: Start with plan A. The start mutation hangs so we can
    // change the plan before it resolves.
    let resolveStart!: (value: { data: unknown }) => void;
    apiPostMock.mockImplementation(
      () => new Promise((resolve) => { resolveStart = resolve; }),
    );

    const { user, rerender, queryClient } = renderDetail();

    // Start the workflow while on plan A.
    await user.click(screen.getByTestId('start-workflow-button'));

    // Phase 2: Plan changes to plan B — trigger a rerender so the component
    // sees the new plan and updates currentPlanCodeRef.
    activePlanMock = { code: 'PLAN-2026-W99', status: 'ACTIVE' };
    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
          <Routes>
            <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Phase 3: The stale start response arrives with run_id for plan A.
    // Wrap in act to ensure React processes the onSuccess callback.
    await act(async () => {
      resolveStart({
        data: {
          run_id: 'run-plan-a-stale',
          state: 'PENDING',
          location: '/api/v1/workflow-runs/run-plan-a-stale',
        },
      });
    });

    // Phase 4: Deterministically wait for the Start mutation to reach
    // terminal 'success' state in the mutation cache. This proves that the
    // onSuccess callback has been invoked — not just that the HTTP call
    // resolved. The button state alone is insufficient because after plan
    // change the Start button may already be visible+enabled for plan B
    // before the mutation callback fires.
    await waitFor(() => {
      const mutations = queryClient.getMutationCache().getAll();
      const completedStart = mutations.find(
        (m) => m.state.status === 'success',
      );
      expect(completedStart).toBeDefined();
    });

    // Flush remaining React notifications after the mutation succeeded.
    await act(async () => {});

    // Phase 5: Affirmative evidence — plan-B Start button is present and
    // enabled, confirming the component has fully processed the plan change.
    await waitFor(() => {
      const btn = screen.getByTestId('start-workflow-button');
      expect(btn).toBeInTheDocument();
      expect(btn).not.toBeDisabled();
    });

    // Phase 6: The stale run_id must NOT be installed — no polling for it.
    const fetchCalls = vi.mocked(workflowApi.fetchWorkflowRun).mock.calls;
    const staleCallFound = fetchCalls.some(
      (call) => call[0] === 'run-plan-a-stale',
    );
    expect(staleCallFound).toBe(false);

    // No workflow status should appear because the stale run_id was rejected.
    expect(screen.queryByTestId('workflow-status')).not.toBeInTheDocument();
  });

  it('stale retry response arriving after plan change is discarded (Target C)', async () => {
    // Phase 1: Start with plan A, reach a retry-eligible state.
    setStartResponse('run-plan-a-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-plan-a-001', state: 'FAILED_PROVIDER' }),
    );
    const { user, rerender, queryClient } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });

    // Phase 2: Make retry hang so we can change the plan before it resolves.
    let resolveRetry!: (value: { data: unknown }) => void;
    apiPostMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/workflow-runs/') && url.endsWith('/retry')) {
        return new Promise((resolve) => { resolveRetry = resolve; });
      }
      return { data: {} };
    });

    // Capture existing mutations before clicking Retry to identify the NEW
    // mutation created by the Retry action (cache-delta mechanism).
    const mutationsBeforeRetry = new Set(
      queryClient.getMutationCache().getAll(),
    );

    // Click retry while on plan A.
    await user.click(screen.getByTestId('retry-workflow-button'));

    // Identify the newly created Retry mutation by finding cache entries
    // that weren't present before the Retry click.
    const newMutations = queryClient
      .getMutationCache()
      .getAll()
      .filter((mutation) => !mutationsBeforeRetry.has(mutation));

    expect(newMutations).toHaveLength(1);
    const retryMutation = newMutations[0];

    // Affirmatively assert the Retry mutation is pending before resolution.
    expect(retryMutation.state.status).toBe('pending');

    // Phase 3: Plan changes to plan B — trigger a rerender so the component
    // sees the new plan and updates currentPlanCodeRef.
    activePlanMock = { code: 'PLAN-2026-W99', status: 'ACTIVE' };
    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
          <Routes>
            <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Spy on invalidateQueries to verify it's not called with stale run_id
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    invalidateSpy.mockClear();

    // Clear mocks to track new calls after the plan change.
    vi.mocked(workflowApi.fetchWorkflowRun).mockClear();

    // Phase 4: The stale retry response arrives.
    // Wrap in act to ensure React processes the onSuccess callback.
    await act(async () => {
      resolveRetry({
        data: {
          run_id: 'run-plan-a-001',
          state: 'PENDING',
          location: '/api/v1/workflow-runs/run-plan-a-001',
        },
      });
    });

    // Phase 5: Deterministically wait for the CAPTURED Retry mutation to reach
    // terminal 'success' state. This proves that the onSuccess callback has been
    // invoked for THIS specific mutation — not the earlier Start mutation.
    await waitFor(() => {
      expect(retryMutation.state.status).toBe('success');
    });

    // Flush remaining React notifications after the mutation succeeded.
    await act(async () => {});

    // Phase 6: The stale retry must NOT have installed the run_id for plan A.
    // Check that fetchWorkflowRun was never called with the plan-A run_id.
    const fetchCalls = vi.mocked(workflowApi.fetchWorkflowRun).mock.calls;
    const staleCallFound = fetchCalls.some(
      (call) => call[0] === 'run-plan-a-001',
    );
    expect(staleCallFound).toBe(false);

    // Phase 7: Explicitly prove that plan-A invalidation did NOT occur.
    // Check that queryClient.invalidateQueries was never called with the
    // plan-A run_id after the plan change.
    const invalidateCalls = invalidateSpy.mock.calls;
    const staleInvalidationFound = invalidateCalls.some(
      (call: unknown[]) => {
        const filters = call[0];
        if (filters && typeof filters === 'object' && 'queryKey' in filters) {
          const queryKey = (filters as { queryKey: unknown[] }).queryKey;
          return Array.isArray(queryKey) && queryKey[1] === 'run-plan-a-001';
        }
        return false;
      },
    );
    expect(staleInvalidationFound).toBe(false);
  });

  it('valid start response for unchanged plan installs run_id correctly', async () => {
    // This test proves that a non-stale response still works as expected.
    setStartResponse('run-valid-001', 'PENDING');
    const { user } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));

    // The run_id should be installed and polling should start.
    await waitFor(() => {
      expect(workflowApi.fetchWorkflowRun).toHaveBeenCalledWith('run-valid-001');
    });
    expect(screen.getByTestId('workflow-status')).toBeInTheDocument();
  });

  it('valid retry response for unchanged plan resumes polling correctly', async () => {
    // This test proves that a non-stale retry response still works.
    setStartResponse('run-valid-retry-001', 'PENDING');
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ id: 'run-valid-retry-001', state: 'FAILED_INTERNAL' }),
    );
    const { user, queryClient } = renderDetail();

    await user.click(screen.getByTestId('start-workflow-button'));
    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });

    // Clear polling calls from the start phase.
    vi.mocked(workflowApi.fetchWorkflowRun).mockClear();

    // Spy on invalidateQueries to verify it's called with correct run_id
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    invalidateSpy.mockClear();

    // Make retry succeed.
    apiPostMock.mockImplementation(async (url: string) => {
      if (url.startsWith('/workflow-runs/') && url.endsWith('/retry')) {
        return {
          data: {
            run_id: 'run-valid-retry-001',
            state: 'PENDING',
            location: '/api/v1/workflow-runs/run-valid-retry-001',
          },
        };
      }
      return { data: {} };
    });

    await user.click(screen.getByTestId('retry-workflow-button'));

    // Polling should resume for the same run_id.
    await waitFor(() => {
      expect(workflowApi.fetchWorkflowRun).toHaveBeenCalledWith('run-valid-retry-001');
    });

    // Verify invalidation was called with the correct run_id
    const invalidateCalls = invalidateSpy.mock.calls;
    const validInvalidationFound = invalidateCalls.some(
      (call: unknown[]) => {
        const filters = call[0];
        if (filters && typeof filters === 'object' && 'queryKey' in filters) {
          const queryKey = (filters as { queryKey: unknown[] }).queryKey;
          return Array.isArray(queryKey) && queryKey[1] === 'run-valid-retry-001';
        }
        return false;
      },
    );
    expect(validInvalidationFound).toBe(true);
  });
});
