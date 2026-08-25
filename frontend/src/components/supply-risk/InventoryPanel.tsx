import { useTranslation } from 'react-i18next'
import { Warehouse } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useLocalizedFormatters } from '@/hooks/useLocalizedFormatters'
import type { InventoryDetail } from '@/lib/risk-detail-api'

interface InventoryPanelProps {
  inventory: InventoryDetail;
}

/**
 * Inventory panel showing warehouse balances and reservations.
 *
 * Localized per WP-UX-UA-03; warehouse/order codes remain machine content.
 */
export function InventoryPanel({ inventory }: InventoryPanelProps) {
  const { t } = useTranslation('riskDetail')
  const { formatQuantity } = useLocalizedFormatters()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Warehouse className="h-5 w-5" />
          {t('inventory.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {inventory.balances.length > 0 && (
            <div>
              <div className="text-sm font-medium mb-2">{t('inventory.warehouseBalances')}</div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('inventory.warehouse')}</TableHead>
                    <TableHead className="text-right">{t('inventory.onHand')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {inventory.balances.map((balance) => (
                    <TableRow key={balance.warehouse_code}>
                      <TableCell className="font-mono">{balance.warehouse_code}</TableCell>
                      <TableCell className="text-right">{formatQuantity(balance.quantity_on_hand)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {inventory.reservations.length > 0 && (
            <div>
              <div className="text-sm font-medium mb-2">{t('inventory.reservations')}</div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('inventory.workOrder')}</TableHead>
                    <TableHead>{t('inventory.warehouse')}</TableHead>
                    <TableHead className="text-right">{t('inventory.reserved')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {inventory.reservations.map((reservation) => (
                    <TableRow key={`${reservation.order_code}-${reservation.warehouse_code}`}>
                      <TableCell className="font-mono text-sm">{reservation.order_code}</TableCell>
                      <TableCell className="font-mono text-sm">{reservation.warehouse_code}</TableCell>
                      <TableCell className="text-right">{formatQuantity(reservation.quantity)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
