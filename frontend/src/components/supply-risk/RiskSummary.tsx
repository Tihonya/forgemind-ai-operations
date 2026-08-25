import { useTranslation } from 'react-i18next'
import { Calendar, Hash, Package, Tag } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { SeverityBadge } from './SeverityBadge'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import type { RiskRecordWithId } from '@/lib/risks-api'

interface RiskSummaryProps {
  risk: RiskRecordWithId;
}

/**
 * Risk summary header showing key identification fields.
 *
 * Localized per WP-UX-UA-03; the severity badge and component/work-order
 * identifiers remain machine content.
 */
export function RiskSummary({ risk }: RiskSummaryProps) {
  const { t } = useTranslation('riskDetail')
  const { formatDate, formatQuantity } = useLocalizedFormatters()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Hash className="h-5 w-5 text-muted-foreground" />
            <span>{risk.risk_id}</span>
            <SeverityBadge severity={risk.severity} />
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex items-center gap-2">
            <Package className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{t('fields.component')}</span>
            <span className="text-sm">{risk.component_code}</span>
            <span className="text-sm text-muted-foreground">— {risk.component_name}</span>
          </div>
          <div className="flex items-center gap-2">
            <Tag className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{t('fields.workOrder')}</span>
            <span className="text-sm">{risk.affected_wo_code}</span>
          </div>
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{t('fields.needDate')}</span>
            <span className="text-sm">{formatDate(risk.need_date)}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{t('fields.shortage')}</span>
            <span className="text-sm font-semibold text-destructive">
              {formatQuantity(risk.shortage)}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
