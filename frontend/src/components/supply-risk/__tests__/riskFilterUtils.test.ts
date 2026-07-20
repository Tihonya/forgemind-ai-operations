import { describe, expect, it } from 'vitest';

import type { RiskRecordWithId } from '@/lib/risks-api';
import { filterRisks, sortRisksBySeverity } from '../riskFilterUtils';

function makeRisk(overrides: Partial<RiskRecordWithId> = {}): RiskRecordWithId {
  return {
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
    ...overrides,
  };
}

describe('sortRisksBySeverity', () => {
  it('sorts CRITICAL before HIGH before MEDIUM before LOW', () => {
    const risks = [
      makeRisk({ risk_id: 'RISK-001', severity: 'LOW' }),
      makeRisk({ risk_id: 'RISK-002', severity: 'CRITICAL' }),
      makeRisk({ risk_id: 'RISK-003', severity: 'MEDIUM' }),
      makeRisk({ risk_id: 'RISK-004', severity: 'HIGH' }),
    ];

    const sorted = sortRisksBySeverity(risks);

    expect(sorted[0].severity).toBe('CRITICAL');
    expect(sorted[1].severity).toBe('HIGH');
    expect(sorted[2].severity).toBe('MEDIUM');
    expect(sorted[3].severity).toBe('LOW');
  });

  it('sorts by risk_id ascending within same severity (stable secondary ordering)', () => {
    const risks = [
      makeRisk({ risk_id: 'RISK-003', severity: 'HIGH' }),
      makeRisk({ risk_id: 'RISK-001', severity: 'HIGH' }),
      makeRisk({ risk_id: 'RISK-002', severity: 'HIGH' }),
    ];

    const sorted = sortRisksBySeverity(risks);

    expect(sorted[0].risk_id).toBe('RISK-001');
    expect(sorted[1].risk_id).toBe('RISK-002');
    expect(sorted[2].risk_id).toBe('RISK-003');
  });

  it('handles mixed severities with stable secondary ordering', () => {
    const risks = [
      makeRisk({ risk_id: 'RISK-003', severity: 'CRITICAL' }),
      makeRisk({ risk_id: 'RISK-001', severity: 'HIGH' }),
      makeRisk({ risk_id: 'RISK-002', severity: 'CRITICAL' }),
      makeRisk({ risk_id: 'RISK-004', severity: 'HIGH' }),
    ];

    const sorted = sortRisksBySeverity(risks);

    // CRITICAL first, sorted by risk_id
    expect(sorted[0].risk_id).toBe('RISK-002');
    expect(sorted[1].risk_id).toBe('RISK-003');
    // HIGH second, sorted by risk_id
    expect(sorted[2].risk_id).toBe('RISK-001');
    expect(sorted[3].risk_id).toBe('RISK-004');
  });

  it('treats unknown severity as lowest priority (after LOW)', () => {
    const risks = [
      makeRisk({ risk_id: 'RISK-001', severity: 'UNKNOWN' }),
      makeRisk({ risk_id: 'RISK-002', severity: 'LOW' }),
      makeRisk({ risk_id: 'RISK-003', severity: 'MEDIUM' }),
    ];

    const sorted = sortRisksBySeverity(risks);

    expect(sorted[0].severity).toBe('MEDIUM');
    expect(sorted[1].severity).toBe('LOW');
    expect(sorted[2].severity).toBe('UNKNOWN');
  });

  it('does not mutate the input array', () => {
    const risks = [
      makeRisk({ risk_id: 'RISK-002', severity: 'HIGH' }),
      makeRisk({ risk_id: 'RISK-001', severity: 'CRITICAL' }),
    ];

    const sorted = sortRisksBySeverity(risks);

    expect(sorted).not.toBe(risks);
    expect(risks[0].risk_id).toBe('RISK-002');
    expect(sorted[0].risk_id).toBe('RISK-001');
  });

  it('returns empty array for empty input', () => {
    expect(sortRisksBySeverity([])).toEqual([]);
  });
});

describe('filterRisks', () => {
  const risks = [
    makeRisk({ risk_id: 'RISK-001', severity: 'CRITICAL', component_code: 'CTRL-X4' }),
    makeRisk({ risk_id: 'RISK-002', severity: 'HIGH', component_code: 'PUMP-A1' }),
    makeRisk({ risk_id: 'RISK-003', severity: 'MEDIUM', component_code: 'ctrl-x4-variant' }),
    makeRisk({ risk_id: 'RISK-004', severity: 'LOW', component_code: 'VALVE-B2' }),
  ];

  it('returns all risks when no severities selected (no severity filtering)', () => {
    const result = filterRisks(risks, [], '');
    expect(result).toHaveLength(4);
  });

  it('filters by single severity', () => {
    const result = filterRisks(risks, ['CRITICAL'], '');
    expect(result).toHaveLength(1);
    expect(result[0].risk_id).toBe('RISK-001');
  });

  it('filters by multiple severities', () => {
    const result = filterRisks(risks, ['CRITICAL', 'HIGH'], '');
    expect(result).toHaveLength(2);
    expect(result.map((r) => r.risk_id)).toEqual(['RISK-001', 'RISK-002']);
  });

  it('filters by component code (case-insensitive substring)', () => {
    const result = filterRisks(risks, [], 'ctrl');
    expect(result).toHaveLength(2);
    expect(result.map((r) => r.risk_id)).toEqual(['RISK-001', 'RISK-003']);
  });

  it('component code filter is case-insensitive', () => {
    const result = filterRisks(risks, [], 'CTRL-X4');
    expect(result).toHaveLength(2);
  });

  it('combines severity and component code filters (AND logic)', () => {
    const result = filterRisks(risks, ['CRITICAL'], 'CTRL');
    expect(result).toHaveLength(1);
    expect(result[0].risk_id).toBe('RISK-001');
  });

  it('returns empty when combined filters match nothing', () => {
    const result = filterRisks(risks, ['CRITICAL'], 'VALVE');
    expect(result).toHaveLength(0);
  });

  it('trims whitespace from component code filter', () => {
    const result = filterRisks(risks, [], '  CTRL  ');
    expect(result).toHaveLength(2);
  });

  it('empty string component code filter matches all', () => {
    const result = filterRisks(risks, [], '');
    expect(result).toHaveLength(4);
  });

  it('filter reset (empty arrays + empty string) returns all', () => {
    const result = filterRisks(risks, [], '');
    expect(result).toHaveLength(4);
  });
});
