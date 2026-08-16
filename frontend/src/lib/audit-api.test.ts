import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosError } from 'axios'

import {
  AUDIT_ENTITY_TYPES,
  AUDIT_EVENT_TYPES,
  ENTITY_TYPE_LABELS,
  EVENT_TYPE_LABELS,
  fetchAuditEvent,
  fetchAuditEvents,
  fetchAuditTrace,
  formatEntityType,
  formatEventType,
  formatShortId,
  formatTimestamp,
  getAuditErrorCode,
  getAuditErrorMessage,
} from '@/lib/audit-api'

vi.mock('./api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import api from './api'

type MockedApi = {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  put: ReturnType<typeof vi.fn>
  patch: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}

const mockApi = api as unknown as MockedApi

function axiosError(status: number, detail?: unknown): AxiosError {
  return {
    isAxiosError: true,
    response: {
      status,
      data: detail !== undefined ? { detail } : undefined,
    },
  } as unknown as AxiosError
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('audit-event taxonomy', () => {
  it('covers every incorporated WP-REC-04B event type', () => {
    expect(AUDIT_EVENT_TYPES).toEqual([
      'APPROVAL_REQUEST_CREATED',
      'APPROVAL_APPROVED',
      'APPROVAL_REJECTED',
      'PROCUREMENT_TASK_CREATION_ATTEMPTED',
      'PROCUREMENT_TASK_CREATED',
      'PROCUREMENT_TASK_CREATION_FAILED',
    ])
    for (const type of AUDIT_EVENT_TYPES) {
      expect(EVENT_TYPE_LABELS[type]).toBeTruthy()
    }
  })

  it('covers every incorporated entity type', () => {
    expect(AUDIT_ENTITY_TYPES).toEqual(['APPROVAL_REQUEST', 'PROCUREMENT_TASK'])
    for (const type of AUDIT_ENTITY_TYPES) {
      expect(ENTITY_TYPE_LABELS[type]).toBeTruthy()
    }
  })

  it('maps known event types to human labels', () => {
    expect(formatEventType('APPROVAL_REQUEST_CREATED')).toBe(
      'Approval request created',
    )
    expect(formatEventType('PROCUREMENT_TASK_CREATION_FAILED')).toBe(
      'Procurement task creation failed',
    )
  })

  it('falls back to the raw value for unknown event types', () => {
    expect(formatEventType('SOME_FUTURE_EVENT')).toBe('SOME_FUTURE_EVENT')
  })

  it('falls back to the raw value for unknown entity types', () => {
    expect(formatEntityType('SOME_FUTURE_ENTITY')).toBe('SOME_FUTURE_ENTITY')
  })
})

describe('formatShortId', () => {
  it('shortens long identifiers to an 8-character prefix', () => {
    expect(formatShortId('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')).toBe(
      'aaaaaaaa…',
    )
  })

  it('returns short identifiers unchanged', () => {
    expect(formatShortId('RISK-001')).toBe('RISK-001')
  })
})

describe('formatTimestamp', () => {
  it('formats an ISO timestamp consistently', () => {
    const out = formatTimestamp('2026-08-16T08:00:00Z')
    expect(out).toContain('2026')
    expect(out).toContain('Aug')
  })

  it('falls back to the raw value on parse failure', () => {
    expect(formatTimestamp('not-a-date')).toBe('not-a-date')
  })
})

describe('fetchAuditEvents (read-only list)', () => {
  it('sends only limit and offset query parameters', async () => {
    mockApi.get.mockResolvedValue({
      data: { items: [], limit: 25, offset: 50, total: 0 },
    })
    await fetchAuditEvents(25, 50)
    expect(mockApi.get).toHaveBeenCalledTimes(1)
    expect(mockApi.get).toHaveBeenCalledWith('/audit-events', {
      params: { limit: 25, offset: 50 },
    })
    // No filter parameters may be added to the backend request.
    const [, config] = mockApi.get.mock.calls[0]
    expect(Object.keys(config.params)).toEqual(['limit', 'offset'])
  })

  it('uses GET only — no write method is invoked', async () => {
    mockApi.get.mockResolvedValue({
      data: { items: [], limit: 50, offset: 0, total: 0 },
    })
    await fetchAuditEvents()
    expect(mockApi.get).toHaveBeenCalled()
    expect(mockApi.post).not.toHaveBeenCalled()
    expect(mockApi.put).not.toHaveBeenCalled()
    expect(mockApi.patch).not.toHaveBeenCalled()
    expect(mockApi.delete).not.toHaveBeenCalled()
  })
})

describe('fetchAuditEvent (read-only detail)', () => {
  it('fetches a single event by ID via GET', async () => {
    mockApi.get.mockResolvedValue({ data: { id: 'evt-1' } })
    await fetchAuditEvent('evt-1')
    expect(mockApi.get).toHaveBeenCalledWith('/audit-events/evt-1')
    expect(mockApi.post).not.toHaveBeenCalled()
    expect(mockApi.delete).not.toHaveBeenCalled()
  })
})

describe('fetchAuditTrace (read-only trace)', () => {
  it('fetches the trace by correlation ID via GET on the exact endpoint', async () => {
    mockApi.get.mockResolvedValue({ data: { items: [], complete: true } })
    await fetchAuditTrace('11111111-2222-3333-4444-555555555555')
    expect(mockApi.get).toHaveBeenCalledTimes(1)
    expect(mockApi.get).toHaveBeenCalledWith(
      '/audit-trace/11111111-2222-3333-4444-555555555555',
    )
  })

  it('uses GET only — no write method is invoked', async () => {
    mockApi.get.mockResolvedValue({ data: { items: [], complete: true } })
    await fetchAuditTrace('11111111-2222-3333-4444-555555555555')
    expect(mockApi.get).toHaveBeenCalled()
    expect(mockApi.post).not.toHaveBeenCalled()
    expect(mockApi.put).not.toHaveBeenCalled()
    expect(mockApi.patch).not.toHaveBeenCalled()
    expect(mockApi.delete).not.toHaveBeenCalled()
  })
})

describe('getAuditErrorCode', () => {
  it('extracts the stable error code from the detail body', () => {
    expect(getAuditErrorCode(axiosError(404, { error: 'audit_event_not_found' }))).toBe(
      'audit_event_not_found',
    )
  })

  it('returns null for non-axios errors', () => {
    expect(getAuditErrorCode(new Error('boom'))).toBeNull()
  })
})

describe('getAuditErrorMessage', () => {
  it('maps 401 to a session message', () => {
    expect(getAuditErrorMessage(axiosError(401))).toBe(
      'Your session has expired. Please sign in again.',
    )
  })

  it('maps 403 to a permission message without leaking detail', () => {
    const message = getAuditErrorMessage(axiosError(403, { error: 'insufficient_permissions' }))
    expect(message).toBe('You do not have permission to view the audit log.')
    expect(message).not.toMatch(/role|allowed|AUDITOR|AI_ADMINISTRATOR/i)
  })

  it('maps scoped-out/missing 404 without disclosing existence', () => {
    const message = getAuditErrorMessage(axiosError(404, { error: 'audit_event_not_found' }))
    expect(message).toBe('The audit event was not found.')
    expect(message).not.toMatch(/uuid|exists|id=/i)
  })

  it('maps the trace 404 error code safely', () => {
    const message = getAuditErrorMessage(axiosError(404, { error: 'audit_trace_not_found' }))
    expect(message).toBe('The trace was not found.')
    expect(message).not.toMatch(/uuid|exists|id=/i)
  })

  it('maps a network error to a reachability message', () => {
    const error = { isAxiosError: true, response: undefined } as unknown as AxiosError
    expect(getAuditErrorMessage(error)).toBe(
      'Unable to reach the server. Please try again.',
    )
  })

  it('falls back to a generic message for unknown errors', () => {
    expect(getAuditErrorMessage(new Error('boom'))).toBe(
      'An unexpected error occurred. Please try again.',
    )
  })
})
