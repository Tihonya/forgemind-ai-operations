import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import type { ComponentPurchaseOrder } from '@/lib/risk-detail-api'

interface IncomingSupplyPanelProps {
  purchaseOrders: ComponentPurchaseOrder[];
  isPartial?: boolean;
}

/**
 * Incoming supply panel showing purchase orders for the component.
 * Data sourced from /purchase-orders list + per-PO detail, filtered client-side.
 *
 * Localized per WP-UX-UA-03; PO/supplier identifiers and line status remain
 * machine content.
 */
export function IncomingSupplyPanel({ purchaseOrders, isPartial }: IncomingSupplyPanelProps) {
  const { t } = useTranslation('riskDetail')
  const { formatDate, formatQuantity } = useLocalizedFormatters()

  if (purchaseOrders.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('incomingSupply.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">{t('incomingSupply.empty')}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('incomingSupply.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        {isPartial && (
          <p className="mb-3 text-xs text-amber-400" role="note">
            {t('incomingSupply.partial')}
          </p>
        )}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('incomingSupply.poNumber')}</TableHead>
              <TableHead>{t('incomingSupply.supplier')}</TableHead>
              <TableHead>{t('incomingSupply.expectedDelivery')}</TableHead>
              <TableHead>{t('incomingSupply.status')}</TableHead>
              <TableHead className="text-right">{t('incomingSupply.ordered')}</TableHead>
              <TableHead className="text-right">{t('incomingSupply.received')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {purchaseOrders.map((po) => (
              <TableRow key={po.po_number}>
                <TableCell className="font-medium">{po.po_number}</TableCell>
                <TableCell>{po.supplier_code}</TableCell>
                <TableCell>{formatDate(po.expected_delivery_date)}</TableCell>
                <TableCell>
                  <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                    po.line_status === 'CONFIRMED'
                      ? 'bg-green-100 text-green-700'
                      : po.line_status === 'PENDING'
                        ? 'bg-yellow-100 text-yellow-700'
                        : 'bg-gray-100 text-gray-700'
                  }`}>
                    {po.line_status}
                  </span>
                </TableCell>
                <TableCell className="text-right font-mono text-sm">
                  {formatQuantity(po.ordered_quantity)}
                </TableCell>
                <TableCell className="text-right font-mono text-sm">
                  {formatQuantity(po.received_quantity)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
