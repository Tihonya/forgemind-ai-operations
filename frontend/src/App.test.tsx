import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from './App'
import { ACCESS_TOKEN_STORAGE_KEY } from '@/lib/storage'
import * as authApiModule from '@/lib/auth-api'

describe('App', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it('redirects unauthenticated root request to /login', async () => {
    // Ensure no token in storage
    sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)

    render(<App />)

    // Login screen should be shown — root "/" was protected
    await waitFor(() => {
      expect(screen.getByTestId('login-username')).toBeInTheDocument()
    })
    expect(screen.getByTestId('login-password')).toBeInTheDocument()
    expect(screen.getByTestId('login-submit')).toBeInTheDocument()
  })

  it('shows the protected home placeholder when already authenticated', async () => {
    const token = 'valid-token-xyz'
    sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token)

    vi.spyOn(authApiModule, 'getMe').mockResolvedValue({
      id: 'user-1',
      username: 'engineer.demo',
      display_name: 'Engineer Demo',
      roles: ['ENGINEER'],
    })

    window.history.pushState({}, 'Protected root', '/')
    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Phase 3.1 scaffold ready')).toBeInTheDocument()
    })
  })

  it('renders not-found state for unknown route after authentication', async () => {
    const token = 'valid-token-xyz'
    sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token)

    vi.spyOn(authApiModule, 'getMe').mockResolvedValue({
      id: 'user-1',
      username: 'engineer.demo',
      display_name: 'Engineer Demo',
      roles: ['ENGINEER'],
    })

    window.history.pushState({}, 'Unknown page', '/nonexistent-path')
    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Page not found')).toBeInTheDocument()
    })
  })
})
