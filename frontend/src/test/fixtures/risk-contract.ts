/**
 * Test-only fixtures for AT-005 data-fidelity contract tests.
 *
 * Provides canonical-shaped and unmistakably non-canonical mutated data
 * matching the backend API contracts (RiskRecordWithId etc.).
 *
 * DO NOT import from any production source files.
 * Only for use in __tests__ and test/ directories.
 */

import type { RiskRecordWithId, RiskSummary } from '@/lib/risks-api';

export type RiskOverrides = Partial<RiskRecordWithId>;

export function createRisk(overrides: RiskOverrides = {}): RiskRecordWithId {
  return {
    risk_id: 'RISK-001',
    component_code: 'CTRL-X4',
    component_name: 'Control Module X4',
    affected_wo_code: 'WO-2026-0142',
    required: '20.0000',
    available: '12.0000',
    confirmed_early: '0.0000',
    confirmed_late: '0.0000',
    shortage: '8.0000',
    severity: 'CRITICAL',
    has_approved_alternative: false,
    has_proposed_alternative: false,
    need_date: '2026-08-03',
    plan_code: 'PLAN-2026-W31',
    ...overrides,
  };
}

export const canonicalRisks: RiskRecordWithId[] = [
  createRisk(),
  createRisk({
    risk_id: 'RISK-002',
    component_code: 'MOTOR-M2',
    component_name: 'Motor M2',
    affected_wo_code: 'WO-2026-0150',
    required: '16.0000',
    available: '10.0000',
    confirmed_late: '10.0000',
    shortage: '6.0000',
    severity: 'HIGH',
    need_date: '2026-08-03',
  }),
  createRisk({
    risk_id: 'RISK-003',
    component_code: 'SENSOR-L9',
    component_name: 'Sensor L9',
    affected_wo_code: 'WO-2026-0156',
    required: '12.0000',
    available: '7.0000',
    shortage: '5.0000',
    severity: 'MEDIUM',
    has_proposed_alternative: true,
    need_date: '2026-08-05',
  }),
];

export const canonicalSummary: RiskSummary = {
  total: 3,
  critical: 1,
  high: 1,
  medium: 1,
  low: 0,
};

/**
 * Returns a risk with unmistakably non-canonical mutation values for AT-005 proof.
 * These values must appear in rendered UI when this fixture is supplied.
 */
export function createMutatedRisk(overrides: RiskOverrides = {}): RiskRecordWithId {
  return createRisk({
    plan_code: 'PLAN-TEST-MUTATED',
    component_code: 'MUT-TEST',
    component_name: 'Mutated Test Component',
    affected_wo_code: 'WO-TEST-999',
    required: '99.0000',
    available: '61.7500',
    confirmed_early: '0.0000',
    confirmed_late: '0.0000',
    shortage: '37.2500',
    severity: 'LOW',
    has_approved_alternative: true,
    has_proposed_alternative: false,
    need_date: '2026-12-31',
    ...overrides,
  });
}

export const mutatedRisk: RiskRecordWithId = createMutatedRisk();

export const mutatedRisks: RiskRecordWithId[] = [
  createMutatedRisk(),
  createRisk({
    risk_id: 'RISK-010',
    component_code: 'OTHER-01',
    component_name: 'Other Component',
    shortage: '1.0000',
    severity: 'LOW',
    plan_code: 'PLAN-TEST-MUTATED',
  }),
];

export const mutatedSummary: RiskSummary = {
  total: 2,
  critical: 0,
  high: 0,
  medium: 0,
  low: 2,
};

/**
 * Simple production plan summary for dashboard contract tests.
 */
export interface TestPlanSummary {
  code: string;
  status: string;
  period_start: string;
  period_end: string;
}

export const canonicalPlan: TestPlanSummary = {
  code: 'PLAN-2026-W31',
  status: 'EXECUTING',
  period_start: '2026-07-01',
  period_end: '2026-09-30',
};

export const mutatedPlan: TestPlanSummary = {
  code: 'PLAN-TEST-MUTATED',
  status: 'DRAFT',
  period_start: '2026-01-01',
  period_end: '2026-12-31',
};
