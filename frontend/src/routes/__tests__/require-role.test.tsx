import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AUDIT_READ_ROLES } from '@/components/layout/navigation/navigation-config'
import { useAuth } from '@/contexts/auth.context'
import { useAuditEvents } from '@/hooks/use-audit-events'
import AuditLog from '../audit-log'
import RequireRole from '../require-role'

vi.mock('@/contexts/auth.context', () => ({ useAuth: vi.fn() }))
vi.mock('@/hooks/use-audit-events', () => ({
  useAuditEvents: vi.fn(),
  useAuditEvent: vi.fn(),
}))
vi.mock('@/components/audit/audit-event-detail', () => ({
  AuditEventDetail: () => null,
}))
vi.mock('@/components/audit/audit-trace-dialog', () => ({
  AuditTraceDialog: () => null,
}))

const mockUseAuth = vi.mocked(useAuth)
const mockUseAuditEvents = vi.mocked(useAuditEvents)

function baseAuth(roles: string[]) {
  return {
    user:
      roles.length > 0
        ? { id: 'user-1', username: 'user', display_name: 'User', roles }
        : null,
    isAuthenticated: roles.length > 0,
    isLoading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  }
}

function baseList() {
  return {
    events: [],
    total: 0,
    limit: 50,
    offset: 0,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }
}

function renderRouteAt(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route element={<RequireRole roles={AUDIT_READ_ROLES} />}>
          <Route path="audit-log" element={<AuditLog />} />
        </Route>
        <Route path="/" element={<div data-testid="dashboard">Dashboard</div>} />
        <Route path="/login" element={<div data-testid="login-page">Login</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue(baseAuth(['AUDITOR']))
  mockUseAuditEvents.mockReturnValue(baseList())
})

describe('Audit Log route role guard (direct navigation)', () => {
  it('renders the Audit Log for AUDITOR', () => {
    mockUseAuth.mockReturnValue(baseAuth(['AUDITOR']))
    renderRouteAt('/audit-log')
    expect(screen.getByRole('heading', { name: 'Audit Log' })).toBeInTheDocument()
  })

  it('renders the Audit Log for AI_ADMINISTRATOR', () => {
    mockUseAuth.mockReturnValue(baseAuth(['AI_ADMINISTRATOR']))
    renderRouteAt('/audit-log')
    expect(screen.getByRole('heading', { name: 'Audit Log' })).toBeInTheDocument()
  })

  it.each(['PRODUCTION_MANAGER', 'PROCUREMENT_SPECIALIST', 'ENGINEER'])(
    'redirects %s away from /audit-log with zero Audit Log route content',
    (role) => {
      mockUseAuth.mockReturnValue(baseAuth([role]))
      renderRouteAt('/audit-log')
      expect(
        screen.queryByRole('heading', { name: 'Audit Log' }),
      ).not.toBeInTheDocument()
      expect(screen.queryByTestId('audit-filter-input')).not.toBeInTheDocument()
      expect(screen.queryByTestId('loading-state')).not.toBeInTheDocument()
      expect(screen.queryByTestId('error-state')).not.toBeInTheDocument()
      expect(screen.queryByText('No audit events')).not.toBeInTheDocument()
      expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    },
  )

  it('redirects unauthenticated callers to /login with zero Audit Log content', () => {
    mockUseAuth.mockReturnValue(baseAuth([]))
    renderRouteAt('/audit-log')
    expect(
      screen.queryByRole('heading', { name: 'Audit Log' }),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('login-page')).toBeInTheDocument()
  })
})
