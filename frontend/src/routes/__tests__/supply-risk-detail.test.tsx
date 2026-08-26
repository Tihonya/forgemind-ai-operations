import { beforeEach } from 'vitest'
import i18n from '@/i18n'
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import SupplyRiskDetail from '../supply-risk-detail';
import { createRisk, createMutatedRisk } from '@/test/fixtures/risk-contract';

// WP-UX-UA-03: pin the active locale to English so behavior assertions
// against English copy stay stable after the Ukrainian-first migration.
beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})


// Mock hooks with fixture support for AT-005
vi.mock('@/hooks/useActivePlan', () => ({
  useActivePlan: () => ({
    activePlan: { code: 'PLAN-001', status: 'ACTIVE' },
    isLoading: false,
    error: null,
  }),
}));

vi.mock('@/hooks/useRisks', () => ({
  useRisks: () => ({
    risks: [
      createRisk({ risk_id: 'RISK-001', component_name: 'Widget A', plan_code: 'PLAN-001' }),
    ],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

// Mock auth context (WP-REC-03G: component now uses useAuth for role visibility)
vi.mock('@/contexts/auth.context', () => ({
  useAuth: () => ({
    user: { id: 'u1', username: 'pm-user', roles: ['production_manager'] },
    isAuthenticated: true,
    isLoading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  }),
}));

// Mock useQueryClient (WP-REC-03G: component uses it to invalidate
// the workflow-run query after retry success).
vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: () => ({
      invalidateQueries: vi.fn(),
    }),
  };
});

// Mock useWorkflowRuns (WP-UX-02: component now uses this for plan-scoped
// latest-run restoration). Returns no existing run by default.
vi.mock('@/hooks/use-workflow-runs', () => ({
  useWorkflowRuns: () => ({
    runs: [],
    total: 0,
    isLoading: false,
    isError: false,
    error: null,
    queriedPlanCode: 'PLAN-001',
    isDisabled: false,
    refetch: vi.fn(),
  }),
}));

// Mock workflow hooks (WP-REC-03G: component now uses these for start/retry/polling)
vi.mock('@/hooks/use-workflow-run', () => ({
  useWorkflowRun: () => ({
    run: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/hooks/use-workflow-start', () => ({
  useWorkflowStart: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
    reset: vi.fn(),
  }),
}));

vi.mock('@/hooks/use-workflow-retry', () => ({
  useWorkflowRetry: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
    reset: vi.fn(),
  }),
}));

// Mock approval-creation mutation (WP-UX-UA-05: the route now wires guided
// approval creation from the recommendation surface).
vi.mock('@/hooks/use-approval-create', () => ({
  useApprovalCreate: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
    reset: vi.fn(),
  }),
}));

vi.mock('@/hooks/useRiskDetail', () => ({
  useRiskDetail: ({ riskId }: { riskId: string }) => {
    if (riskId === 'RISK-001') {
      return {
        risk: createRisk({ risk_id: 'RISK-001', component_name: 'Widget A', plan_code: 'PLAN-001' }),
        riskFound: true,
        component: { code: 'COMP-001', name: 'Widget A', unit: 'EA', alternatives: [] },
        inventory: { component_code: 'COMP-001', component_name: 'Widget A', unit: 'EA', balances: [], reservations: [] },
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
      };
    }
    if (riskId === 'RISK-MUT') {
      return {
        risk: createMutatedRisk({ risk_id: 'RISK-MUT' }),
        riskFound: true,
        component: null,
        inventory: null,
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
      };
    }
    return {
      risk: null,
      riskFound: false,
      component: null,
      inventory: null,
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
    };
  },
}));

function renderDetail(riskId = 'RISK-001') {
  return render(
    <MemoryRouter initialEntries={[`/supply-risk/${riskId}`]}>
      <Routes>
        <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('SupplyRiskDetail', () => {
  it('renders risk detail for valid riskId', () => {
    renderDetail('RISK-001');

    // RISK-001 appears in breadcrumb and in risk summary
    const riskIdElements = screen.getAllByText('RISK-001');
    expect(riskIdElements.length).toBeGreaterThanOrEqual(2);
    // Critical severity badge is rendered (localized English label;
    // machine code preserved via data-code below)
    expect(screen.getByText('Critical')).toBeInTheDocument();
  });

  it('shows not-found screen for invalid riskId', () => {
    render(
      <MemoryRouter initialEntries={['/supply-risk/RISK-999']}>
        <Routes>
          <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
        </Routes>
      </MemoryRouter>
    );

    // "Risk not found" appears in breadcrumb and in error message
    const notFoundElements = screen.getAllByText(/Risk not found/i);
    expect(notFoundElements.length).toBeGreaterThan(0);
    expect(screen.getByText(/RISK-999/i)).toBeInTheDocument();
  });

  it('displays breadcrumb navigation', () => {
    renderDetail('RISK-001');

    expect(screen.getByText('Supply Risks')).toBeInTheDocument();
    // RISK-001 appears in breadcrumb
    const riskIdElements = screen.getAllByText('RISK-001');
    expect(riskIdElements.length).toBeGreaterThan(0);
  });

  it('does not display back button (removed in WP-3.7)', () => {
    renderDetail('RISK-001');

    // Back button was removed in WP-3.7; breadcrumb navigation is used instead
    expect(screen.queryByText(/Back to Supply Risks/i)).not.toBeInTheDocument();
  });

  it('does not implement whole-row navigation (no onClick on table rows)', () => {
    const { container } = renderDetail('RISK-001');

    // Check that no table rows have onClick handlers (whole-row navigation forbidden)
    const rows = container.querySelectorAll('tr');
    rows.forEach((row) => {
      expect(row.getAttribute('onclick')).toBeNull();
      expect(row.style.cursor).not.toBe('pointer');
    });
  });

  // AT-005: detail renders mutated risk values from fixture
  it('renders mutated evidence values when non-canonical risk supplied (AT-005)', () => {
    renderDetail('RISK-MUT');

    // Mutated risk_id (multiple elements: breadcrumb, RiskSummary, h1)
    const riskIdElements = screen.getAllByText('RISK-MUT');
    expect(riskIdElements.length).toBeGreaterThanOrEqual(2);
    // Mutated component code and name via RiskSummary
    expect(screen.getByText('MUT-TEST')).toBeInTheDocument();
    expect(screen.getByText(/Mutated Test Component/)).toBeInTheDocument();
    // Mutated severity
    expect(screen.getByText('Low')).toBeInTheDocument();
    // Mutated work order
    expect(screen.getByText('WO-TEST-999')).toBeInTheDocument();
    // Evidence panel shows mutated values (formatQuantity strips trailing zeros)
    // Note: both RiskSummary and EvidencePanel display shortage, so use getAllByText.
    expect(screen.getByText('99')).toBeInTheDocument(); // required (EvidencePanel only)
    expect(screen.getByText('61.75')).toBeInTheDocument(); // available (EvidencePanel only)
    const shortageElements = screen.getAllByText('37.25');
    expect(shortageElements.length).toBeGreaterThanOrEqual(2); // RiskSummary + EvidencePanel
    // Descriptive formula label remains
    expect(screen.getByText(/Shortage = max\(0, required − available − confirmed_early\)/)).toBeInTheDocument();
  });
});
