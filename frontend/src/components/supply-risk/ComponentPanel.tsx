import { useTranslation } from 'react-i18next'
import { Package } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ComponentDetail } from '@/lib/risk-detail-api'

interface ComponentPanelProps {
  component: ComponentDetail;
}

/**
 * Component detail panel showing alternatives and metadata.
 *
 * Localized per WP-UX-UA-03; component/alternative codes and the alternative
 * status remain machine content.
 */
export function ComponentPanel({ component }: ComponentPanelProps) {
  const { t } = useTranslation('riskDetail')

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Package className="h-5 w-5" />
          {t('panels.component')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div>
            <div className="text-sm text-muted-foreground">{t('fields.code')}</div>
            <div className="font-mono text-sm">{component.code}</div>
          </div>
          {component.description && (
            <div>
              <div className="text-sm text-muted-foreground">{t('fields.description')}</div>
              <div className="text-sm">{component.description}</div>
            </div>
          )}
          {component.alternatives.length > 0 && (
            <div>
              <div className="text-sm font-medium mb-2">{t('fields.alternatives')}</div>
              <div className="space-y-2">
                {component.alternatives.map((alt) => (
                  <div key={alt.alternative_code} className="flex items-center gap-2 text-sm">
                    <span className="font-mono">{alt.alternative_code}</span>
                    <span className="text-muted-foreground">— {alt.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
