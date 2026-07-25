import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidencePanel } from '../EvidencePanel';
import type { RiskRecordWithId } from '@/lib/risks-api';
import { createRisk, createMutatedRisk } from '@/test/fixtures/risk-contract';

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

/**
 * AT-005 data-fidelity contract tests.
 * Mutated fixture values must appear exactly; no recalculation.
 */
describe('EvidencePanel — AT-005 data fidelity (non-canonical mutations)', () => {
  it('renders canonical fixture values', () => {
    const risk = createRisk();
    render(<EvidencePanel risk={risk} />);

    expect(screen.getByText('20')).toBeInTheDocument(); // required
    expect(screen.getByText('12')).toBeInTheDocument(); // available
    expect(screen.getByText('8')).toBeInTheDocument(); // shortage
  });

  it('renders unmistakably non-canonical mutated values exactly (AT-005)', () => {
    const mutated = createMutatedRisk();
    render(<EvidencePanel risk={mutated} />);

    // Non-canonical values from fixture must be rendered verbatim (via formatQuantity)
    // formatQuantity strips trailing zeros and rounds to 2 decimals:
    // '99.0000' → '99', '61.7500' → '61.75', '37.2500' → '37.25'
    expect(screen.getByText('99')).toBeInTheDocument(); // required
    expect(screen.getByText('61.75')).toBeInTheDocument(); // available
    expect(screen.getByText('37.25')).toBeInTheDocument(); // shortage (key AT-005 proof)
    // Descriptive formula label remains (not a calculation)
    expect(screen.getByText(/Shortage = max\(0, required − available − confirmed_early\)/)).toBeInTheDocument();
  });

  it('does not recalculate shortage from mutated inputs', () => {
    // Use values where formatQuantity output is unambiguous (≤2 decimals)
    // mutated shortage='50.5000' → formatted '50.5'; required='30.0000'→'30'; available='10.0000'→'10'
    // If frontend recalculated: 30 - 10 - 0 = 20, NOT 50.5
    const mutated = createMutatedRisk({ required: '30.0000', available: '10.0000', confirmed_early: '0.0000', shortage: '50.5000' });
    render(<EvidencePanel risk={mutated} />);

    // Must show the supplied shortage, not computed 20
    expect(screen.getByText('50.5')).toBeInTheDocument();
    expect(screen.queryByText('20')).not.toBeInTheDocument();
  });
});
