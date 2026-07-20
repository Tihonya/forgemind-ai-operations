/**
 * Supply Risk Analysis page for WP-3.5.
 *
 * Orchestrates:
 * - Active production plan (reuses WP-3.4 useActivePlan hook)
 * - Risk fetching (useRisks hook)
 * - Client-side filtering and sorting (Phase 3 §5.1)
 * - All UX states: loading, error, empty, filtered-empty, no-active-plan
 *
 * No row navigation, no risk detail, no backend changes.
 */

import { useMemo, useState } from 'react';

import { AlertTriangle, Calendar, Package } from 'lucide-react';

import { RiskFilters } from '@/components/supply-risk/RiskFilters';
import { RiskList } from '@/components/supply-risk/RiskList';
import { filterRisks, sortRisksBySeverity } from '@/components/supply-risk/riskFilterUtils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useActivePlan } from '@/hooks/useActivePlan';
import { useRisks } from '@/hooks/useRisks';
import type { ProductionPlanSummary } from '@/lib/production-plans-api';

/**
 * Format ISO date to short readable format.
 */
function formatDate(isoDate: string): string {
  try {
    const date = new Date(isoDate);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return isoDate;
  }
}

/**
 * Active production plan banner.
 * Shows plan code, status badge, and period.
 * Handles multiple-active-plan warning.
 */
function ActivePlanBanner({
  plan,
  hasMultipleActive,
  isLoading,
}: {
  plan: ProductionPlanSummary | null;
  hasMultipleActive: boolean;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card className="bg-steel-900/60 border-steel-700">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
            <Package className="h-4 w-4 text-steel-500" aria-hidden="true" />
            Active Production Plan
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-56" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!plan) {
    return (
      <Card className="bg-steel-900/60 border-steel-700">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
            <Package className="h-4 w-4 text-steel-500" aria-hidden="true" />
            Active Production Plan
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-steel-400">No active production plan</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-steel-900/60 border-steel-700">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <Package className="h-4 w-4 text-steel-500" aria-hidden="true" />
          Active Production Plan
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-lg font-semibold text-white">{plan.code}</span>
            <span className="inline-flex items-center rounded-md border border-primary-600/40 bg-primary-600/20 px-2 py-0.5 text-xs font-medium text-primary-300">
              {plan.status}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm text-steel-400">
            <Calendar className="h-4 w-4 text-steel-500" aria-hidden="true" />
            <span>
              {formatDate(plan.period_start)} — {formatDate(plan.period_end)}
            </span>
          </div>
          {hasMultipleActive && (
            <div
              className="flex items-start gap-2 rounded-md border border-amber-600/30 bg-amber-600/10 px-3 py-2"
              role="status"
            >
              <AlertTriangle
                className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-500"
                aria-hidden="true"
              />
              <p className="text-xs text-amber-300">
                Multiple active plans detected. Showing the most recent.
              </p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Supply Risk Analysis page.
 */
export default function SupplyRisk() {
  const { activePlan, hasMultipleActive, isLoading: planLoading } = useActivePlan();
  const planCode = activePlan?.code ?? null;
  const { risks, isLoading: risksLoading, isError: risksError, error, refetch } = useRisks(planCode);

  const [selectedSeverities, setSelectedSeverities] = useState<string[]>([]);
  const [componentCodeFilter, setComponentCodeFilter] = useState('');

  const filteredRisks = useMemo(
    () => filterRisks(risks, selectedSeverities, componentCodeFilter),
    [risks, selectedSeverities, componentCodeFilter],
  );

  const sortedRisks = useMemo(() => sortRisksBySeverity(filteredRisks), [filteredRisks]);

  const hasActiveFilters = selectedSeverities.length > 0 || componentCodeFilter.trim() !== '';

  function handleReset() {
    setSelectedSeverities([]);
    setComponentCodeFilter('');
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Supply Risk Analysis</h1>
        <p className="mt-1 text-sm text-steel-400">
          Identify and prioritize supply risks for the active production plan.
        </p>
      </div>

      <ActivePlanBanner plan={activePlan} hasMultipleActive={hasMultipleActive} isLoading={planLoading} />

      {planCode ? (
        <Card className="bg-steel-900/60 border-steel-700">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-steel-300">
              Supply Risks
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <RiskFilters
              selectedSeverities={selectedSeverities}
              onSeverityChange={setSelectedSeverities}
              componentCodeFilter={componentCodeFilter}
              onComponentCodeChange={setComponentCodeFilter}
              onReset={handleReset}
              hasActiveFilters={hasActiveFilters}
            />
            <RiskList
              risks={sortedRisks}
              isLoading={risksLoading}
              isError={risksError}
              error={error}
              onRetry={refetch}
              totalCount={risks.length}
              visibleCount={sortedRisks.length}
            />
          </CardContent>
        </Card>
      ) : (
        !planLoading && (
          <Card className="bg-steel-900/60 border-steel-700">
            <CardContent className="py-12">
              <div className="flex flex-col items-center justify-center text-center">
                <Package className="mb-3 h-10 w-10 text-steel-500" aria-hidden="true" />
                <p className="text-sm font-medium text-steel-300">
                  No active production plan
                </p>
                <p className="mt-1 text-xs text-steel-500">
                  Supply risk analysis requires an active production plan.
                </p>
              </div>
            </CardContent>
          </Card>
        )
      )}
    </div>
  );
}
