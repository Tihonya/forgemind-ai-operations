import i18n from '@/i18n'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth, type AuthContextValue } from '@/contexts/auth.context'
import Login from '../login'

// WP-UX-UA-03: pin the active locale to English so behavior assertions
// against English copy stay stable after the Ukrainian-first migration.
beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})


vi.mock('@/contexts/auth.context', () => ({ useAuth: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)

function baseAuth(
  roles: string[] = [],
  overrides: Partial<AuthContextValue> = {},
): AuthContextValue {
  return {
    user:
      roles.length > 0
        ? { id: 'user-1', username: 'user', display_name: 'User', roles }
        : null,
    isAuthenticated: roles.length > 0,
    isLoading: false,
    error: null,
    login: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn(),
    clearError: vi.fn(),
    ...overrides,
  }
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<div data-testid="dashboard-stub">Dashboard</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Login page demo accounts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAuth.mockReturnValue(baseAuth())
  })

  it('renders exactly three public Demo account options', () => {
    renderLogin()
    expect(screen.getAllByTestId(/^demo-account-/)).toHaveLength(3)
  })

  it('renders manager.demo', () => {
    renderLogin()
    expect(screen.getByTestId('demo-account-manager.demo')).toBeInTheDocument()
    expect(screen.getByText('manager.demo')).toBeInTheDocument()
  })

  it('renders procurement.demo', () => {
    renderLogin()
    expect(
      screen.getByTestId('demo-account-procurement.demo'),
    ).toBeInTheDocument()
  })

  it('renders auditor.demo', () => {
    renderLogin()
    expect(screen.getByTestId('demo-account-auditor.demo')).toBeInTheDocument()
  })

  it('does NOT render admin.demo', () => {
    renderLogin()
    expect(screen.queryByText('admin.demo')).not.toBeInTheDocument()
  })

  it('does NOT render engineer.demo', () => {
    renderLogin()
    expect(screen.queryByText('engineer.demo')).not.toBeInTheDocument()
  })

  it('selecting Manager fills manager username + corresponding Demo password', async () => {
    const user = userEvent.setup()
    renderLogin()
    await user.click(screen.getByTestId('demo-use-manager.demo'))
    expect(screen.getByTestId('login-username')).toHaveValue('manager.demo')
    expect(screen.getByTestId('login-password')).toHaveValue('ManagerPass123!')
  })

  it('selecting Procurement fills procurement credentials', async () => {
    const user = userEvent.setup()
    renderLogin()
    await user.click(screen.getByTestId('demo-use-procurement.demo'))
    expect(screen.getByTestId('login-username')).toHaveValue(
      'procurement.demo',
    )
    expect(screen.getByTestId('login-password')).toHaveValue(
      'ProcurementPass123!',
    )
  })

  it('selecting Auditor fills auditor credentials', async () => {
    const user = userEvent.setup()
    renderLogin()
    await user.click(screen.getByTestId('demo-use-auditor.demo'))
    expect(screen.getByTestId('login-username')).toHaveValue('auditor.demo')
    expect(screen.getByTestId('login-password')).toHaveValue(
      'AuditorPass123!',
    )
  })

  it('selecting an account does NOT auto-submit', async () => {
    const auth = baseAuth()
    mockUseAuth.mockReturnValue(auth)
    const user = userEvent.setup()
    renderLogin()
    await user.click(screen.getByTestId('demo-use-manager.demo'))
    expect(auth.login).not.toHaveBeenCalled()
    expect(screen.queryByTestId('dashboard-stub')).not.toBeInTheDocument()
    expect(screen.getByTestId('login-submit')).not.toBeDisabled()
  })
})

describe('Login page authentication behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAuth.mockReturnValue(baseAuth())
  })

  it('normal manual login submits entered username/password', async () => {
    const auth = baseAuth()
    mockUseAuth.mockReturnValue(auth)
    const user = userEvent.setup()
    renderLogin()
    await user.type(screen.getByTestId('login-username'), 'someone')
    await user.type(screen.getByTestId('login-password'), 'secret')
    await user.click(screen.getByTestId('login-submit'))
    expect(auth.login).toHaveBeenCalledTimes(1)
    expect(auth.login).toHaveBeenCalledWith('someone', 'secret')
  })

  it('loading disables submission and demo buttons', () => {
    mockUseAuth.mockReturnValue(baseAuth([], { isLoading: true }))
    renderLogin()
    expect(screen.getByTestId('login-submit')).toBeDisabled()
    expect(screen.getByTestId('login-username')).toBeDisabled()
    expect(screen.getByTestId('login-password')).toBeDisabled()
    expect(screen.getByTestId('demo-use-manager.demo')).toBeDisabled()
  })

  it('invalid credential error still renders', () => {
    mockUseAuth.mockReturnValue(baseAuth([], { error: 'invalid_credentials' }))
    renderLogin()
    expect(screen.getByTestId('login-error')).toHaveTextContent(
      'Invalid username or password.',
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('backend-unavailable error still renders', () => {
    mockUseAuth.mockReturnValue(baseAuth([], { error: 'backend_unavailable' }))
    renderLogin()
    expect(screen.getByTestId('login-error')).toHaveTextContent(
      'Authentication service is unavailable. Please try again later.',
    )
  })

  it('authenticated user still redirects away from login', () => {
    mockUseAuth.mockReturnValue(baseAuth(['PRODUCTION_MANAGER']))
    renderLogin()
    expect(screen.getByTestId('dashboard-stub')).toBeInTheDocument()
    expect(screen.queryByTestId('login-username')).not.toBeInTheDocument()
  })

  it('password visibility toggle is keyboard accessible and toggles type', async () => {
    const user = userEvent.setup()
    renderLogin()
    const input = screen.getByTestId('login-password')
    expect(input).toHaveAttribute('type', 'password')

    const show = screen.getByRole('button', { name: 'Show password' })
    await user.click(show)
    expect(input).toHaveAttribute('type', 'text')
    expect(
      screen.getByRole('button', { name: 'Hide password' }),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(input).toHaveAttribute('type', 'password')
  })
})