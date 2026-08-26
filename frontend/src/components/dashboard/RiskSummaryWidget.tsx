import { useTranslation } from 'react-i18next'
import { ShieldAlert } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useRiskSummary } from '@/hooks/useRiskSummary'
import { resolveStatus, type StatusTone } from '@/lib/status-registry'
import { useStatusTranslation } from '@/lib/status-i18n'
import type { RiskSummary } from '@/lib/risks-api'

/** Tone → count text class (repository severity colors, non-color label). */
const TONE_TEXT_CLASSES: Record<StatusTone | 'neutral', string> = {
  neutral: 'text-steel-400',
  info: 'text-blue-400',
  success: 'text-emerald-400',
  warning: 'text-amber-400',
  danger: 'text-red-400',
}

interface SeverityBadgeProps {
  /** One of CRITICAL | HIGH | MEDIUM | LOW (machine code). */
  severityCode: string;
  count: number;
  testId: string;
}

function SeverityBadge({ severityCode, count, testId }: SeverityBadgeProps) {
  const entry = resolveStatus('severity', severityCode)
  const { t } = useStatusTranslation()
  const label = entry.known ? t(entry.labelKey) : severityCode

  return (
    <div
      className="flex flex-col items-center rounded-lg border border-steel-700 bg-steel-800/40 px-3 py-2"
      data-testid={testId}
      data-severity={severityCode}
    >
      <span
        className={`text-lg font-bold ${TONE_TEXT_CLASSES[entry.tone]}`}
        data-testid={`${testId}-count`}
      >
        {count}
      </span>
      <span className="text-xs text-steel-400">{label}</span>
    </div>
  )
}

function SummaryContent({ summary, t }: { summary: RiskSummary; t: (key: string) => string }) {
  if (summary.total === 0) {
    return (
      <p className="text-sm text-steel-400" data-testid="no-risks">
        {t('widgets.riskSummary.noRisks')}
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-steel-400">{t('widgets.riskSummary.totalRisks')}</span>
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
          severityCode="CRITICAL"
          count={summary.critical}
          testId="severity-critical"
        />
        <SeverityBadge
          severityCode="HIGH"
          count={summary.high}
          testId="severity-high"
        />
        <SeverityBadge
          severityCode="MEDIUM"
          count={summary.medium}
          testId="severity-medium"
        />
        <SeverityBadge
          severityCode="LOW"
          count={summary.low}
          testId="severity-low"
        />
      </div>
    </div>
  )
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
  const { t } = useTranslation('dashboard')
  const { summary, isLoading, isError, refetch } = useRiskSummary(planCode)

  return (
    <Card data-testid="risk-summary-widget">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <ShieldAlert className="h-4 w-4 text-steel-500" aria-hidden="true" />
          {t('widgets.riskSummary.title')}
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
          <div className="space-y-2" data-testid="risk-summary-error">
            <p className="text-sm text-red-400" role="alert">
              {t('widgets.riskSummary.error')}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void refetch()
              }}
              data-testid="risk-summary-retry"
              className="border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
            >
              {t('common:actions.retry')}
            </Button>
          </div>
        )}
        {!isLoading && !isError && (
          <div data-testid="risk-summary-content">
            <SummaryContent summary={summary} t={t} />
          </div>
        )}
        {planCode === null && !isLoading && (
          <p className="text-sm text-steel-500" data-testid="risk-no-plan">
            {t('widgets.riskSummary.selectPlan')}
          </p>
        )}
      </CardContent>
    </Card>
  )
}