import { Calculator } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatQuantity } from '@/lib/utils';
import type { RiskRecordWithId } from '@/lib/risks-api';

interface EvidencePanelProps {
  risk: RiskRecordWithId;
}

/**
 * Evidence panel showing the calculation breakdown.
 * All values come from the backend (authoritative).
 */
export function EvidencePanel({ risk }: EvidencePanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Calculator className="h-5 w-5" />
          Evidence & Calculation
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-muted-foreground">Required</div>
              <div className="text-lg font-semibold">{formatQuantity(risk.required)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Available</div>
              <div className="text-lg font-semibold">{formatQuantity(risk.available)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Confirmed (early)</div>
              <div className="text-lg font-semibold">{formatQuantity(risk.confirmed_early)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Confirmed (late)</div>
              <div className="text-lg font-semibold">{formatQuantity(risk.confirmed_late)}</div>
            </div>
          </div>
          <div className="border-t pt-3">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-medium">Shortage</span>
              <span className="text-2xl font-bold text-destructive">
                {formatQuantity(risk.shortage)}
              </span>
            </div>
          </div>
          <div className="border-t pt-3">
            <p className="text-xs text-muted-foreground">
              Shortage = max(0, required − available − confirmed_early)
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
