import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AwaitingDecisionWidget from '../AwaitingDecisionWidget';
import * as useApprovalRequestsModule from '@/hooks/use-approval-requests';
import type { ApprovalRequestResponse } from '@/lib/approval-api';

vi.mock('@/hooks/use-approval-requests');

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
            path="/approval-center"
            element={<div>Approval Center</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function createApproval(
  overrides: Partial<ApprovalRequestResponse> = {},
): ApprovalRequestResponse {
  return {
    id: 'apr-001',
    correlation_id: 'corr-001',
    recommendation_id: 'rec-001',
    workflow_run_id: 'run-001',
    risk_id: 'RISK-001',
    action_type: 'CREATE_PROCUREMENT_TASK',
    action_snapshot: {
      binding_version: 1,
      action_type: 'CREATE_PROCUREMENT_TASK',
      component_code: 'CTRL-X4',
      quantity: '8.0000',
      risk_id: 'RISK-001',
      workflow_run_id: 'run-001',
      recommendation_id: 'rec-001',
      title: 'Procure 8 units of CTRL-X4',
      rationale: 'Supplier has units arriving Aug 5',
    },
    binding_hash: 'hash-001',
    requested_by: 'user-001',
    requested_by_username: 'manager.demo',
    status: 'PENDING',
    decided_by: null,
    decided_by_username: null,
    decision_comment: null,
    requested_at: '2026-08-23T14:41:00Z',
    decided_at: null,
    ...overrides,
  };
}

/**
 * Mock return value for useApprovalRequests when the widget requests
 * status=PENDING with limit=1. The backend returns one item but the
 * exact count is in `total`.
 */
function mockPendingTotal(
  total: number,
  items: ApprovalRequestResponse[] = [],
) {
  vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
    requests: items,
    total,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  });
}

describe('AwaitingDecisionWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
      requests: [],
      total: 0,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByTestId('awaiting-decision-loading')).toBeInTheDocument();
  });

  it('renders error state', () => {
    vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
      requests: [],
      total: 0,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
      refetch: vi.fn(),
    });

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByTestId('awaiting-decision-error')).toBeInTheDocument();
    expect(
      screen.getByText('Unable to load approval requests'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('awaiting-decision-retry')).toBeInTheDocument();
  });

  it('renders zero-pending state truthfully when total is 0', () => {
    mockPendingTotal(0);

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByTestId('awaiting-decision-zero')).toBeInTheDocument();
    expect(screen.getByText('No decisions waiting')).toBeInTheDocument();
  });

  it('renders one pending approval from total', () => {
    const pending = createApproval({ status: 'PENDING' });
    mockPendingTotal(1, [pending]);

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByTestId('awaiting-decision-pending')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(
      screen.getByText('approval request waiting'),
    ).toBeInTheDocument();
  });

  it('displays exact backend total even when only one item is returned', () => {
    // The widget requests limit=1, so the backend returns one item
    // but total=73 — the widget must display 73, not 1.
    const pending = createApproval({ status: 'PENDING' });
    mockPendingTotal(73, [pending]);

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByTestId('awaiting-decision-pending')).toBeInTheDocument();
    expect(screen.getByText('73')).toBeInTheDocument();
    expect(
      screen.getByText('approval requests waiting'),
    ).toBeInTheDocument();
  });

  it('uses backend-filtered total, not client-side count of items', () => {
    // Even if the response includes non-PENDING items (shouldn't happen
    // with the filter, but the widget must still use total, not filter),
    // the displayed number must be the backend total.
    const pending = createApproval({ status: 'PENDING' });
    const approved = createApproval({
      id: 'apr-002',
      status: 'APPROVED',
    });
    mockPendingTotal(42, [pending, approved]);

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByTestId('awaiting-decision-pending')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('pluralizes correctly for total > 1', () => {
    mockPendingTotal(5);

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(
      screen.getByText('approval requests waiting'),
    ).toBeInTheDocument();
  });

  it('singularizes correctly for total === 1', () => {
    mockPendingTotal(1);

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(
      screen.getByText('approval request waiting'),
    ).toBeInTheDocument();
  });

  it('links to Approval Center', () => {
    mockPendingTotal(0);

    renderWithProviders(<AwaitingDecisionWidget />);
    const cta = screen.getByTestId('awaiting-decision-cta');
    expect(cta.closest('a')).toHaveAttribute('href', '/approval-center');
  });

  it('shows Approval Center link even when there are pending approvals', () => {
    mockPendingTotal(3);

    renderWithProviders(<AwaitingDecisionWidget />);
    const cta = screen.getByTestId('awaiting-decision-cta');
    expect(cta.closest('a')).toHaveAttribute('href', '/approval-center');
  });

  it('passes status=PENDING option to useApprovalRequests hook', () => {
    // Verify the widget calls useApprovalRequests with status=PENDING
    vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
      requests: [],
      total: 0,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<AwaitingDecisionWidget />);

    expect(
      useApprovalRequestsModule.useApprovalRequests,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'PENDING',
        limit: 1,
        offset: 0,
      }),
    );
  });
});
