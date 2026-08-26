import i18n from '@/i18n'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ApprovalCenter from '../approval-center'
import { useAuth } from '@/contexts/auth.context'
import { useApprovalRequests } from '@/hooks/use-approval-requests'
import { useApprovalDecision } from '@/hooks/use-approval-decision'
import { useProcurementCreate, useProcurementTasks } from '@/hooks/use-procurement-tasks'
import { createApprovalRequest } from '@/test/fixtures/approval-contract'

// WP-UX-UA-03: pin the active locale to English so behavior assertions
// against English copy stay stable after the Ukrainian-first migration.
beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})


vi.mock('@/contexts/auth.context', () => ({ useAuth: vi.fn() }))
vi.mock('@/hooks/use-approval-requests', () => ({ useApprovalRequests: vi.fn() }))
vi.mock('@/hooks/use-approval-decision', () => ({ useApprovalDecision: vi.fn() }))
vi.mock('@/hooks/use-procurement-tasks', () => ({
  useProcurementTasks: vi.fn(),
  useProcurementCreate: vi.fn(),
}))
vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>(
    '@tanstack/react-query',
  )
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  }
})

const mockUseAuth = vi.mocked(useAuth)
const mockUseApprovalRequests = vi.mocked(useApprovalRequests)
const mockUseApprovalDecision = vi.mocked(useApprovalDecision)
const mockUseProcurementTasks = vi.mocked(useProcurementTasks)
const mockUseProcurementCreate = vi.mocked(useProcurementCreate)

function renderRoute() {
  return render(
    <MemoryRouter>
      <ApprovalCenter />
    </MemoryRouter>,
  )
}

function baseAuth(roles: string[], id = 'user-1') {
  return {
    user: { id, username: 'user', display_name: 'User', roles },
    isAuthenticated: true,
    isLoading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  }
}

function baseList() {
  return {
    requests: [],
    total: 0,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }
}

function baseMutation() {
  return {
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
    reset: vi.fn(),
  }
}

function baseTasks() {
  return {
    tasks: [],
    total: 0,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }
}

function baseTaskMutation() {
  return {
    mutateAsync: vi.fn(),
    isPending: false,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue(baseAuth([]))
  mockUseApprovalRequests.mockReturnValue(baseList())
  mockUseApprovalDecision.mockReturnValue(baseMutation())
  mockUseProcurementTasks.mockReturnValue(baseTasks())
  mockUseProcurementCreate.mockReturnValue(baseTaskMutation())
})

describe('ApprovalCenter', () => {
  it('shows the loading state while the list is loading', () => {
    mockUseApprovalRequests.mockReturnValue({ ...baseList(), isLoading: true })
    renderRoute()
    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
  })

  it('shows the empty state when there are no approval requests', () => {
    renderRoute()
    expect(screen.getByText('No approval requests')).toBeInTheDocument()
  })

  it('shows the error state with a reload action', () => {
    mockUseApprovalRequests.mockReturnValue({
      ...baseList(),
      isError: true,
      error: new Error('boom'),
    })
    renderRoute()
    expect(screen.getByTestId('error-state')).toBeInTheDocument()
    expect(screen.getByTestId('reload-button')).toBeInTheDocument()
  })

  it('shows the creation guidance (not a manual UUID form) for PRODUCTION_MANAGER', () => {
    mockUseAuth.mockReturnValue(baseAuth(['PRODUCTION_MANAGER']))
    renderRoute()
    expect(screen.getByTestId('approval-guidance')).toBeInTheDocument()
    // The manual UUID form must be gone from the primary workflow.
    expect(screen.queryByTestId('create-submit')).not.toBeInTheDocument()
  })

  it('does NOT show the creation guidance for PROCUREMENT_SPECIALIST', () => {
    mockUseAuth.mockReturnValue(baseAuth(['PROCUREMENT_SPECIALIST']))
    renderRoute()
    expect(screen.queryByTestId('approval-guidance')).not.toBeInTheDocument()
  })

  it('renders a populated list with no decision controls for PRODUCTION_MANAGER', () => {
    mockUseAuth.mockReturnValue(baseAuth(['PRODUCTION_MANAGER']))
    mockUseApprovalRequests.mockReturnValue({
      ...baseList(),
      requests: [createApprovalRequest()],
      total: 1,
    })
    renderRoute()
    expect(screen.getByTestId('approval-request-card')).toBeInTheDocument()
    // Production manager cannot approve or reject.
    expect(screen.queryByTestId('approve-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('reject-button')).not.toBeInTheDocument()
  })

  it('renders decision controls for PROCUREMENT_SPECIALIST on a PENDING request', () => {
    mockUseAuth.mockReturnValue(baseAuth(['PROCUREMENT_SPECIALIST'], 'specialist-1'))
    mockUseApprovalRequests.mockReturnValue({
      ...baseList(),
      requests: [createApprovalRequest({ requested_by: 'other-user' })],
      total: 1,
    })
    renderRoute()
    expect(screen.getByTestId('approve-button')).toBeInTheDocument()
    expect(screen.getByTestId('reject-button')).toBeInTheDocument()
  })

  it('hides decision controls when the specialist is the requester (self-decision)', () => {
    mockUseAuth.mockReturnValue(baseAuth(['PROCUREMENT_SPECIALIST'], 'specialist-1'))
    mockUseApprovalRequests.mockReturnValue({
      ...baseList(),
      requests: [createApprovalRequest({ requested_by: 'specialist-1' })],
      total: 1,
    })
    renderRoute()
    expect(screen.queryByTestId('approve-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('reject-button')).not.toBeInTheDocument()
  })

  it('shows no decision controls or creation guidance for AUDITOR', () => {
    mockUseAuth.mockReturnValue(baseAuth(['AUDITOR']))
    mockUseApprovalRequests.mockReturnValue({
      ...baseList(),
      requests: [createApprovalRequest()],
      total: 1,
    })
    renderRoute()
    // AUDITOR is outside the backend read scope; the route renders the list
    // the backend returns, but grants no mutation controls.
    expect(screen.queryByTestId('approval-guidance')).not.toBeInTheDocument()
    expect(screen.queryByTestId('approve-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('reject-button')).not.toBeInTheDocument()
  })

  it('renders a decision trail inside each approval-request card', () => {
    mockUseAuth.mockReturnValue(baseAuth(['PRODUCTION_MANAGER']))
    mockUseApprovalRequests.mockReturnValue({
      ...baseList(),
      requests: [createApprovalRequest()],
      total: 1,
    })
    renderRoute()
    expect(screen.getByTestId('decision-trail')).toBeInTheDocument()
  })
})
