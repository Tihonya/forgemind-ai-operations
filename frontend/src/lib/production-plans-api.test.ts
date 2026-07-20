import { describe, it, expect } from 'vitest';
import { selectActivePlan } from '@/lib/production-plans-api';
import type { ProductionPlanSummary } from '@/lib/production-plans-api';

describe('selectActivePlan', () => {
  it('returns null when no plans exist', () => {
    const plans: ProductionPlanSummary[] = [];
    expect(selectActivePlan(plans)).toBeNull();
  });

  it('returns null when no active plans exist', () => {
    const plans: ProductionPlanSummary[] = [
      { code: 'PLAN-001', status: 'DRAFT', period_start: '2025-01-01', period_end: '2025-01-31' },
      { code: 'PLAN-002', status: 'COMPLETED', period_start: '2025-02-01', period_end: '2025-02-28' },
    ];
    expect(selectActivePlan(plans)).toBeNull();
  });

  it('returns the single active plan', () => {
    const plans: ProductionPlanSummary[] = [
      { code: 'PLAN-001', status: 'DRAFT', period_start: '2025-01-01', period_end: '2025-01-31' },
      { code: 'PLAN-002', status: 'EXECUTING', period_start: '2025-02-01', period_end: '2025-02-28' },
      { code: 'PLAN-003', status: 'COMPLETED', period_start: '2025-03-01', period_end: '2025-03-31' },
    ];
    const result = selectActivePlan(plans);
    expect(result).toEqual(plans[1]);
  });

  it('selects the most recent plan when multiple active plans exist', () => {
    const plans: ProductionPlanSummary[] = [
      { code: 'PLAN-001', status: 'EXECUTING', period_start: '2025-01-01', period_end: '2025-01-31' },
      { code: 'PLAN-002', status: 'EXECUTING', period_start: '2025-03-01', period_end: '2025-03-31' },
      { code: 'PLAN-003', status: 'EXECUTING', period_start: '2025-02-01', period_end: '2025-02-28' },
    ];
    const result = selectActivePlan(plans);
    expect(result?.code).toBe('PLAN-002'); // Latest period_start
  });

  it('breaks ties by code when period_start is identical', () => {
    const plans: ProductionPlanSummary[] = [
      { code: 'PLAN-B', status: 'EXECUTING', period_start: '2025-01-01', period_end: '2025-01-31' },
      { code: 'PLAN-A', status: 'EXECUTING', period_start: '2025-01-01', period_end: '2025-01-31' },
      { code: 'PLAN-C', status: 'EXECUTING', period_start: '2025-01-01', period_end: '2025-01-31' },
    ];
    const result = selectActivePlan(plans);
    expect(result?.code).toBe('PLAN-A'); // Lexical order
  });

  it('handles plans with non-standard status values', () => {
    const plans = [
      { code: 'PLAN-001', status: 'UNKNOWN' as const, period_start: '2025-01-01', period_end: '2025-01-31' },
      { code: 'PLAN-002', status: 'EXECUTING' as const, period_start: '2025-02-01', period_end: '2025-02-28' },
    ] as ProductionPlanSummary[];
    const result = selectActivePlan(plans);
    expect(result?.code).toBe('PLAN-002');
  });
});
