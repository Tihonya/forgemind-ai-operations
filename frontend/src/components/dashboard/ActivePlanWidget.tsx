import { Calendar, AlertTriangle, Package } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useActivePlan } from '@/hooks/useActivePlan';
import type { ProductionPlanSummary } from '@/lib/production-plans-api';

/**
 * Formats an ISO date string to a human-readable short date.
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

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    EXECUTING: 'bg-primary-600/20 text-primary-300 border-primary-600/40',
    DRAFT: 'bg-steel-700/40 text-steel-300 border-steel-600/40',
    APPROVED: 'bg-emerald-600/20 text-emerald-300 border-emerald-600/40',
    COMPLETED: 'bg-steel-700/40 text-steel-400 border-steel-600/40',
    CLOSED: 'bg-steel-700/40 text-steel-400 border-steel-600/40',
  };

  const classes = colorMap[status] ?? 'bg-steel-700/40 text-steel-300 border-steel-600/40';

  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${classes}`}
      data-testid="plan-status"
    >
      {status}
    </span>
  );
}

function PlanContent({ plan }: { plan: ProductionPlanSummary }) {
  return (
    <div className="space-y-3" data-testid="active-plan-content">
      <div className="flex items-center justify-between">
        <span className="text-lg font-semibold text-white" data-testid="plan-code">
          {plan.code}
        </span>
        <StatusBadge status={plan.status} />
      </div>
      <div className="flex items-center gap-2 text-sm text-steel-400">
        <Calendar className="h-4 w-4 text-steel-500" aria-hidden="true" />
        <span data-testid="plan-period">
          {formatDate(plan.period_start)} — {formatDate(plan.period_end)}
        </span>
      </div>
    </div>
  );
}

function MultipleActiveWarning() {
  return (
    <div
      className="mt-3 flex items-start gap-2 rounded-md border border-amber-600/30 bg-amber-600/10 px-3 py-2"
      data-testid="multiple-active-warning"
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
  );
}

/**
 * Active Production Plan widget.
 *
 * Displays the currently executing production plan with its code,
 * status badge, and date period. Handles loading, empty, and error states.
 */
export default function ActivePlanWidget() {
  const { activePlan, hasMultipleActive, isLoading, isError } = useActivePlan();

  return (
    <Card className="bg-steel-900/60 border-steel-700" data-testid="active-plan-widget">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <Package className="h-4 w-4 text-steel-500" aria-hidden="true" />
          Active Production Plan
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-3" data-testid="plan-loading">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-56" />
          </div>
        )}
        {isError && (
          <p className="text-sm text-red-400" data-testid="plan-error" role="alert">
            Unable to load production plans
          </p>
        )}
        {!isLoading && !isError && activePlan === null && (
          <p className="text-sm text-steel-400" data-testid="no-active-plan">
            No active production plan
          </p>
        )}
        {!isLoading && !isError && activePlan !== null && (
          <>
            <PlanContent plan={activePlan} />
            {hasMultipleActive && <MultipleActiveWarning />}
          </>
        )}
      </CardContent>
    </Card>
  );
}
