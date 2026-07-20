import { describe, expect, it, vi, beforeEach } from 'vitest';
import * as apiModule from './risk-detail-api';
import type { AxiosResponse } from 'axios';

// We mock the underlying axios api module
vi.mock('./api', () => ({
  default: {
    get: vi.fn(),
  },
}));

// Import after mock
import api from './api';

const mockedGet = vi.mocked(api.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('risk-detail-api', () => {
  describe('fetchComponentDetail', () => {
    it('calls /components/:code', async () => {
      const mockData = {
        code: 'COMP-001',
        name: 'Component 1',
        unit: 'EA',
        alternatives: [],
      };
      mockedGet.mockResolvedValueOnce({ data: mockData } as AxiosResponse);

      const result = await apiModule.fetchComponentDetail('COMP-001');

      expect(mockedGet).toHaveBeenCalledWith('/components/COMP-001');
      expect(result).toEqual(mockData);
    });
  });

  describe('fetchInventoryDetail', () => {
    it('calls /inventory/:componentCode', async () => {
      const mockData = {
        component_code: 'COMP-001',
        component_name: 'Component 1',
        unit: 'EA',
        balances: [],
        reservations: [],
      };
      mockedGet.mockResolvedValueOnce({ data: mockData } as AxiosResponse);

      const result = await apiModule.fetchInventoryDetail('COMP-001');

      expect(mockedGet).toHaveBeenCalledWith('/inventory/COMP-001');
      expect(result).toEqual(mockData);
    });
  });

  describe('fetchPurchaseOrdersForComponent', () => {
    it('fetches PO list with limit=200 and filters by component_code', async () => {
      // Mock list response
      mockedGet.mockResolvedValueOnce({
        data: {
          items: [
            { po_number: 'PO-001', supplier_code: 'SUP-1', status: 'OPEN', placed_at: '2024-01-01', total_lines: 1, total_ordered_quantity: '10.00' },
          ],
          limit: 200,
          offset: 0,
          total: 1,
        },
      } as AxiosResponse);

      // Mock detail response
      mockedGet.mockResolvedValueOnce({
        data: {
          po_number: 'PO-001',
          supplier_code: 'SUP-1',
          status: 'OPEN',
          placed_at: '2024-01-01',
          lines: [
            {
              component_code: 'COMP-001',
              component_name: 'Component 1',
              ordered_quantity: '10.00',
              received_quantity: '0.00',
              expected_delivery_date: '2024-02-01',
              status: 'CONFIRMED',
            },
          ],
        },
      } as AxiosResponse);

      const result = await apiModule.fetchPurchaseOrdersForComponent('COMP-001');

      expect(mockedGet).toHaveBeenCalledWith('/purchase-orders', { params: { limit: 200, offset: 0 } });
      expect(mockedGet).toHaveBeenCalledWith('/purchase-orders/PO-001');
      expect(result.orders).toHaveLength(1);
      expect(result.orders[0].po_number).toBe('PO-001');
      expect(result.isPartial).toBe(false);
    });

    it('marks isPartial=true when total > 200', async () => {
      mockedGet.mockResolvedValueOnce({
        data: {
          items: [],
          limit: 200,
          offset: 0,
          total: 250,
        },
      } as AxiosResponse);

      const result = await apiModule.fetchPurchaseOrdersForComponent('COMP-001');
      expect(result.isPartial).toBe(true);
    });
  });

  describe('fetchProductionOrderDetail', () => {
    it('calls /production-orders/:orderCode', async () => {
      const mockData = {
        code: 'WO-001',
        plan_code: 'PLAN-001',
        product_code: 'PROD-001',
        product_version: '1.0',
        quantity: '100.00',
        need_date: '2024-03-01',
        status: 'RELEASED',
        requirements: [],
      };
      mockedGet.mockResolvedValueOnce({ data: mockData } as AxiosResponse);

      const result = await apiModule.fetchProductionOrderDetail('WO-001');

      expect(mockedGet).toHaveBeenCalledWith('/production-orders/WO-001');
      expect(result).toEqual(mockData);
    });
  });

  describe('fetchProductionPlanDetail', () => {
    it('calls /production-plans/:planCode', async () => {
      const mockData = {
        code: 'PLAN-001',
        status: 'ACTIVE',
        period_start: '2024-01-01',
        period_end: '2024-01-31',
        production_orders: [],
      };
      mockedGet.mockResolvedValueOnce({ data: mockData } as AxiosResponse);

      const result = await apiModule.fetchProductionPlanDetail('PLAN-001');

      expect(mockedGet).toHaveBeenCalledWith('/production-plans/PLAN-001');
      expect(result).toEqual(mockData);
    });
  });
});
