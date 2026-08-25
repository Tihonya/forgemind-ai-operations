import { useTranslation } from 'react-i18next'
import { Calendar, AlertTriangle, Package } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useActivePlan } from '@/hooks/useActivePlan'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import type { ProductionPlanSummary } from '@/lib/production-plans-api'

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    EXECUTING: 'bg-primary-600/20 text-primary-300 border-primary-600/40',
    DRAFT: 'bg-steel-700/40 text-steel-300 border-steel-600/40',
    APPROVED: 'bg-emerald-600/20 text-emerald-300 border-emerald-600/40',
    COMPLETED: 'bg-steel-700/40 text-steel-400 border-steel-600/40',
    CLOSED: 'bg-steel-700/40 text-steel-400 border-steel-600/40',
  }

  const classes = colorMap[status] ?? 'bg-steel-700/40 text-steel-300 border-steel-600/40'

  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${classes}`}
      data-testid="plan-status"
    >
      {status}
    </span>
  )
}

function PlanContent({
  plan,
  formatDate,
}: {
  plan: ProductionPlanSummary;
  formatDate: (isoDate: string) => string;
}) {
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
  )
}

function MultipleActiveWarning({ message }: { message: string }) {
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
      <p className="text-xs text-amber-300">{message}</p>
    </div>
  )
}

/**
 * Active Production Plan widget.
 *
 * Displays the currently executing production plan with its code,
 * status badge, and date period. Handles loading, empty, and error states.
 *
 * Localized per WP-UX-UA-03; the plan code and raw status value remain
 * machine content.
 */
export default function ActivePlanWidget() {
  const { t } = useTranslation('dashboard')
  const { activePlan, hasMultipleActive, isLoading, isError, refetch } = useActivePlan()
  const { formatDate } = useLocalizedFormatters()

  return (
    <Card data-testid="active-plan-widget">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <Package className="h-4 w-4 text-steel-500" aria-hidden="true" />
          {t('widgets.activePlan.title')}
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
          <div className="space-y-2" data-testid="plan-error">
            <p className="text-sm text-red-400" role="alert">
              {t('widgets.activePlan.error')}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void refetch()
              }}
              data-testid="plan-retry"
              className="border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
            >
              {t('common:actions.retry')}
            </Button>
          </div>
        )}
        {!isLoading && !isError && activePlan === null && (
          <p className="text-sm text-steel-400" data-testid="no-active-plan">
            {t('widgets.activePlan.noActivePlan')}
          </p>
        )}
        {!isLoading && !isError && activePlan !== null && (
          <>
            <PlanContent plan={activePlan} formatDate={formatDate} />
            {hasMultipleActive && <MultipleActiveWarning message={t('widgets.activePlan.multipleActive')} />}
          </>
        )}
      </CardContent>
    </Card>
  )
}
