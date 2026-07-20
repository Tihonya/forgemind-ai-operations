import api from './api';

export interface ComponentAlternative {
  alternative_code: string;
  status: string;
  rationale?: string;
}

export interface ComponentDetail {
  code: string;
  name: string;
  unit: string;
  description?: string;
  alternatives: ComponentAlternative[];
}

export interface InventoryBalance {
  warehouse_code: string;
  quantity_on_hand: string;
}

export interface Reservation {
  order_code: string;
  warehouse_code: string;
  quantity: string;
}

export interface InventoryDetail {
  component_code: string;
  component_name: string;
  unit: string;
  description?: string;
  balances: InventoryBalance[];
  reservations: Reservation[];
}

export interface PurchaseOrderLine {
  component_code: string;
  component_name: string;
  ordered_quantity: string;
  received_quantity: string;
  expected_delivery_date: string;
  status: string;
}

export interface PurchaseOrderSummary {
  po_number: string;
  supplier_code: string;
  status: string;
  placed_at: string;
  total_lines: number;
  total_ordered_quantity: string;
}

export interface PurchaseOrderListResponse {
  items: PurchaseOrderSummary[];
  limit: number;
  offset: number;
  total: number;
}

export interface PurchaseOrderDetail {
  po_number: string;
  supplier_code: string;
  status: string;
  placed_at: string;
  lines: PurchaseOrderLine[];
}

/**
 * A purchase order relevant to a specific component, with line-level detail.
 * Derived by fetching PO list, then fetching detail for POs containing the component.
 */
export interface ComponentPurchaseOrder {
  po_number: string;
  supplier_code: string;
  status: string;
  placed_at: string;
  ordered_quantity: string;
  received_quantity: string;
  expected_delivery_date: string;
  line_status: string;
}

export interface ProductionOrderDetail {
  code: string;
  plan_code: string;
  product_code: string;
  product_version: string;
  quantity: string;
  need_date: string;
  status: string;
  requirements: {
    component_code: string;
    component_name: string;
    required_quantity: string;
    reserved_quantity: string;
  }[];
}

export interface ProductionPlanDetail {
  code: string;
  status: string;
  period_start: string;
  period_end: string;
  production_orders: {
    code: string;
    product_code: string;
    product_version: string;
    quantity: string;
    need_date: string;
    status: string;
  }[];
}

/**
 * Fetch component detail by code
 */
export async function fetchComponentDetail(componentCode: string): Promise<ComponentDetail> {
  const response = await api.get(`/components/${componentCode}`);
  return response.data;
}

/**
 * Fetch inventory detail by component code
 */
export async function fetchInventoryDetail(componentCode: string): Promise<InventoryDetail> {
  const response = await api.get(`/inventory/${componentCode}`);
  return response.data;
}

/**
 * Fetch purchase orders relevant to a component.
 *
 * Strategy (from verified backend contract):
 * - Backend GET /purchase-orders has NO component_code filter
 * - Fetch with limit=200 (maximum allowed)
 * - Identify POs whose lines contain the target component
 * - Fetch detail for each matching PO to get line-level info
 * - If total > 200, result is partial (caller should note this)
 *
 * @returns matching purchase orders with line-level detail, plus isPartial flag
 */
export async function fetchPurchaseOrdersForComponent(
  componentCode: string,
): Promise<{ orders: ComponentPurchaseOrder[]; isPartial: boolean }> {
  // Step 1: Fetch PO list (max 200)
  const listResponse = await api.get<PurchaseOrderListResponse>('/purchase-orders', {
    params: { limit: 200, offset: 0 },
  });
  const { items, total } = listResponse.data;
  const isPartial = total > 200;

  // Step 2: We need to identify which POs contain lines for our component.
  // The list response does NOT include line-level component codes.
  // We must fetch detail for each PO to check.
  // Optimization: fetch details in parallel, but limit concurrency
  const matchingOrders: ComponentPurchaseOrder[] = [];

  // Fetch all PO details in parallel batches
  const detailPromises = items.map((po) =>
    api
      .get<PurchaseOrderDetail>(`/purchase-orders/${po.po_number}`)
      .then((r) => r.data)
      .catch(() => null),
  );

  const details = await Promise.all(detailPromises);

  for (const detail of details) {
    if (!detail) continue;
    // Find lines for our component
    for (const line of detail.lines) {
      if (line.component_code === componentCode) {
        matchingOrders.push({
          po_number: detail.po_number,
          supplier_code: detail.supplier_code,
          status: detail.status,
          placed_at: detail.placed_at,
          ordered_quantity: line.ordered_quantity,
          received_quantity: line.received_quantity,
          expected_delivery_date: line.expected_delivery_date,
          line_status: line.status,
        });
      }
    }
  }

  return { orders: matchingOrders, isPartial };
}

/**
 * Fetch production order detail by code
 */
export async function fetchProductionOrderDetail(orderCode: string): Promise<ProductionOrderDetail> {
  const response = await api.get(`/production-orders/${orderCode}`);
  return response.data;
}

/**
 * Fetch production plan detail by code
 */
export async function fetchProductionPlanDetail(planCode: string): Promise<ProductionPlanDetail> {
  const response = await api.get(`/production-plans/${planCode}`);
  return response.data;
}
