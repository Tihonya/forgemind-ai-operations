import { act, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import AuthenticatedLayout from './AuthenticatedLayout'
import { AuthContext, type AuthContextValue } from '@/contexts/auth.context'
import i18n from '@/i18n'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

function renderWithAuth(ui: React.ReactElement, authValue: AuthContextValue) {
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route element={ui}>
              <Route index element={<div data-testid="route-content">Route Content</div>} />
              <Route path="supply-risk" element={<div>Ризики постачання Page</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>
  )
}

describe('AuthenticatedLayout', () => {
  const mockUser = {
    id: '1',
    username: 'test_user',
    display_name: 'Test User',
    roles: ['production_manager'],
  }

  const defaultAuthContext: AuthContextValue = {
    user: mockUser,
    isAuthenticated: true,
    isLoading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  }

  afterEach(() => {
    act(() => {
      void i18n.changeLanguage('uk')
    })
  })

  it('renders sidebar with user info (uk default)', () => {
    renderWithAuth(<AuthenticatedLayout />, defaultAuthContext)
    expect(screen.getByText('ForgeMind')).toBeInTheDocument()
    const userElements = screen.getAllByText('Test User')
    expect(userElements.length).toBeGreaterThan(0)
  })

  it('renders header with localized breadcrumb and logout', () => {
    renderWithAuth(<AuthenticatedLayout />, defaultAuthContext)
    const breadcrumbItems = screen.getAllByText('Огляд')
    expect(breadcrumbItems.length).toBeGreaterThan(0)
    expect(screen.getByTestId('header-logout')).toBeInTheDocument()
  })

  it('renders route content inside layout', () => {
    renderWithAuth(<AuthenticatedLayout />, defaultAuthContext)
    expect(screen.getByTestId('route-content')).toBeInTheDocument()
  })

  it('returns null if user is null', () => {
    const noUserContext = { ...defaultAuthContext, user: null }
    const { container } = renderWithAuth(<AuthenticatedLayout />, noUserContext)
    expect(container.firstChild).toBeNull()
  })

  it('renders sidebar navigation items based on role (permission filtering unchanged)', () => {
    renderWithAuth(<AuthenticatedLayout />, defaultAuthContext)
    expect(screen.getByTestId('nav-link-dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('nav-link-supply-risk')).toBeInTheDocument()
    expect(screen.queryByTestId('nav-link-audit')).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-disabled-knowledge')).not.toBeInTheDocument()
  })
})