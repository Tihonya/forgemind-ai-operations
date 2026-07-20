/**
 * Risk list component for WP-3.5.
 *
 * Renders a table of supply risks with fixed severity-descending ordering.
 * No row navigation, no clickable rows, no sortable headers.
 */

import { AlertTriangle, Package } from 'lucide-react';

import { SeverityBadge } from './SeverityBadge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';
import type { RiskRecordWithId } from '@/lib/risks-api';

interface RiskListProps {
  risks: RiskRecordWithId[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  onRetry: () => void;
  totalCount: number;
  visibleCount: number;
}

/**
 * Render the risk list with loading, empty, error, and filtered-empty states.
 *
 * Columns: Severity, Risk ID, Component Code, Component Name, Shortage, Available, Required.
 * Decimal quantities displayed as-is from backend (4 decimal places).
 */
export function RiskList({
  risks,
  isLoading,
  isError,
  error,
  onRetry,
  totalCount,
  visibleCount,
}: RiskListProps) {
  if (isLoading) {
    return (
      <div className="space-y-3" data-testid="risk-list-loading">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className="flex items-start gap-3 rounded-md border border-red-600/30 bg-red-600/10 px-4 py-3"
        data-testid="risk-list-error"
        role="alert"
      >
        <AlertTriangle
          className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500"
          aria-hidden="true"
        />
        <div className="flex-1">
          <p className="text-sm font-medium text-red-300">
            Unable to load risks
          </p>
          {error && (
            <p className="mt-1 text-xs text-red-400">{error.message}</p>
          )}
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-red-600/40 bg-red-600/20 px-3 py-1 text-xs font-medium text-red-300 hover:bg-red-600/30"
          data-testid="retry-risks"
        >
          Retry
        </button>
      </div>
    );
  }

  if (totalCount === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-md border border-steel-700 bg-steel-800/40 px-6 py-12 text-center"
        data-testid="risk-list-empty"
      >
        <Package className="mb-3 h-10 w-10 text-steel-500" aria-hidden="true" />
        <p className="text-sm font-medium text-steel-300">
          No risks calculated
        </p>
        <p className="mt-1 text-xs text-steel-500">
          The risk engine has not identified any supply risks for this plan.
        </p>
      </div>
    );
  }

  if (visibleCount === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-md border border-steel-700 bg-steel-800/40 px-6 py-12 text-center"
        data-testid="risk-list-filtered-empty"
      >
        <Package className="mb-3 h-10 w-10 text-steel-500" aria-hidden="true" />
        <p className="text-sm font-medium text-steel-300">
          No risks match the selected filters
        </p>
        <p className="mt-1 text-xs text-steel-500">
          Adjust your filters to see more results.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="risk-list">
      <div className="flex items-center justify-between text-sm text-steel-400">
        <span data-testid="risk-count">
          Showing {visibleCount} of {totalCount} risks
        </span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Severity</TableHead>
            <TableHead>Risk ID</TableHead>
            <TableHead>Component Code</TableHead>
            <TableHead>Component Name</TableHead>
            <TableHead className="text-right">Shortage</TableHead>
            <TableHead className="text-right">Available</TableHead>
            <TableHead className="text-right">Required</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {risks.map((risk) => (
            <TableRow key={risk.risk_id}>
              <TableCell>
                <SeverityBadge severity={risk.severity} />
              </TableCell>
              <TableCell className="font-mono text-xs text-steel-300">
                {risk.risk_id}
              </TableCell>
              <TableCell className="font-mono text-sm text-white">
                {risk.component_code}
              </TableCell>
              <TableCell className="text-steel-200">
                {risk.component_name}
              </TableCell>
              <TableCell className="text-right font-mono text-sm text-red-300">
                {risk.shortage}
              </TableCell>
              <TableCell className="text-right font-mono text-sm text-steel-200">
                {risk.available}
              </TableCell>
              <TableCell className="text-right font-mono text-sm text-steel-200">
                {risk.required}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
