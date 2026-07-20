import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { RiskList } from '../RiskList';
import type { RiskRecordWithId } from '@/lib/risks-api';

const mockRisks: RiskRecordWithId[] = [
  {
    risk_id: 'RISK-001',
    component_code: 'CTRL-X4',
    component_name: 'Control Module X4',
    affected_wo_code: 'WO-001',
    required: '20.0000',
    available: '12.0000',
    confirmed_early: '0.0000',
    confirmed_late: '0.0000',
    shortage: '8.0000',
    severity: 'CRITICAL',
    has_approved_alternative: false,
    has_proposed_alternative: false,
    need_date: '2026-07-28',
    plan_code: 'PLAN-2026-W31',
  },
  {
    risk_id: 'RISK-002',
    component_code: 'PUMP-A1',
    component_name: 'Hydraulic Pump A1',
    affected_wo_code: 'WO-002',
    required: '15.0000',
    available: '9.0000',
    confirmed_early: '0.0000',
    confirmed_late: '0.0000',
    shortage: '6.0000',
    severity: 'HIGH',
    has_approved_alternative: false,
    has_proposed_alternative: false,
    need_date: '2026-07-30',
    plan_code: 'PLAN-2026-W31',
  },
];

const defaultProps = {
  risks: mockRisks,
  isLoading: false,
  isError: false,
  error: null,
  onRetry: () => {},
  totalCount: 2,
  visibleCount: 2,
};

function renderWithRouter(ui: React.ReactElement) {
  return render(ui, { wrapper: MemoryRouter });
}

describe('RiskList', () => {
  it('renders risk count', () => {
    renderWithRouter(<RiskList {...defaultProps} />);
    expect(screen.getByTestId('risk-count')).toHaveTextContent('Showing 2 of 2 risks');
  });

  it('renders all risk rows', () => {
    renderWithRouter(<RiskList {...defaultProps} />);
    expect(screen.getByText('RISK-001')).toBeInTheDocument();
    expect(screen.getByText('RISK-002')).toBeInTheDocument();
    expect(screen.getByText('CTRL-X4')).toBeInTheDocument();
    expect(screen.getByText('PUMP-A1')).toBeInTheDocument();
  });

  it('renders severity badges', () => {
    renderWithRouter(<RiskList {...defaultProps} />);
    const badges = screen.getAllByTestId('severity-badge');
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveTextContent('CRITICAL');
    expect(badges[1]).toHaveTextContent('HIGH');
  });

  it('shows loading skeletons when isLoading', () => {
    renderWithRouter(<RiskList {...defaultProps} isLoading={true} />);
    expect(screen.getByTestId('risk-list-loading')).toBeInTheDocument();
  });

  it('shows error state with retry button when isError', () => {
    renderWithRouter(<RiskList {...defaultProps} isError={true} error={new Error('Network error')} />);
    expect(screen.getByTestId('risk-list-error')).toBeInTheDocument();
    expect(screen.getByTestId('retry-risks')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('shows empty state when totalCount is 0', () => {
    renderWithRouter(<RiskList {...defaultProps} risks={[]} totalCount={0} visibleCount={0} />);
    expect(screen.getByTestId('risk-list-empty')).toBeInTheDocument();
    expect(screen.getByText('No risks calculated')).toBeInTheDocument();
  });

  it('shows filtered-empty state when visibleCount is 0 but totalCount > 0', () => {
    renderWithRouter(<RiskList {...defaultProps} risks={[]} totalCount={5} visibleCount={0} />);
    expect(screen.getByTestId('risk-list-filtered-empty')).toBeInTheDocument();
    expect(screen.getByText('No risks match the selected filters')).toBeInTheDocument();
  });

  it('renders table headers', () => {
    renderWithRouter(<RiskList {...defaultProps} />);
    expect(screen.getByText('Severity')).toBeInTheDocument();
    expect(screen.getByText('Risk ID')).toBeInTheDocument();
    expect(screen.getByText('Component Code')).toBeInTheDocument();
    expect(screen.getByText('Component Name')).toBeInTheDocument();
    expect(screen.getByText('Shortage')).toBeInTheDocument();
    expect(screen.getByText('Available')).toBeInTheDocument();
    expect(screen.getByText('Required')).toBeInTheDocument();
  });

  it('formats quantity values using formatQuantity', () => {
    const risksWithDecimals: RiskRecordWithId[] = [
      {
        risk_id: 'RISK-001',
        component_code: 'TEST-01',
        component_name: 'Test Component',
        affected_wo_code: 'WO-001',
        required: '1234567.8900',
        available: '100.0000',
        confirmed_early: '0.0000',
        confirmed_late: '0.0000',
        shortage: '45.6789',
        severity: 'CRITICAL',
        has_approved_alternative: false,
        has_proposed_alternative: false,
        need_date: '2026-07-28',
        plan_code: 'PLAN-2026-W31',
      },
    ];

    renderWithRouter(
      <RiskList
        risks={risksWithDecimals}
        isLoading={false}
        isError={false}
        error={null}
        onRetry={() => {}}
        totalCount={1}
        visibleCount={1}
      />
    );

    // Verify formatQuantity is applied to all three quantity columns
    expect(screen.getByText('1,234,567.89')).toBeInTheDocument(); // required
    expect(screen.getByText('100')).toBeInTheDocument(); // available
    expect(screen.getByText('45.68')).toBeInTheDocument(); // shortage
  });
});
