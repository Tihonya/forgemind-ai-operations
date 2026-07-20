/**
 * Production plans API client for WP-3.4.
 *
 * Endpoint: GET /api/v1/production-plans
 * Requires authentication.
 */

import api from './api';

export interface ProductionPlanSummary {
  code: string;
  status: 'DRAFT' | 'APPROVED' | 'EXECUTING' | 'COMPLETED' | 'CLOSED';
  period_start: string;
  period_end: string;
}

export interface ProductionPlanListResponse {
  items: ProductionPlanSummary[];
  limit: number;
  offset: number;
  total: number;
}

/**
 * Fetch all production plans (paginated).
 * Requires Bearer token authentication.
 */
export async function getProductionPlans(
  limit = 50,
  offset = 0,
): Promise<ProductionPlanListResponse> {
  const response = await api.get<ProductionPlanListResponse>('/production-plans', {
    params: { limit, offset },
  });
  return response.data;
}

/**
 * Select the active production plan from a list.
 *
 * Rules:
 * - Filter plans with status === 'EXECUTING'
 * - If zero active plans: return null
 * - If one active plan: return it
 * - If multiple active plans: deterministic selection:
 *   1. Latest period_start (descending)
 *   2. Tie-break by code (ascending, lexical)
 *
 * @param plans - Array of production plan summaries
 * @returns The active plan, or null if none found
 */
export function selectActivePlan(
  plans: ProductionPlanSummary[],
): ProductionPlanSummary | null {
  const activePlans = plans.filter((plan) => plan.status === 'EXECUTING');

  if (activePlans.length === 0) {
    return null;
  }

  if (activePlans.length === 1) {
    return activePlans[0];
  }

  // Multiple active plans: deterministic selection
  // Sort by period_start DESC, then code ASC
  activePlans.sort((a, b) => {
    const dateCompare = b.period_start.localeCompare(a.period_start);
    if (dateCompare !== 0) {
      return dateCompare;
    }
    return a.code.localeCompare(b.code);
  });

  return activePlans[0];
}
