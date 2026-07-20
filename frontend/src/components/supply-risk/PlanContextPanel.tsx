import { Calendar } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ProductionPlanDetail } from '@/lib/risk-detail-api';

interface PlanContextPanelProps {
  productionPlan: ProductionPlanDetail;
}

/**
 * Plan context panel showing production plan period and status.
 */
export function PlanContextPanel({ productionPlan }: PlanContextPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Calendar className="h-5 w-5" />
          Production Plan Context
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="text-sm text-muted-foreground">Plan Code</div>
            <div className="font-mono text-sm">{productionPlan.code}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Status</div>
            <div className="text-sm">{productionPlan.status}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Period Start</div>
            <div className="text-sm">{productionPlan.period_start}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Period End</div>
            <div className="text-sm">{productionPlan.period_end}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
