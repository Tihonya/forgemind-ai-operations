import { ClipboardList } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatQuantity } from '@/lib/utils';
import type { ProductionOrderDetail } from '@/lib/risk-detail-api';

interface ProductionOrderPanelProps {
  productionOrder: ProductionOrderDetail;
}

/**
 * Production order panel showing work order details.
 */
export function ProductionOrderPanel({ productionOrder }: ProductionOrderPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardList className="h-5 w-5" />
          Production Order
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <div className="text-sm text-muted-foreground">Order Code</div>
              <div className="font-mono text-sm">{productionOrder.code}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Status</div>
              <div className="text-sm">{productionOrder.status}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Product</div>
              <div className="text-sm">
                {productionOrder.product_code} v{productionOrder.product_version}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Quantity</div>
              <div className="text-sm">{formatQuantity(productionOrder.quantity)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Need Date</div>
              <div className="text-sm">{productionOrder.need_date}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Plan</div>
              <div className="font-mono text-sm">{productionOrder.plan_code}</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
