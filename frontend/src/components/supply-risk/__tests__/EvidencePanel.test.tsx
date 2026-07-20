import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidencePanel } from '../EvidencePanel';
import type { RiskRecordWithId } from '@/lib/risks-api';

describe('EvidencePanel', () => {
  const mockRisk: RiskRecordWithId = {
    risk_id: 'RISK-001',
    component_code: 'COMP-001',
    component_name: 'Component 1',
    affected_wo_code: 'WO-001',
    required: '100.0000',
    available: '50.0000',
    confirmed_early: '10.0000',
    confirmed_late: '5.0000',
    shortage: '40.0000',
    severity: 'CRITICAL',
    has_approved_alternative: false,
    has_proposed_alternative: false,
    need_date: '2026-07-28',
    plan_code: 'PLAN-2026-W31',
  };

  it('displays all 5 quantity fields', () => {
    render(<EvidencePanel risk={mockRisk} />);

    expect(screen.getByText('Required')).toBeInTheDocument();
    expect(screen.getByText('Available')).toBeInTheDocument();
    expect(screen.getByText('Confirmed (early)')).toBeInTheDocument();
    expect(screen.getByText('Confirmed (late)')).toBeInTheDocument();
    expect(screen.getByText('Shortage')).toBeInTheDocument();
  });

  it('formats quantities correctly (WP-3.5 regression invariant)', () => {
    render(<EvidencePanel risk={mockRisk} />);

    // 100.0000 → 100
    // 50.0000 → 50
    // 10.0000 → 10
    // 5.0000 → 5
    // 40.0000 → 40
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
  });

  it('displays backend values as-is (no recalculation)', () => {
    const customRisk: RiskRecordWithId = {
      risk_id: 'RISK-002',
      component_code: 'COMP-002',
      component_name: 'Component 2',
      affected_wo_code: 'WO-002',
      required: '200.0000',
      available: '150.0000',
      confirmed_early: '30.0000',
      confirmed_late: '0.0000',
      shortage: '20.0000',
      severity: 'HIGH',
      has_approved_alternative: false,
      has_proposed_alternative: false,
      need_date: '2026-07-29',
      plan_code: 'PLAN-2026-W31',
    };

    render(<EvidencePanel risk={customRisk} />);

    // Should show backend values, not recalculated
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('150')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
  });
});
