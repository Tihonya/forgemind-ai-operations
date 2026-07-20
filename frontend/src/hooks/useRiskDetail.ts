import { useQuery } from '@tanstack/react-query';
import type { RiskRecordWithId } from '@/lib/risks-api';
import {
  fetchComponentDetail,
  fetchInventoryDetail,
  fetchPurchaseOrdersForComponent,
  fetchProductionOrderDetail,
  fetchProductionPlanDetail,
  type ComponentDetail,
  type ComponentPurchaseOrder,
  type InventoryDetail,
  type ProductionOrderDetail,
  type ProductionPlanDetail,
} from '@/lib/risk-detail-api';

interface UseRiskDetailParams {
  risks: RiskRecordWithId[];
  riskId: string;
}

interface UseRiskDetailResult {
  risk: RiskRecordWithId | null;
  riskFound: boolean;
  component: ComponentDetail | null;
  inventory: InventoryDetail | null;
  purchaseOrders: ComponentPurchaseOrder[];
  purchaseOrdersPartial: boolean;
  productionOrder: ProductionOrderDetail | null;
  productionPlan: ProductionPlanDetail | null;
  isLoading: boolean;
  componentError: Error | null;
  inventoryError: Error | null;
  purchaseOrderError: Error | null;
  productionOrderError: Error | null;
  productionPlanError: Error | null;
  refetchComponent: () => void;
  refetchInventory: () => void;
  refetchPurchaseOrders: () => void;
  refetchProductionOrder: () => void;
  refetchProductionPlan: () => void;
}

/**
 * Hook to fetch and compose risk detail from multiple endpoints.
 *
 * Strategy:
 * - First, find the risk in the provided list by riskId
 * - If found, fetch component, inventory, purchase orders, production order, and plan in parallel
 * - Handle partial failures: if enrichment endpoints fail, still show the risk
 * - Provides per-panel refetch functions for retry
 */
export function useRiskDetail({ risks, riskId }: UseRiskDetailParams): UseRiskDetailResult {
  // Find the risk by ID
  const risk = risks.find((r) => r.risk_id === riskId) ?? null;
  const riskFound = risks.length > 0 && risk !== null;

  // Component detail query
  const componentQuery = useQuery<ComponentDetail, Error>({
    queryKey: ['component', risk?.component_code],
    queryFn: () => fetchComponentDetail(risk!.component_code),
    enabled: !!risk,
    staleTime: 30_000,
  });

  // Inventory detail query
  const inventoryQuery = useQuery<InventoryDetail, Error>({
    queryKey: ['inventory', risk?.component_code],
    queryFn: () => fetchInventoryDetail(risk!.component_code),
    enabled: !!risk,
    staleTime: 30_000,
  });

  // Purchase orders query (for this component)
  const purchaseOrdersQuery = useQuery<
    { orders: ComponentPurchaseOrder[]; isPartial: boolean },
    Error
  >({
    queryKey: ['purchase-orders-for-component', risk?.component_code],
    queryFn: () => fetchPurchaseOrdersForComponent(risk!.component_code),
    enabled: !!risk,
    staleTime: 30_000,
  });

  // Production order detail query
  const productionOrderQuery = useQuery<ProductionOrderDetail, Error>({
    queryKey: ['production-order', risk?.affected_wo_code],
    queryFn: () => fetchProductionOrderDetail(risk!.affected_wo_code),
    enabled: !!risk,
    staleTime: 30_000,
  });

  // Production plan detail query
  const productionPlanQuery = useQuery<ProductionPlanDetail, Error>({
    queryKey: ['production-plan', risk?.plan_code],
    queryFn: () => fetchProductionPlanDetail(risk!.plan_code),
    enabled: !!risk,
    staleTime: 30_000,
  });

  // Overall loading: only show full-page loading while risks list is being matched
  // Individual panels have their own loading states
  const isLoading = !riskFound && risks.length === 0;

  return {
    risk,
    riskFound,
    component: componentQuery.data ?? null,
    inventory: inventoryQuery.data ?? null,
    purchaseOrders: purchaseOrdersQuery.data?.orders ?? [],
    purchaseOrdersPartial: purchaseOrdersQuery.data?.isPartial ?? false,
    productionOrder: productionOrderQuery.data ?? null,
    productionPlan: productionPlanQuery.data ?? null,
    isLoading,
    componentError: componentQuery.error,
    inventoryError: inventoryQuery.error,
    purchaseOrderError: purchaseOrdersQuery.error,
    productionOrderError: productionOrderQuery.error,
    productionPlanError: productionPlanQuery.error,
    refetchComponent: componentQuery.refetch,
    refetchInventory: inventoryQuery.refetch,
    refetchPurchaseOrders: purchaseOrdersQuery.refetch,
    refetchProductionOrder: productionOrderQuery.refetch,
    refetchProductionPlan: productionPlanQuery.refetch,
  };
}
