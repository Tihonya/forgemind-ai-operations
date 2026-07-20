import { ShieldAlert } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useRiskSummary } from '@/hooks/useRiskSummary';
import type { RiskSummary } from '@/lib/risks-api';

interface SeverityBadgeProps {
  label: string;
  count: number;
  color: string;
  testId: string;
}

function SeverityBadge({ label, count, color, testId }: SeverityBadgeProps) {
  return (
    <div
      className="flex flex-col items-center rounded-lg border border-steel-700 bg-steel-800/40 px-3 py-2"
      data-testid={testId}
    >
      <span className={`text-lg font-bold ${color}`} data-testid={`${testId}-count`}>
        {count}
      </span>
      <span className="text-xs text-steel-400">{label}</span>
    </div>
  );
}

function SummaryContent({ summary }: { summary: RiskSummary }) {
  if (summary.total === 0) {
    return (
      <p className="text-sm text-steel-400" data-testid="no-risks">
        No active risks for this plan
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-steel-400">Total risks</span>
        <span
          className="text-2xl font-bold text-white"
          data-testid="risk-total"
        >
          {summary.total}
        </span>
      </div>
      <div
        className="grid grid-cols-4 gap-2"
        data-testid="severity-breakdown"
      >
        <SeverityBadge
          label="Critical"
          count={summary.critical}
          color="text-red-400"
          testId="severity-critical"
        />
        <SeverityBadge
          label="High"
          count={summary.high}
          color="text-amber-400"
          testId="severity-high"
        />
        <SeverityBadge
          label="Medium"
          count={summary.medium}
          color="text-yellow-400"
          testId="severity-medium"
        />
        <SeverityBadge
          label="Low"
          count={summary.low}
          color="text-blue-400"
          testId="severity-low"
        />
      </div>
    </div>
  );
}

interface RiskSummaryWidgetProps {
  planCode: string | null;
}

/**
 * Risk Severity Summary widget.
 *
 * Displays total risk count and breakdown by severity (CRITICAL, HIGH, MEDIUM, LOW).
 * Fetches risks only when a plan code is provided.
 */
export default function RiskSummaryWidget({ planCode }: RiskSummaryWidgetProps) {
  const { summary, isLoading, isError } = useRiskSummary(planCode);

  return (
    <Card className="bg-steel-900/60 border-steel-700" data-testid="risk-summary-widget">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <ShieldAlert className="h-4 w-4 text-steel-500" aria-hidden="true" />
          Risk Severity Summary
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-3" data-testid="risk-summary-loading">
            <Skeleton className="h-8 w-20" />
            <div className="grid grid-cols-4 gap-2">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
          </div>
        )}
        {isError && (
          <p className="text-sm text-red-400" data-testid="risk-summary-error" role="alert">
            Unable to load risk summary
          </p>
        )}
        {!isLoading && !isError && (
          <div data-testid="risk-summary-content">
            <SummaryContent summary={summary} />
          </div>
        )}
        {planCode === null && !isLoading && (
          <p className="text-sm text-steel-500" data-testid="risk-no-plan">
            Select a production plan to view risks
          </p>
        )}
      </CardContent>
    </Card>
  );
}
