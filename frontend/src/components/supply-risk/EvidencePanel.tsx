import { useTranslation } from 'react-i18next'
import { Calculator } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import type { RiskRecordWithId } from '@/lib/risks-api'

interface EvidencePanelProps {
  risk: RiskRecordWithId;
}

/**
 * Evidence panel showing the calculation breakdown.
 * All values come from the backend (authoritative).
 *
 * Localized per WP-UX-UA-03; quantity values format with the active locale.
 */
export function EvidencePanel({ risk }: EvidencePanelProps) {
  const { t } = useTranslation('riskDetail')
  const { formatQuantity } = useLocalizedFormatters()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Calculator className="h-5 w-5" />
          {t('evidence.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-muted-foreground">{t('fields.required')}</div>
              <div className="text-lg font-semibold tabular-nums">{formatQuantity(risk.required)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">{t('fields.available')}</div>
              <div className="text-lg font-semibold tabular-nums">{formatQuantity(risk.available)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">{t('fields.confirmedEarly')}</div>
              <div className="text-lg font-semibold tabular-nums">{formatQuantity(risk.confirmed_early)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">{t('fields.confirmedLate')}</div>
              <div className="text-lg font-semibold tabular-nums">{formatQuantity(risk.confirmed_late)}</div>
            </div>
          </div>
          <div className="border-t pt-3">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-medium">{t('evidence.shortage')}</span>
              <span className="text-2xl font-bold text-destructive tabular-nums">
                {formatQuantity(risk.shortage)}
              </span>
            </div>
          </div>
          <div className="border-t pt-3">
            <p className="text-xs text-muted-foreground">{t('evidence.formula')}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
