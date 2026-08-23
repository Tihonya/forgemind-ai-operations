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

  it('renders zero-pending state truthfully', () => {
    const approved = createApproval({ status: 'APPROVED' });
    vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
      requests: [approved],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByTestId('awaiting-decision-zero')).toBeInTheDocument();
    expect(screen.getByText('No decisions waiting')).toBeInTheDocument();
  });

  it('renders one pending approval', () => {
    const pending = createApproval({ status: 'PENDING' });
    vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
      requests: [pending],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByTestId('awaiting-decision-pending')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(
      screen.getByText('approval request waiting'),
    ).toBeInTheDocument();
  });

  it('renders multiple pending approvals', () => {
    const pending1 = createApproval({
      id: 'apr-001',
      status: 'PENDING',
    });
    const pending2 = createApproval({
      id: 'apr-002',
      status: 'PENDING',
      risk_id: 'RISK-002',
    });
    const approved = createApproval({
      id: 'apr-003',
      status: 'APPROVED',
    });
    vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
      requests: [pending1, pending2, approved],
      total: 3,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<AwaitingDecisionWidget />);
    expect(screen.getByTestId('awaiting-decision-pending')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(
      screen.getByText('approval requests waiting'),
    ).toBeInTheDocument();
  });

  it('links to Approval Center', () => {
    vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
      requests: [],
      total: 0,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<AwaitingDecisionWidget />);
    const cta = screen.getByTestId('awaiting-decision-cta');
    expect(cta.closest('a')).toHaveAttribute('href', '/approval-center');
  });

  it('shows Approval Center link even when there are pending approvals', () => {
    const pending = createApproval({ status: 'PENDING' });
    vi.mocked(useApprovalRequestsModule.useApprovalRequests).mockReturnValue({
      requests: [pending],
      total: 1,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderWithProviders(<AwaitingDecisionWidget />);
    const cta = screen.getByTestId('awaiting-decision-cta');
    expect(cta.closest('a')).toHaveAttribute('href', '/approval-center');
  });
});
