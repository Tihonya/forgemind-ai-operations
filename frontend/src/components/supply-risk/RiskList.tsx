/**
 * Risk list component for WP-3.5.
 *
 * Renders a table of supply risks with fixed severity-descending ordering.
 * No row navigation, no clickable rows, no sortable headers.
 *
 * Localized per WP-UX-UA-03; severity values and component/risk identifiers
 * remain machine content (severity labels are WP-UX-UA-04 scope).
 */

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Package } from 'lucide-react'

import { SeverityBadge } from './SeverityBadge'
import { DataErrorState } from '@/components/common/DataErrorState'
import { DataEmptyState } from '@/components/common/DataEmptyState'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { RiskRecordWithId } from '@/lib/risks-api'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'

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
 * Quantity values are formatted with the active locale.
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
  const { t } = useTranslation('supplyRisk')
  const { formatQuantity } = useLocalizedFormatters()

  if (isLoading) {
    return (
      <div className="space-y-3" data-testid="risk-list-loading">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (isError) {
    return (
      <DataErrorState
        title={t('list.loadError')}
        message={error?.message ?? t('list.errorFallback')}
        onRetry={onRetry}
        testId="risk-list-error"
      />
    )
  }

  if (totalCount === 0) {
    return (
      <DataEmptyState
        primaryText={t('list.emptyTitle')}
        secondaryText={t('list.emptyDescription')}
        testId="risk-list-empty"
      />
    )
  }

  if (visibleCount === 0) {
    return (
      <DataEmptyState
        primaryText={t('list.filteredEmptyTitle')}
        secondaryText={t('list.filteredEmptyDescription')}
        icon={<Package className="mb-3 h-10 w-10 text-steel-500" aria-hidden="true" />}
        testId="risk-list-filtered-empty"
      />
    )
  }

  return (
    <div className="space-y-3" data-testid="risk-list">
      <div className="flex items-center justify-between text-sm text-steel-400">
        <span data-testid="risk-count">
          {t('list.showingCount', { count: totalCount, visible: visibleCount, total: totalCount })}
        </span>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('columns.severity')}</TableHead>
              <TableHead>{t('columns.riskId')}</TableHead>
              <TableHead>{t('columns.componentCode')}</TableHead>
              <TableHead>{t('columns.componentName')}</TableHead>
              <TableHead className="text-right">{t('columns.shortage')}</TableHead>
              <TableHead className="text-right">{t('columns.available')}</TableHead>
              <TableHead className="text-right">{t('columns.required')}</TableHead>
              <TableHead>{t('columns.view')}</TableHead>
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
                    <Button variant="ghost" size="sm" aria-label={t('list.viewAria', { riskId: risk.risk_id })}>
                      {t('columns.view')}
                    </Button>
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
