import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { useRiskDetail } from './useRiskDetail';
import * as api from '@/lib/risk-detail-api';
import type { RiskRecordWithId } from '@/lib/risks-api';
import { createRisk, createMutatedRisk } from '@/test/fixtures/risk-contract';

vi.mock('@/lib/risk-detail-api');

const mockedApi = vi.mocked(api);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const mockRisk: RiskRecordWithId = createRisk({
  risk_id: 'RISK-001',
  component_code: 'COMP-1',
  component_name: 'Component 1',
  affected_wo_code: 'WO-1',
  plan_code: 'PLAN-1',
});

describe('useRiskDetail', () => {
  it('returns risk=null when riskId not found', () => {
    const risks: RiskRecordWithId[] = [mockRisk];

    const { result } = renderHook(() => useRiskDetail({ risks, riskId: 'RISK-999' }), {
      wrapper: createWrapper(),
    });

    expect(result.current.risk).toBeNull();
    expect(result.current.riskFound).toBe(false);
  });

  it('returns risk when riskId matches', () => {
    const risks: RiskRecordWithId[] = [mockRisk];

    const { result } = renderHook(() => useRiskDetail({ risks, riskId: 'RISK-001' }), {
      wrapper: createWrapper(),
    });

    expect(result.current.risk).toEqual(mockRisk);
    expect(result.current.riskFound).toBe(true);
  });

  it('fetches component detail when risk is found', async () => {
    const risks: RiskRecordWithId[] = [mockRisk];

    mockedApi.fetchComponentDetail.mockResolvedValue({
      code: 'COMP-1',
      name: 'Component 1',
      unit: 'EA',
      alternatives: [],
    });

    const { result } = renderHook(() => useRiskDetail({ risks, riskId: 'RISK-001' }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.component).not.toBeNull());
    expect(result.current.component?.code).toBe('COMP-1');
  });

  it('handles component fetch error', async () => {
    const risks: RiskRecordWithId[] = [mockRisk];

    mockedApi.fetchComponentDetail.mockRejectedValue(new Error('Not found'));

    const { result } = renderHook(() => useRiskDetail({ risks, riskId: 'RISK-001' }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.componentError).not.toBeNull());
    expect(result.current.componentError?.message).toBe('Not found');
  });

  it('provides refetch functions for each panel', () => {
    const risks: RiskRecordWithId[] = [mockRisk];

    const { result } = renderHook(() => useRiskDetail({ risks, riskId: 'RISK-001' }), {
      wrapper: createWrapper(),
    });

    expect(result.current.refetchComponent).toBeInstanceOf(Function);
    expect(result.current.refetchInventory).toBeInstanceOf(Function);
    expect(result.current.refetchPurchaseOrders).toBeInstanceOf(Function);
    expect(result.current.refetchProductionOrder).toBeInstanceOf(Function);
    expect(result.current.refetchProductionPlan).toBeInstanceOf(Function);
  });
});

/**
 * AT-005: risk list input to hook drives the returned risk (data fidelity).
 */
describe('useRiskDetail — AT-005 data fidelity (risk from list)', () => {
  it('returns the mutated risk record when supplied in risks list (non-canonical values)', () => {
    const mutated = createMutatedRisk({ risk_id: 'RISK-MUT' });
    const risks: RiskRecordWithId[] = [mutated];

    const { result } = renderHook(() => useRiskDetail({ risks, riskId: 'RISK-MUT' }), {
      wrapper: createWrapper(),
    });

    expect(result.current.risk).not.toBeNull();
    expect(result.current.risk?.plan_code).toBe('PLAN-TEST-MUTATED');
    expect(result.current.risk?.component_name).toBe('Mutated Test Component');
    expect(result.current.risk?.shortage).toBe('37.2500');
    expect(result.current.risk?.severity).toBe('LOW');
    expect(result.current.riskFound).toBe(true);
  });
});
