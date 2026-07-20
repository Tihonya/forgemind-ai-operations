import { describe, it, expect } from 'vitest';
import { aggregateRiskSummary } from '@/lib/risks-api';
import type { RiskRecordWithId } from '@/lib/risks-api';

describe('aggregateRiskSummary', () => {
  it('returns zero counts for empty risk list', () => {
    const risks: RiskRecordWithId[] = [];
    const summary = aggregateRiskSummary(risks);
    expect(summary).toEqual({
      total: 0,
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
    });
  });

  it('counts risks by severity correctly', () => {
    const risks: RiskRecordWithId[] = [
      createRisk('RISK-001', 'CRITICAL'),
      createRisk('RISK-002', 'CRITICAL'),
      createRisk('RISK-003', 'HIGH'),
      createRisk('RISK-004', 'MEDIUM'),
      createRisk('RISK-005', 'LOW'),
    ];
    const summary = aggregateRiskSummary(risks);
    expect(summary).toEqual({
      total: 5,
      critical: 2,
      high: 1,
      medium: 1,
      low: 1,
    });
  });

  it('ignores unknown severity values without crashing', () => {
    const risks: RiskRecordWithId[] = [
      createRisk('RISK-001', 'CRITICAL'),
      createRisk('RISK-002', 'UNKNOWN'),
      createRisk('RISK-003', 'INVALID'),
      createRisk('RISK-004', ''),
    ];
    const summary = aggregateRiskSummary(risks);
    expect(summary).toEqual({
      total: 1,
      critical: 1,
      high: 0,
      medium: 0,
      low: 0,
    });
  });

  it('handles mixed valid and invalid severities', () => {
    const risks: RiskRecordWithId[] = [
      createRisk('RISK-001', 'CRITICAL'),
      createRisk('RISK-002', 'HIGH'),
      createRisk('RISK-003', 'BOGUS'),
      createRisk('RISK-004', 'MEDIUM'),
    ];
    const summary = aggregateRiskSummary(risks);
    expect(summary).toEqual({
      total: 3,
      critical: 1,
      high: 1,
      medium: 1,
      low: 0,
    });
  });

  it('counts only known severities in total', () => {
    const risks: RiskRecordWithId[] = [
      createRisk('RISK-001', 'CRITICAL'),
      createRisk('RISK-002', 'UNKNOWN'),
      createRisk('RISK-003', 'HIGH'),
    ];
    const summary = aggregateRiskSummary(risks);
    expect(summary.total).toBe(2); // Only CRITICAL and HIGH
  });
});

function createRisk(risk_id: string, severity: string): RiskRecordWithId {
  return {
    risk_id,
    component_code: 'COMP-001',
    component_name: 'Test Component',
    affected_wo_code: 'WO-001',
    required: '100.0000',
    available: '50.0000',
    confirmed_early: '0.0000',
    confirmed_late: '0.0000',
    shortage: '50.0000',
    severity,
    has_approved_alternative: false,
    has_proposed_alternative: false,
    need_date: '2025-02-15',
    plan_code: 'PLAN-001',
  };
}
