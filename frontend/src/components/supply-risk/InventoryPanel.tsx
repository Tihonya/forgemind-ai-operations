import { Warehouse } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatQuantity } from '@/lib/utils';
import type { InventoryDetail } from '@/lib/risk-detail-api';

interface InventoryPanelProps {
  inventory: InventoryDetail;
}

/**
 * Inventory panel showing warehouse balances and reservations.
 */
export function InventoryPanel({ inventory }: InventoryPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Warehouse className="h-5 w-5" />
          Inventory
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {inventory.balances.length > 0 && (
            <div>
              <div className="text-sm font-medium mb-2">Warehouse Balances</div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Warehouse</TableHead>
                    <TableHead className="text-right">On Hand</TableHead>
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
              <div className="text-sm font-medium mb-2">Reservations</div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Work Order</TableHead>
                    <TableHead>Warehouse</TableHead>
                    <TableHead className="text-right">Reserved</TableHead>
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
  );
}
