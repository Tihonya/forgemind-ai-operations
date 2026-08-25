import { useTranslation } from 'react-i18next'
import { Calendar } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import type { ProductionPlanDetail } from '@/lib/risk-detail-api'

interface PlanContextPanelProps {
  productionPlan: ProductionPlanDetail;
}

/**
 * Plan context panel showing production plan period and status.
 *
 * Localized per WP-UX-UA-03; the plan code and status remain machine content
 * (period dates format with the active locale).
 */
export function PlanContextPanel({ productionPlan }: PlanContextPanelProps) {
  const { t } = useTranslation('riskDetail')
  const { formatDate } = useLocalizedFormatters()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Calendar className="h-5 w-5" />
          {t('planContext.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="text-sm text-muted-foreground">{t('planContext.planCode')}</div>
            <div className="font-mono text-sm">{productionPlan.code}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">{t('planContext.status')}</div>
            <div className="text-sm">{productionPlan.status}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">{t('planContext.periodStart')}</div>
            <div className="text-sm">{formatDate(productionPlan.period_start)}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">{t('planContext.periodEnd')}</div>
            <div className="text-sm">{formatDate(productionPlan.period_end)}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
