/**
 * Risk filtering and sorting utilities for WP-3.5.
 *
 * Client-side only (Phase 3 §5.1).
 * Fixed severity-descending ordering (no sortable headers).
 */

import type { RiskRecordWithId } from '@/lib/risks-api';

/** Canonical severity ordering: CRITICAL > HIGH > MEDIUM > LOW. Unknown → lowest. */
const SEVERITY_ORDER: Record<string, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
};

const UNKNOWN_SEVERITY_ORDER = 4;

/**
 * Filter risks by selected severities and component-code substring.
 *
 * Rules:
 * - If selectedSeverities is empty, return all risks (no severity filtering).
 * - If componentCodeFilter is empty, skip component-code filtering.
 * - Combined: AND logic (both must match).
 * - Component-code match is case-insensitive substring.
 */
export function filterRisks(
  risks: RiskRecordWithId[],
  selectedSeverities: string[],
  componentCodeFilter: string,
): RiskRecordWithId[] {
  return risks.filter((risk) => {
    const severityMatch =
      selectedSeverities.length === 0 ||
      selectedSeverities.includes(risk.severity);
    const componentMatch =
      componentCodeFilter.trim() === '' ||
      risk.component_code
        .toLowerCase()
        .includes(componentCodeFilter.trim().toLowerCase());
    return severityMatch && componentMatch;
  });
}

/**
 * Sort risks by severity descending (CRITICAL first), then risk_id ascending.
 *
 * Unknown severity values sort after LOW (lowest priority).
 * The sort is stable: equal severities preserve risk_id order.
 */
export function sortRisksBySeverity(risks: RiskRecordWithId[]): RiskRecordWithId[] {
  return [...risks].sort((a, b) => {
    const aOrder = SEVERITY_ORDER[a.severity] ?? UNKNOWN_SEVERITY_ORDER;
    const bOrder = SEVERITY_ORDER[b.severity] ?? UNKNOWN_SEVERITY_ORDER;

    if (aOrder !== bOrder) {
      return aOrder - bOrder;
    }
    // Stable secondary ordering by risk_id ascending
    return a.risk_id.localeCompare(b.risk_id);
  });
}
