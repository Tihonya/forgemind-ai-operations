import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import SupplyRiskDetail from '../supply-risk-detail';

// Mock hooks
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
      {
        risk_id: 'RISK-001',
        component_code: 'COMP-001',
        component_name: 'Widget A',
        affected_wo_code: 'WO-001',
        required: '100.0000',
        available: '50.0000',
        confirmed_early: '10.0000',
        confirmed_late: '5.0000',
        shortage: '40.0000',
        severity: 'CRITICAL',
        has_approved_alternative: false,
        has_proposed_alternative: false,
        need_date: '2024-03-01',
        plan_code: 'PLAN-001',
      },
    ],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/hooks/useRiskDetail', () => ({
  useRiskDetail: ({ riskId }: { riskId: string }) => {
    if (riskId === 'RISK-001') {
      return {
        risk: {
          risk_id: 'RISK-001',
          component_code: 'COMP-001',
          component_name: 'Widget A',
          affected_wo_code: 'WO-001',
          required: '100.0000',
          available: '50.0000',
          confirmed_early: '10.0000',
          confirmed_late: '5.0000',
          shortage: '40.0000',
          severity: 'CRITICAL',
          has_approved_alternative: false,
          has_proposed_alternative: false,
          need_date: '2024-03-01',
          plan_code: 'PLAN-001',
        },
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

describe('SupplyRiskDetail', () => {
  it('renders risk detail for valid riskId', () => {
    render(
      <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
        <Routes>
          <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
        </Routes>
      </MemoryRouter>
    );

    // RISK-001 appears in breadcrumb and in risk summary
    const riskIdElements = screen.getAllByText('RISK-001');
    expect(riskIdElements.length).toBeGreaterThanOrEqual(2);
    // CRITICAL severity badge is rendered
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
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
    render(
      <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
        <Routes>
          <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Supply Risks')).toBeInTheDocument();
    // RISK-001 appears in breadcrumb
    const riskIdElements = screen.getAllByText('RISK-001');
    expect(riskIdElements.length).toBeGreaterThan(0);
  });

  it('does not display back button (removed in WP-3.7)', () => {
    render(
      <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
        <Routes>
          <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
        </Routes>
      </MemoryRouter>
    );

    // Back button was removed in WP-3.7; breadcrumb navigation is used instead
    expect(screen.queryByText(/Back to Supply Risks/i)).not.toBeInTheDocument();
  });

  it('does not implement whole-row navigation (no onClick on table rows)', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/supply-risk/RISK-001']}>
        <Routes>
          <Route path="/supply-risk/:riskId" element={<SupplyRiskDetail />} />
        </Routes>
      </MemoryRouter>
    );

    // Check that no table rows have onClick handlers (whole-row navigation forbidden)
    const rows = container.querySelectorAll('tr');
    rows.forEach((row) => {
      expect(row.getAttribute('onclick')).toBeNull();
      expect(row.style.cursor).not.toBe('pointer');
    });
  });
});
