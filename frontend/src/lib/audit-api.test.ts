import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosError } from 'axios'

import i18n from '@/i18n'

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
  getAuditErrorCode,
  getAuditErrorKey,
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

beforeEach(async () => {
  vi.clearAllMocks()
  // The registry-backed formatters resolve through the real i18n layer;
  // pin English so the intentional English expectations stay stable after
  // the Ukrainian-first migration (same convention as the route tests).
  await i18n.changeLanguage('en')
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

  it('maps known event types to localized registry labels', () => {
    expect(formatEventType('APPROVAL_REQUEST_CREATED')).toBe(
      'Approval request created',
    )
    expect(formatEventType('PROCUREMENT_TASK_CREATION_FAILED')).toBe(
      'Procurement action creation failed',
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

describe('getAuditErrorKey', () => {
  it('maps 401 to the session-expired key', () => {
    expect(getAuditErrorKey(axiosError(401))).toBe(
      'common:errors.sessionExpired',
    )
  })

  it('maps 403 to a permission key without leaking detail', () => {
    const key = getAuditErrorKey(axiosError(403, { error: 'insufficient_permissions' }))
    expect(key).toBe('audit:errors.permissionDenied')
    expect(key).not.toMatch(/role|allowed|AUDITOR|AI_ADMINISTRATOR/i)
  })

  it('maps scoped-out/missing 404 without disclosing existence', () => {
    const key = getAuditErrorKey(axiosError(404, { error: 'audit_event_not_found' }))
    expect(key).toBe('audit:errors.eventNotFound')
    expect(key).not.toMatch(/uuid|exists|id=/i)
  })

  it('maps the trace 404 error code safely', () => {
    const key = getAuditErrorKey(axiosError(404, { error: 'audit_trace_not_found' }))
    expect(key).toBe('audit:errors.traceNotFound')
    expect(key).not.toMatch(/uuid|exists|id=/i)
  })

  it('maps a network error to a reachability key', () => {
    const error = { isAxiosError: true, response: undefined } as unknown as AxiosError
    expect(getAuditErrorKey(error)).toBe(
      'common:errors.serverUnreachable',
    )
  })

  it('falls back to a generic key for unknown errors', () => {
    expect(getAuditErrorKey(new Error('boom'))).toBe(
      'common:errors.unexpected',
    )
  })
})
