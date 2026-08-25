import i18n from '@/i18n'
/**
 * WP-UX-02 — Supply Risk Detail: Restoration, Completed Moment, Status/Copy
 *
 * Tests the new WP-UX-02 product behavior:
 * - Latest plan-scoped run is restored on initial page load
 * - Refresh-equivalent render with existing completed run does not show Start
 * - Existing RUNNING run does not show Start
 * - Existing failed run exposes Retry when authorized
 * - No existing run allows the plan-analysis Start action
 * - Start remains unavailable while restoration lookup is unresolved
 * - Current plan change cannot be overwritten by stale previous-plan lookup
 * - Dashboard's global latest-run query remains unaffected
 * - COMPLETED + matching current-risk recommendation shows summary, impact,
 *   action, rationale, sources, approval-required message
 * - Recommendation for another risk is not accidentally shown
 * - COMPLETED + no current-risk item shows truthful absence state
 * - COMPLETED + recommendation null is controlled
 * - CTA routes to /workflow-runs/{run_id}
 * - Business-facing state label used instead of raw enum as primary display
 * - Start copy clearly communicates plan scope
 * - No duplicate Start appears after restored completed run
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import SupplyRiskDetail from '../supply-risk-detail';
import { createRisk } from '@/test/fixtures/risk-contract';
import type {
  WorkflowRunDetail as WorkflowRunDetailType,
  WorkflowRunListResponse,
} from '@/lib/workflow-api';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const apiPostMock = vi.fn();
const apiGetMock = vi.fn();

vi.mock('@/lib/api', () => ({
  default: {
    get: (...args: unknown[]) => apiGetMock(...args),
    post: (...args: unknown[]) => apiPostMock(...args),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

vi.mock('@/lib/workflow-api', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/workflow-api')>('@/lib/workflow-api');
  return {
    ...actual,
    fetchWorkflowRun: vi.fn(),
    fetchWorkflowRuns: vi.fn(),
  };
});

vi.mock('@/hooks/useActivePlan', () => ({
  useActivePlan: () => ({
    activePlan: activePlanMock,
    isLoading: planLoadingMock,
    error: planErrorMock,
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

import * as workflowApi from '@/lib/workflow-api';

// WP-UX-UA-03: pin the active locale to English so behavior assertions
// against English copy stay stable after the Ukrainian-first migration.
beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})


// ---------------------------------------------------------------------------
// Auth context mock
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

let activePlanMock: { code: string; status: string } | null = {
  code: 'PLAN-2026-W31',
  status: 'ACTIVE',
};

let planLoadingMock = false;
let planErrorMock: Error | null = null;

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

function makeCompletedRunWithRec(
  riskId = 'RISK-001',
  runId = 'run-completed-001',
): WorkflowRunDetailType {
  return makeRun({
    id: runId,
    state: 'COMPLETED',
    completed_at: '2026-01-01T10:05:00Z',
    triggered_by: 'pm-user',
    recommendation: {
      id: 'rec-001',
      status: 'VALIDATED',
      schema_version: '1.0',
      content: {
        schema_version: '1.0',
        run_id: runId,
        plan_id: 'PLAN-2026-W31',
        risks: [
          {
            risk_id: riskId,
            summary: 'Critical shortage of CTRL-X4 requires immediate action.',
            business_impact: 'Production line stoppage risk within 7 days.',
            recommended_actions: [
              {
                action_type: 'CREATE_PROCUREMENT_TASK',
                title: 'Expedite supplier order for CTRL-X4',
                rationale: 'Standard lead time exceeds the shortage window.',
                requires_approval: true,
              },
            ],
            sources: [
              {
                document_id: 'doc-uuid-001',
                version: '2.1',
                chunk_id: 'chunk-uuid-001',
              },
            ],
          },
        ],
      },
      created_at: '2026-01-01T10:05:00Z',
      updated_at: '2026-01-01T10:05:00Z',
    },
  });
}

function makeEmptyListResponse(): WorkflowRunListResponse {
  return { items: [], limit: 1, offset: 0, total: 0 };
}

function makeListWithRun(
  runId: string,
  state = 'COMPLETED',
): WorkflowRunListResponse {
  return {
    items: [
      {
        id: runId,
        correlation_id: 'corr-001',
        state,
        plan_id: 'plan-uuid-001',
        triggered_by: 'pm-user',
        error_code: null,
        error_detail: null,
        started_at: '2026-01-01T10:00:00Z',
        completed_at: state === 'COMPLETED' ? '2026-01-01T10:05:00Z' : null,
        created_at: '2026-01-01T10:00:00Z',
        updated_at: '2026-01-01T10:05:00Z',
      },
    ],
    limit: 1,
    offset: 0,
    total: 1,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
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
          <Route path="/workflow-runs/:runId" element={<div>Run Detail Page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, user, queryClient };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SupplyRiskDetail — WP-UX-02 Restoration & Completed Moment', () => {
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
    planLoadingMock = false;
    planErrorMock = null;
    // Default: no existing run → restoration returns empty.
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeEmptyListResponse());
    // Default: fetchWorkflowRun returns PENDING (for polling tests).
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeRun({ state: 'PENDING' }),
    );
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // -----------------------------------------------------------------------
  // RESTORATION
  // -----------------------------------------------------------------------

  it('latest plan-scoped run is restored on initial page load', async () => {
    const runId = 'run-restore-001';
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun(runId, 'COMPLETED'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeCompletedRunWithRec('RISK-001', runId));

    renderDetail();

    // The workflow state badge should appear (restored run).
    await waitFor(() => {
      expect(screen.getByTestId('workflow-status')).toBeInTheDocument();
    });

    // Start should NOT appear because an existing run was restored.
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
  });

  it('refresh-equivalent render with an existing completed run does not show Start', async () => {
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun('run-comp-001', 'COMPLETED'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeCompletedRunWithRec('RISK-001', 'run-comp-001'));

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('workflow-status')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
  });

  it('existing RUNNING run does not show Start', async () => {
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun('run-running-001', 'RUNNING'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeRun({ id: 'run-running-001', state: 'RUNNING' }));

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('workflow-status')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
  });

  it('existing failed run exposes Retry when authorized', async () => {
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun('run-failed-001', 'FAILED_PROVIDER'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeRun({ id: 'run-failed-001', state: 'FAILED_PROVIDER', triggered_by: 'pm-user' }));

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('retry-workflow-button')).toBeInTheDocument();
    });
    // Start should NOT appear — existing failed run is restored.
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
  });

  it('no existing run allows the plan-analysis Start action', async () => {
    // No existing runs.
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeEmptyListResponse());

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('start-workflow-button')).toBeInTheDocument();
    });
    expect(screen.getByText('Analyze production plan')).toBeInTheDocument();
  });

  it('Start remains unavailable while restoration lookup is unresolved', async () => {
    // Make fetchWorkflowRuns hang (restoration pending).
    vi.mocked(workflowApi.fetchWorkflowRuns).mockImplementation(
      () => new Promise(() => {}),
    );

    renderDetail();

    // Restoration loading indicator should be visible.
    await waitFor(() => {
      expect(screen.getByTestId('restoration-loading')).toBeInTheDocument();
    });

    // Start should NOT appear while restoration is pending.
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
  });

  it('current plan change cannot be overwritten by stale previous-plan lookup', async () => {
    // This is tested via the existing plan-change guard tests in the
    // WP-REC-03G suite. Here we verify that the restoration query
    // uses the current plan code, not a stale one.
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeEmptyListResponse());

    renderDetail();

    // Verify fetchWorkflowRuns was called with the current plan code.
    await waitFor(() => {
      expect(workflowApi.fetchWorkflowRuns).toHaveBeenCalledWith(
        1, 0, 'PLAN-2026-W31',
      );
    });
  });

  it('Dashboard global latest-run query remains unaffected by plan-scoped options', async () => {
    // The Dashboard uses useWorkflowRuns({ limit: 5, offset: 0 }) — no planCode.
    // The Risk Detail uses useWorkflowRuns({ planCode, limit: 1, offset: 0 }).
    // The query keys are different, so no cache collision.
    // We verify by checking that fetchWorkflowRuns is called with the
    // plan code parameter (not without it).
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeEmptyListResponse());

    renderDetail();

    await waitFor(() => {
      expect(workflowApi.fetchWorkflowRuns).toHaveBeenCalledWith(1, 0, 'PLAN-2026-W31');
    });

    // The Dashboard's call would be fetchWorkflowRuns(5, 0, undefined) —
    // a different query. The plan-scoped call always includes the plan code.
    expect(workflowApi.fetchWorkflowRuns).not.toHaveBeenCalledWith(5, 0, undefined);
  });

  // -----------------------------------------------------------------------
  // COMPLETED MOMENT
  // -----------------------------------------------------------------------

  it('COMPLETED + matching current-risk recommendation shows summary, impact, action, rationale, sources, approval', async () => {
    const runId = 'run-moment-001';
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun(runId, 'COMPLETED'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeCompletedRunWithRec('RISK-001', runId));

    renderDetail();

    // Wait for the recommendation panel.
    await waitFor(() => {
      expect(screen.getByTestId('recommendation-panel')).toBeInTheDocument();
    });

    // AI summary
    expect(screen.getByTestId('rec-summary')).toHaveTextContent('Critical shortage of CTRL-X4 requires immediate action.');
    // Business impact
    expect(screen.getByTestId('rec-business-impact')).toHaveTextContent('Production line stoppage risk within 7 days.');
    // Recommended action title
    expect(screen.getByText('Expedite supplier order for CTRL-X4')).toBeInTheDocument();
    // Rationale
    expect(screen.getByTestId('rec-action-rationale-0')).toHaveTextContent('Standard lead time exceeds the shortage window.');
    // Sources / evidence used
    expect(screen.getByTestId('evidence-used')).toBeInTheDocument();
    expect(screen.getByTestId('evidence-source-0')).toHaveTextContent('doc-uuid-001 (v2.1)');
    // Human approval boundary
    expect(screen.getByTestId('human-approval-boundary')).toBeInTheDocument();
    expect(screen.getByTestId('human-approval-boundary')).toHaveTextContent(/Human approval required before procurement/);
  });

  it('recommendation for another risk is not accidentally shown', async () => {
    const runId = 'run-other-risk-001';
    // Recommendation contains RISK-002, but we're viewing RISK-001.
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun(runId, 'COMPLETED'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeCompletedRunWithRec('RISK-002', runId));

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('recommendation-panel')).toBeInTheDocument();
    });

    // Should show the truthful absence state, not RISK-002's recommendation.
    expect(screen.getByTestId('no-recommendation-for-risk')).toBeInTheDocument();
    // Should NOT show RISK-002's summary.
    expect(screen.queryByTestId('rec-summary')).not.toBeInTheDocument();
  });

  it('COMPLETED + no current-risk item shows truthful absence state', async () => {
    const runId = 'run-absent-001';
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun(runId, 'COMPLETED'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeCompletedRunWithRec('RISK-999', runId));

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('no-recommendation-for-risk')).toBeInTheDocument();
    });
    expect(screen.getByTestId('no-recommendation-for-risk')).toHaveTextContent(
      /Analysis completed, but no AI recommendation was produced for this risk/,
    );
  });

  it('COMPLETED + recommendation null is controlled', async () => {
    const runId = 'run-null-rec-001';
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun(runId, 'COMPLETED'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeRun({
      id: runId,
      state: 'COMPLETED',
      recommendation: null,
    }));

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('no-recommendation-row')).toBeInTheDocument();
    });
    expect(screen.getByTestId('no-recommendation-row')).toHaveTextContent(
      /Analysis completed, but no recommendation was produced/,
    );
  });

  it('CTA routes to /workflow-runs/{run_id}', async () => {
    const runId = 'run-cta-001';
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun(runId, 'COMPLETED'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeCompletedRunWithRec('RISK-001', runId));

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('view-full-analysis')).toBeInTheDocument();
    });
    expect(screen.getByTestId('view-full-analysis').closest('a')).toHaveAttribute(
      'href',
      `/workflow-runs/${runId}`,
    );
  });

  // -----------------------------------------------------------------------
  // STATUS / COPY
  // -----------------------------------------------------------------------

  it('business-facing state label used instead of raw enum as primary display', async () => {
    const runId = 'run-label-001';
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun(runId, 'RUNNING'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeRun({ id: runId, state: 'RUNNING' }));

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('workflow-state-badge')).toBeInTheDocument();
    });
    // The badge should show the business label "Analysis in progress", not "RUNNING".
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent('Analysis in progress');
  });

  it('Start copy clearly communicates plan scope', async () => {
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeEmptyListResponse());

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('start-workflow-button')).toBeInTheDocument();
    });
    // Button text says "Analyze production plan" (not "Start AI Analysis").
    expect(screen.getByText('Analyze production plan')).toBeInTheDocument();
    // Supporting copy mentions the plan code.
    expect(screen.getByTestId('start-workflow-scope-copy')).toHaveTextContent(
      /Analyzes all supply risks in PLAN-2026-W31/,
    );
  });

  it('no duplicate Start appears after restored completed run', async () => {
    const runId = 'run-no-dup-001';
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeListWithRun(runId, 'COMPLETED'));
    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(makeCompletedRunWithRec('RISK-001', runId));

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('recommendation-panel')).toBeInTheDocument();
    });

    // Start button must not appear.
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // F-1/F-4: UNRESOLVED PLAN — NO GLOBAL QUERY, NO CROSS-PLAN INSTALL
  // -----------------------------------------------------------------------

  it('F-1/F-4: while active plan is unresolved, no global workflow-runs fetch is issued', async () => {
    // Simulate cold load: plan still loading.
    planLoadingMock = true;
    activePlanMock = null;

    // This mock should NEVER be called while plan is unresolved.
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeEmptyListResponse());

    renderDetail();

    // Wait a tick to let any potential effect fire.
    await waitFor(() => {
      expect(screen.getByText('Loading risk...')).toBeInTheDocument();
    });

    // No fetchWorkflowRuns call should have been made — the query is disabled.
    expect(workflowApi.fetchWorkflowRuns).not.toHaveBeenCalled();
  });

  it('F-1/F-4: plan resolves after loading → only plan-scoped fetch occurs, not a global one', async () => {
    // Phase 1: plan is loading — no fetch should happen.
    planLoadingMock = true;
    activePlanMock = null;

    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeEmptyListResponse());

    const { rerender, queryClient } = renderDetail();

    // No fetch during loading.
    await waitFor(() => {
      expect(screen.getByText('Loading risk...')).toBeInTheDocument();
    });
    expect(workflowApi.fetchWorkflowRuns).not.toHaveBeenCalled();

    // Phase 2: plan resolves to PLAN-B.
    vi.mocked(workflowApi.fetchWorkflowRuns).mockClear();
    planLoadingMock = false;
    activePlanMock = { code: 'PLAN-2026-W42', status: 'ACTIVE' };

    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
          <Routes>
            <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
            <Route path="/workflow-runs/:runId" element={<div>Run Detail Page</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Now the plan-scoped fetch should fire with PLAN-2026-W42.
    await waitFor(() => {
      expect(workflowApi.fetchWorkflowRuns).toHaveBeenCalledWith(1, 0, 'PLAN-2026-W42');
    });

    // No global (undefined planCode) fetch should have been made.
    const globalCallFound = vi.mocked(workflowApi.fetchWorkflowRuns).mock.calls.some(
      (call) => call[2] === undefined,
    );
    expect(globalCallFound).toBe(false);
  });

  it('F-1/F-4: Dashboard global cache does not become Risk Detail restoration data', async () => {
    // This test uses a real QueryClient to verify that a global workflow-runs
    // query (as Dashboard would issue) does NOT get consumed by Risk Detail
    // when the plan is unresolved.
    const queryClient = createQueryClient();

    // Pre-populate the cache with global data (as if Dashboard had fetched).
    queryClient.setQueryData(
      ['workflow-runs', null, 5, 0],
      {
        items: [
          {
            id: 'run-global-001',
            correlation_id: 'corr-global',
            state: 'COMPLETED',
            plan_id: 'plan-A',
            triggered_by: 'someone',
            error_code: null,
            error_detail: null,
            started_at: '2026-01-01T10:00:00Z',
            completed_at: '2026-01-01T10:05:00Z',
            created_at: '2026-01-01T10:00:00Z',
            updated_at: '2026-01-01T10:05:00Z',
          },
        ],
        limit: 5,
        offset: 0,
        total: 1,
      },
    );

    // Render with plan unresolved.
    planLoadingMock = true;
    activePlanMock = null;
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeEmptyListResponse());

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
          <Routes>
            <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
            <Route path="/workflow-runs/:runId" element={<div>Run Detail Page</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Wait for skeleton.
    await waitFor(() => {
      expect(screen.getByText('Loading risk...')).toBeInTheDocument();
    });

    // No workflow status should appear — the global cached run must not
    // be installed as restoration data.
    expect(screen.queryByTestId('workflow-status')).not.toBeInTheDocument();

    // No fetch should have been issued.
    expect(workflowApi.fetchWorkflowRuns).not.toHaveBeenCalled();
  });

  // -----------------------------------------------------------------------
  // F-4: PLAN-SWITCH — stale restoration data cannot overwrite current plan
  // -----------------------------------------------------------------------

  it('F-4: plan-A restoration data completing after plan switch to plan-B does not install plan-A run', async () => {
    // Phase 1: Start with plan A, no existing run.
    planLoadingMock = false;
    activePlanMock = { code: 'PLAN-2026-W31', status: 'ACTIVE' };

    // Make the restoration query hang so we can change the plan before it resolves.
    let resolveRestoration!: (value: WorkflowRunListResponse) => void;
    vi.mocked(workflowApi.fetchWorkflowRuns).mockImplementation(
      () => new Promise((resolve) => { resolveRestoration = resolve; }),
    );

    const { rerender, queryClient } = renderDetail();

    // Wait for the plan-A restoration query to be issued.
    await waitFor(() => {
      expect(workflowApi.fetchWorkflowRuns).toHaveBeenCalledWith(1, 0, 'PLAN-2026-W31');
    });

    // Phase 2: Plan changes to plan B.
    vi.mocked(workflowApi.fetchWorkflowRuns).mockClear();
    // Now set up a normal mock for plan-B's query.
    vi.mocked(workflowApi.fetchWorkflowRuns).mockResolvedValue(makeEmptyListResponse());

    activePlanMock = { code: 'PLAN-2026-W42', status: 'ACTIVE' };
    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
          <Routes>
            <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
            <Route path="/workflow-runs/:runId" element={<div>Run Detail Page</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Wait for plan-B query to fire.
    await waitFor(() => {
      expect(workflowApi.fetchWorkflowRuns).toHaveBeenCalledWith(1, 0, 'PLAN-2026-W42');
    });

    // Phase 3: The stale plan-A restoration resolves with a run from plan A.
    await act(async () => {
      resolveRestoration(makeListWithRun('run-plan-A-stale', 'COMPLETED'));
    });

    // Phase 4: The stale plan-A run must NOT be installed.
    // No workflow status should appear for the stale run.
    await waitFor(() => {
      expect(screen.queryByTestId('workflow-status')).not.toBeInTheDocument();
    });

    // Start button should be available for plan B (no existing run).
    await waitFor(() => {
      expect(screen.getByTestId('start-workflow-button')).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // F-5: RESTORATION ERROR FAILS CLOSED
  // -----------------------------------------------------------------------

  it('F-5: restoration query hard-fails → Start remains unavailable and error is visible', async () => {
    planLoadingMock = false;
    activePlanMock = { code: 'PLAN-2026-W31', status: 'ACTIVE' };

    // Make the restoration query reject.
    vi.mocked(workflowApi.fetchWorkflowRuns).mockRejectedValue(
      new Error('Network error'),
    );

    renderDetail();

    // The restoration error should be visible (retry:1 in hook adds delay).
    await waitFor(() => {
      expect(screen.getByTestId('restoration-error')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Start must NOT be available.
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();

    // No raw error detail leakage.
    expect(screen.queryByText('Network error')).not.toBeInTheDocument();
  });

  it('F-5: restoration error shows safe user-facing message and retry button', async () => {
    planLoadingMock = false;
    activePlanMock = { code: 'PLAN-2026-W31', status: 'ACTIVE' };

    vi.mocked(workflowApi.fetchWorkflowRuns).mockRejectedValue(
      new Error('Internal server error'),
    );

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('restoration-error')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Safe message is visible.
    expect(screen.getByTestId('restoration-error')).toHaveTextContent(
      /Couldn.*check for an existing AI analysis/,
    );
    // Retry button is visible.
    expect(screen.getByTestId('restoration-retry')).toBeInTheDocument();
  });

  it('F-5: restoration retry → refetch succeeds with zero runs → Start becomes available', async () => {
    planLoadingMock = false;
    activePlanMock = { code: 'PLAN-2026-W31', status: 'ACTIVE' };

    // Hook has retry:1, so the initial attempt AND the automatic retry must
    // both fail before isError becomes true. Then the user-initiated refetch
    // (third call) succeeds with an empty list.
    vi.mocked(workflowApi.fetchWorkflowRuns)
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce(makeEmptyListResponse());

    renderDetail();

    // Error appears (after initial + retry both fail).
    await waitFor(() => {
      expect(screen.getByTestId('restoration-error')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Start not available during error.
    expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();

    // Click retry.
    await act(async () => {
      const retryButton = screen.getByTestId('restoration-retry');
      await userEvent.click(retryButton);
    });

    // After successful refetch, Start should become available.
    await waitFor(() => {
      expect(screen.getByTestId('start-workflow-button')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Error should be gone.
    expect(screen.queryByTestId('restoration-error')).not.toBeInTheDocument();
  });

  it('F-5: restoration retry → refetch succeeds with existing run → Start stays unavailable', async () => {
    planLoadingMock = false;
    activePlanMock = { code: 'PLAN-2026-W31', status: 'ACTIVE' };

    const runId = 'run-restored-001';

    // Hook has retry:1, so the initial attempt AND the automatic retry must
    // both fail before isError becomes true. Then the user-initiated refetch
    // (third call) succeeds with a completed run.
    vi.mocked(workflowApi.fetchWorkflowRuns)
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce(makeListWithRun(runId, 'COMPLETED'));

    vi.mocked(workflowApi.fetchWorkflowRun).mockResolvedValue(
      makeCompletedRunWithRec('RISK-001', runId),
    );

    renderDetail();

    // Error appears (after initial + retry both fail).
    await waitFor(() => {
      expect(screen.getByTestId('restoration-error')).toBeInTheDocument();
    }, { timeout: 5000 });

    // Click retry.
    await act(async () => {
      const retryButton = screen.getByTestId('restoration-retry');
      await userEvent.click(retryButton);
    });

    // After refetch finds existing run, Start should NOT appear.
    await waitFor(() => {
      expect(screen.queryByTestId('start-workflow-button')).not.toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('F-5: no recommendation from unrelated/global data is shown during restoration error', async () => {
    planLoadingMock = false;
    activePlanMock = { code: 'PLAN-2026-W31', status: 'ACTIVE' };

    vi.mocked(workflowApi.fetchWorkflowRuns).mockRejectedValue(
      new Error('Server error'),
    );

    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId('restoration-error')).toBeInTheDocument();
    }, { timeout: 5000 });

    // No recommendation panel should appear.
    expect(screen.queryByTestId('recommendation-panel')).not.toBeInTheDocument();
    // No workflow status.
    expect(screen.queryByTestId('workflow-status')).not.toBeInTheDocument();
  });
});
