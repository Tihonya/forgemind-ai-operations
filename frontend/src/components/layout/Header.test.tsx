import { act, render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Header from './Header'
import type { AuthUser } from '@/contexts/auth.context'
import i18n from '@/i18n'

describe('Header', () => {
  const user: AuthUser = {
    id: '1',
    username: 'test_user',
    display_name: 'Test User',
    roles: ['production_manager'],
  }

  afterEach(() => {
    // Restore the Product Owner default locale for other tests.
    act(() => {
      void i18n.changeLanguage('uk')
    })
  })

  it('renders breadcrumb for current page', () => {
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['ForgeMind', 'Огляд']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByText('ForgeMind')).toBeInTheDocument()
    expect(screen.getByText('Огляд')).toBeInTheDocument()
  })

  it('renders user identity with display name and localized role label (uk default)', () => {
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['Огляд']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('header-user')).toHaveTextContent('Test User')
    expect(screen.getByTestId('header-user')).toHaveTextContent('Керівник виробництва')
  })

  it('renders localized role label in English after switching locale', () => {
    act(() => {
      void i18n.changeLanguage('en')
    })
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['Dashboard']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('header-user')).toHaveTextContent('Production Manager')
  })

  it('renders user identity with username if no display_name (unknown role fallback)', () => {
    const userNoDisplay: AuthUser = {
      id: '1',
      username: 'jdoe',
      roles: ['platform_admin'],
    }
    render(
      <MemoryRouter>
        <Header user={userNoDisplay} breadcrumbs={['Огляд']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('header-user')).toHaveTextContent('jdoe')
    // Unknown role → safe localized fallback label, never a crash
    expect(screen.getByTestId('header-user')).toHaveTextContent('Користувач')
  })

  it('calls onLogout when sign out button clicked (behavior unchanged)', () => {
    const logoutMock = vi.fn()
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['Огляд']} onLogout={logoutMock} />
      </MemoryRouter>
    )
    const logoutBtn = screen.getByTestId('header-logout')
    fireEvent.click(logoutBtn)
    expect(logoutMock).toHaveBeenCalledOnce()
  })

  it('renders single breadcrumb as current page', () => {
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['Ризики постачання']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByText('Ризики постачання')).toBeInTheDocument()
  })

  it('exposes a localized accessible name on the sign-out control', () => {
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['Огляд']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    // uk default → «Вийти»
    expect(screen.getByRole('button', { name: /Вийти/i })).toBeInTheDocument()
  })

  it('renders the locale switcher with both options reachable', () => {
    render(
      <MemoryRouter>
        <Header user={user} breadcrumbs={['Огляд']} onLogout={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByTestId('locale-switch-uk')).toBeInTheDocument()
    expect(screen.getByTestId('locale-switch-en')).toBeInTheDocument()
    expect(screen.getByTestId('locale-switch-uk')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('locale-switch-en')).toHaveAttribute('aria-pressed', 'false')
  })
})