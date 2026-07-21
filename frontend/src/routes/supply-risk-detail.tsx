import { useParams, useNavigate, Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';

import { useActivePlan } from '@/hooks/useActivePlan';
import { useRisks } from '@/hooks/useRisks';
import { useRiskDetail } from '@/hooks/useRiskDetail';
import { Button } from '@/components/ui/button';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RiskSummary } from '@/components/supply-risk/RiskSummary';
import { EvidencePanel } from '@/components/supply-risk/EvidencePanel';
import { ComponentPanel } from '@/components/supply-risk/ComponentPanel';
import { InventoryPanel } from '@/components/supply-risk/InventoryPanel';
import { IncomingSupplyPanel } from '@/components/supply-risk/IncomingSupplyPanel';
import { ProductionOrderPanel } from '@/components/supply-risk/ProductionOrderPanel';
import { PlanContextPanel } from '@/components/supply-risk/PlanContextPanel';
import { PartialFailurePlaceholder } from '@/components/supply-risk/PartialFailurePlaceholder';
import { Skeleton } from '@/components/ui/skeleton';

export default function SupplyRiskDetail() {
  const { riskId } = useParams<{ riskId: string }>();
  const navigate = useNavigate();

  // Fetch active plan
  const { activePlan, isLoading: planLoading, error: planError } = useActivePlan();

  // Fetch risks for the active plan
  const { risks, isLoading: risksLoading, error: risksError } = useRisks(activePlan?.code ?? null);

  // Fetch risk detail and enrichment data
  const {
    risk,
    component,
    inventory,
    purchaseOrders,
    purchaseOrdersPartial,
    productionOrder,
    productionPlan,
    isLoading: detailLoading,
    componentError,
    inventoryError,
    purchaseOrderError,
    productionOrderError,
    productionPlanError,
    refetchComponent,
    refetchInventory,
    refetchPurchaseOrders,
    refetchProductionOrder,
    refetchProductionPlan,
  } = useRiskDetail({ risks, riskId: riskId ?? '' });

  // Loading state — only full-page while active plan or risks list are loading
  if (planLoading || risksLoading) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Loading risk...</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    );
  }

  // Active plan error
  if (planError) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Error</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">Failed to load active plan</h2>
                <p className="text-sm text-muted-foreground mt-1">{planError.message}</p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>Back to Supply Risks</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // No active plan
  if (!activePlan) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>No Active Plan</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-muted-foreground" />
              <div>
                <h2 className="text-lg font-semibold">No active production plan</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Please select a production plan from the Supply Risks page.
                </p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>Back to Supply Risks</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Risks fetch error
  if (risksError) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Error</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">Failed to load risks</h2>
                <p className="text-sm text-muted-foreground mt-1">{risksError.message}</p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>Back to Supply Risks</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Risk not found (stale/unknown risk)
  // riskFound is true only when risks have loaded and risk matched.
  // If risks loaded but no match → stale/unknown.
  if (!detailLoading && risks.length > 0 && !risk) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Risk Not Found</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <AlertCircle className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">Risk not found</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Risk ID &quot;{riskId}&quot; does not exist in the current production plan,
                  or the plan data has changed.
                </p>
              </div>
              <Button onClick={() => navigate('/supply-risk')}>Back to Supply Risks</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Still loading detail (enrichment panels)
  if (detailLoading || !risk) {
    return (
      <div className="space-y-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/supply-risk">Supply Risks</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Loading risk...</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <div className="space-y-4">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/supply-risk">Supply Risks</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{risk.risk_id}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Page heading */}
      <h1 className="text-2xl font-bold text-white">Risk {risk.risk_id}</h1>

      {/* Risk Summary */}
      <RiskSummary risk={risk} />

      {/* Evidence Panel */}
      <EvidencePanel risk={risk} />

      {/* Component Panel */}
      {component ? (
        <ComponentPanel component={component} />
      ) : componentError ? (
        <PartialFailurePlaceholder
          label="Component Details"
          error={componentError}
          onRetry={refetchComponent}
        />
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Inventory Panel */}
      {inventory ? (
        <InventoryPanel inventory={inventory} />
      ) : inventoryError ? (
        <PartialFailurePlaceholder
          label="Inventory"
          error={inventoryError}
          onRetry={refetchInventory}
        />
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-40 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Incoming Supply Panel */}
      {purchaseOrderError ? (
        <PartialFailurePlaceholder
          label="Incoming Supply"
          error={purchaseOrderError}
          onRetry={refetchPurchaseOrders}
        />
      ) : purchaseOrders.length > 0 ? (
        <IncomingSupplyPanel
          purchaseOrders={purchaseOrders}
          isPartial={purchaseOrdersPartial}
        />
      ) : !detailLoading ? (
        <Card>
          <CardHeader>
            <CardTitle>Incoming Supply</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">No incoming supply orders found for this component.</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Production Order Panel */}
      {productionOrder ? (
        <ProductionOrderPanel productionOrder={productionOrder} />
      ) : productionOrderError ? (
        <PartialFailurePlaceholder
          label="Production Order"
          error={productionOrderError}
          onRetry={refetchProductionOrder}
        />
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Plan Context Panel */}
      {productionPlan ? (
        <PlanContextPanel productionPlan={productionPlan} />
      ) : productionPlanError ? (
        <PartialFailurePlaceholder
          label="Production Plan"
          error={productionPlanError}
          onRetry={refetchProductionPlan}
        />
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
