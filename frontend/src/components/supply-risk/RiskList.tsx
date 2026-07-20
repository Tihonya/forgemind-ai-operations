/**
 * Risk list component for WP-3.5.
 *
 * Renders a table of supply risks with fixed severity-descending ordering.
 * No row navigation, no clickable rows, no sortable headers.
 */

import { Link } from 'react-router-dom';
import { Package } from 'lucide-react';

import { SeverityBadge } from './SeverityBadge';
import { DataErrorState } from '@/components/common/DataErrorState';
import { DataEmptyState } from '@/components/common/DataEmptyState';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import type { RiskRecordWithId } from '@/lib/risks-api';
import { formatQuantity } from '@/lib/utils';

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
 * Quantity values are formatted using formatQuantity() for display.
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
      <DataErrorState
        title="Unable to load risks"
        message={error?.message ?? 'An error occurred'}
        onRetry={onRetry}
        testId="risk-list-error"
      />
    );
  }

  if (totalCount === 0) {
    return (
      <DataEmptyState
        primaryText="No risks calculated"
        secondaryText="The risk engine has not identified any supply risks for this plan."
        testId="risk-list-empty"
      />
    );
  }

  if (visibleCount === 0) {
    return (
      <DataEmptyState
        primaryText="No risks match the selected filters"
        secondaryText="Adjust your filters to see more results."
        icon={<Package className="mb-3 h-10 w-10 text-steel-500" aria-hidden="true" />}
        testId="risk-list-filtered-empty"
      />
    );
  }

  return (
    <div className="space-y-3" data-testid="risk-list">
      <div className="flex items-center justify-between text-sm text-steel-400">
        <span data-testid="risk-count">
          Showing {visibleCount} of {totalCount} risks
        </span>
      </div>
      <div className="overflow-x-auto">
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
              <TableHead>View</TableHead>
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
                <TableCell className="text-right font-mono text-sm text-red-300 tabular-nums">
                  {formatQuantity(risk.shortage)}
                </TableCell>
                <TableCell className="text-right font-mono text-sm text-steel-200 tabular-nums">
                  {formatQuantity(risk.available)}
                </TableCell>
                <TableCell className="text-right font-mono text-sm text-steel-200 tabular-nums">
                  {formatQuantity(risk.required)}
                </TableCell>
                <TableCell>
                  <Link to={`/supply-risk/${risk.risk_id}`}>
                    <Button variant="ghost" size="sm" aria-label={`View ${risk.risk_id}`}>
                      View
                    </Button>
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
