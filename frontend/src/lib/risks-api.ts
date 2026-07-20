/**
 * Risks API client for WP-3.4.
 *
 * Endpoint: GET /api/v1/production-plans/{plan_code}/risks
 * Requires authentication.
 */

import api from './api';

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export interface RiskRecordWithId {
  risk_id: string;
  component_code: string;
  component_name: string;
  affected_wo_code: string;
  required: string;
  available: string;
  confirmed_early: string;
  confirmed_late: string;
  shortage: string;
  severity: string;
  has_approved_alternative: boolean;
  has_proposed_alternative: boolean;
  need_date: string;
  plan_code: string;
}

export interface RiskSummary {
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

/**
 * Fetch risk records for a production plan.
 * Requires Bearer token authentication.
 *
 * @param planCode - Production plan code (e.g., "PLAN-2026-W31")
 */
export async function getProductionPlanRisks(
  planCode: string,
): Promise<RiskRecordWithId[]> {
  const response = await api.get<RiskRecordWithId[]>(
    `/production-plans/${planCode}/risks`,
  );
  return response.data;
}

/**
 * Aggregate risk severity counts from a list of risk records.
 *
 * Rules:
 * - Count risks by severity field
 * - Known severities: CRITICAL, HIGH, MEDIUM, LOW
 * - Unknown severities are ignored (do not crash)
 * - Total = sum of all known severities
 *
 * @param risks - Array of risk records
 * @returns Aggregated severity counts
 */
export function aggregateRiskSummary(risks: RiskRecordWithId[]): RiskSummary {
  const summary: RiskSummary = {
    total: 0,
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
  };

  for (const risk of risks) {
    const severity = risk.severity.toUpperCase();

    switch (severity) {
      case 'CRITICAL':
        summary.critical++;
        summary.total++;
        break;
      case 'HIGH':
        summary.high++;
        summary.total++;
        break;
      case 'MEDIUM':
        summary.medium++;
        summary.total++;
        break;
      case 'LOW':
        summary.low++;
        summary.total++;
        break;
      default:
        // Unknown severity: ignore (do not increment total)
        break;
    }
  }

  return summary;
}
