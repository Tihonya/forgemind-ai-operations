import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import Header from './Header'
import type { AuthUser } from '@/contexts/auth.context'

describe('Header', () => {
  const user: AuthUser = {
    id: '1',
    username: 'test_user',
    display_name: 'Test User',
    roles: ['production_manager'],
  }

  it('renders breadcrumb for current page', () => {
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['ForgeMind', 'Dashboard']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByText('ForgeMind')).toBeInTheDocument()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('renders user identity with display name', () => {
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['Dashboard']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('header-user')).toHaveTextContent('Test User')
    expect(screen.getByTestId('header-user')).toHaveTextContent('Production Manager')
  })

  it('renders user identity with username if no display_name', () => {
    const userNoDisplay: AuthUser = {
      id: '1',
      username: 'jdoe',
      roles: ['auditor'],
    }
    render(
      <MemoryRouter>
        <Header user={userNoDisplay} breadcrumbs={['Dashboard']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('header-user')).toHaveTextContent('jdoe')
  })

  it('calls onLogout when sign out button clicked', () => {
    const logoutMock = vi.fn()
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['Dashboard']} onLogout={logoutMock} />
      </MemoryRouter>
    )
    const logoutBtn = screen.getByTestId('header-logout')
    fireEvent.click(logoutBtn)
    expect(logoutMock).toHaveBeenCalledOnce()
  })

  it('renders single breadcrumb as current page', () => {
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['Supply Risk Analysis']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByText('Supply Risk Analysis')).toBeInTheDocument()
  })
})
