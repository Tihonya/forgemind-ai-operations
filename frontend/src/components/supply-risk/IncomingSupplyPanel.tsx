import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatQuantity } from '@/lib/utils';
import type { ComponentPurchaseOrder } from '@/lib/risk-detail-api';

interface IncomingSupplyPanelProps {
  purchaseOrders: ComponentPurchaseOrder[];
  isPartial?: boolean;
}

/**
 * Incoming supply panel showing purchase orders for the component.
 * Data sourced from /purchase-orders list + per-PO detail, filtered client-side.
 */
export function IncomingSupplyPanel({ purchaseOrders, isPartial }: IncomingSupplyPanelProps) {
  if (purchaseOrders.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Incoming Supply</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">No incoming supply orders found for this component.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Incoming Supply</CardTitle>
      </CardHeader>
      <CardContent>
        {isPartial && (
          <p className="mb-3 text-xs text-amber-400" role="note">
            Showing first 200 purchase orders. Some orders may not be displayed.
          </p>
        )}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>PO Number</TableHead>
              <TableHead>Supplier</TableHead>
              <TableHead>Expected Delivery</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Ordered</TableHead>
              <TableHead className="text-right">Received</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {purchaseOrders.map((po) => (
              <TableRow key={po.po_number}>
                <TableCell className="font-medium">{po.po_number}</TableCell>
                <TableCell>{po.supplier_code}</TableCell>
                <TableCell>{po.expected_delivery_date}</TableCell>
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
  );
}
