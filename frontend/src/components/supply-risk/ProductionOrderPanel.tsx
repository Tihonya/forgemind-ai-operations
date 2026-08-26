import { useTranslation } from 'react-i18next'
import { ClipboardList } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import StatusBadge from '@/components/status/StatusBadge'
import type { ProductionOrderDetail } from '@/lib/risk-detail-api'

interface ProductionOrderPanelProps {
  productionOrder: ProductionOrderDetail;
}

/**
 * Production order panel showing work order details.
 *
 * Localized per WP-UX-UA-03; order/product/plan codes and the order status
 * remain machine content.
 */
export function ProductionOrderPanel({ productionOrder }: ProductionOrderPanelProps) {
  const { t } = useTranslation('riskDetail')
  const { formatDate, formatQuantity } = useLocalizedFormatters()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardList className="h-5 w-5" />
          {t('productionOrder.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <div className="text-sm text-muted-foreground">{t('productionOrder.orderCode')}</div>
              <div className="font-mono text-sm">{productionOrder.code}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">{t('productionOrder.status')}</div>
              <StatusBadge
                domain="productionOrder"
                code={productionOrder.status}
                testId="production-order-status"
              />
            </div>
            <div>
              <div className="text-sm text-muted-foreground">{t('productionOrder.product')}</div>
              <div className="text-sm">
                {productionOrder.product_code} v{productionOrder.product_version}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">{t('productionOrder.quantity')}</div>
              <div className="text-sm">{formatQuantity(productionOrder.quantity)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">{t('productionOrder.needDate')}</div>
              <div className="text-sm">{formatDate(productionOrder.need_date)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">{t('productionOrder.plan')}</div>
              <div className="font-mono text-sm">{productionOrder.plan_code}</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
