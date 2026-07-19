import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import type { PropsWithChildren } from 'react'

import { AuthProvider, AuthContext, useAuth } from './auth.context'
import * as authApi from '@/lib/auth-api'
import * as apiModule from '@/lib/api'
import { ACCESS_TOKEN_STORAGE_KEY } from '@/lib/storage'

// Test harness wrapper
function TestWrapper({
  children,
  initialEntries = ['/'],
}: PropsWithChildren<{ initialEntries?: string[] }>) {
  return (
    <MemoryRouter initialEntries={initialEntries}>
      <AuthProvider>{children}</AuthProvider>
    </MemoryRouter>
  )
}

// A simple component that displays auth state for assertions
function AuthStateDisplay() {
  const { user, isAuthenticated, isLoading, error } = useAuth()
  return (
    <div>
      <div data-testid="loading">{isLoading ? 'yes' : 'no'}</div>
      <div data-testid="authenticated">{isAuthenticated ? 'yes' : 'no'}</div>
      <div data-testid="username">{user?.username ?? 'none'}</div>
      <div data-testid="error">{error ?? 'none'}</div>
      <div data-testid="roles">{user?.roles?.join(',') ?? 'none'}</div>
    </div>
  )
}

/**
 * Create a mock axios-style error object.
 * isAxiosError: true makes axios.isAxiosError() return true.
 */
function mockAxiosError(
  status?: number,
  response?: Record<string, unknown>
): { isAxiosError: boolean; response?: { status: number; data?: unknown } } {
  const err: { isAxiosError: boolean; response?: { status: number; data?: unknown } } =
    { isAxiosError: true }
  if (status !== undefined || response) {
    err.response = { status: status ?? 500, data: response }
  }
  return err
}

/**
 * Mock axios error with NO response (network/DNS/timeout/CORS error).
 */
function mockNetworkError(): { isAxiosError: boolean } {
  return { isAxiosError: true }
}

/**
 * Setup the authApi mocks in their default "success" state.
 * Tests override specific spies as needed.
 */
function setupDefaultAuthMocks() {
  vi.spyOn(authApi, 'getMe').mockResolvedValue({
    id: 'user-1',
    username: 'engineer.demo',
    display_name: 'Engineer',
    roles: ['ENGINEER'],
  })
}

describe('AuthContext', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    vi.restoreAllMocks()
    // Default: mock getMe to succeed
    setupDefaultAuthMocks()
  })

  afterEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  // ═══════════════════════════════════════════════════════════════
  // 1. STARTUP RESTORATION
  // ═══════════════════════════════════════════════════════════════

  describe('initial session restoration', () => {
    it('restores user from valid stored token on mount', async () => {
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'valid-token')
      setupDefaultAuthMocks()

      render(
        <TestWrapper>
          <AuthStateDisplay />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('no')
      })
      expect(screen.getByTestId('authenticated')).toHaveTextContent('yes')
      expect(screen.getByTestId('username')).toHaveTextContent('engineer.demo')
      expect(screen.getByTestId('roles')).toHaveTextContent('ENGINEER')
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe('valid-token')
    })

    it('does not call /auth/me when no token exists', async () => {
      sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
      const getMeSpy = vi.spyOn(authApi, 'getMe')

      render(
        <TestWrapper>
          <AuthStateDisplay />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('no')
      })

      expect(getMeSpy).not.toHaveBeenCalled()
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no')
    })

    // CRITICAL: 401 removes token
    it('startup: 401 removes token, sets session_invalid, unauthenticated', async () => {
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'expired-token')
      vi.spyOn(authApi, 'getMe').mockRejectedValue(mockAxiosError(401))

      render(
        <TestWrapper>
          <AuthStateDisplay />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('no')
      })

      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no')
      expect(screen.getByTestId('username')).toHaveTextContent('none')
      expect(screen.getByTestId('error')).toHaveTextContent('session_invalid')
    })

    // CRITICAL: 500 preserves token
    it('startup: 500 preserves token, sets backend_unavailable, unauthenticated', async () => {
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'valid-but-server-error')
      vi.spyOn(authApi, 'getMe').mockRejectedValue(mockAxiosError(500))

      render(
        <TestWrapper>
          <AuthStateDisplay />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('no')
      })

      // Token MUST be preserved
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe(
        'valid-but-server-error'
      )
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no')
      expect(screen.getByTestId('username')).toHaveTextContent('none')
      expect(screen.getByTestId('error')).toHaveTextContent('backend_unavailable')
    })

    // CRITICAL: network error preserves token
    it('startup: network error preserves token, sets backend_unavailable', async () => {
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'valid-but-no-network')
      vi.spyOn(authApi, 'getMe').mockRejectedValue(mockNetworkError())

      render(
        <TestWrapper>
          <AuthStateDisplay />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('no')
      })

      // Token MUST be preserved
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe(
        'valid-but-no-network'
      )
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no')
      expect(screen.getByTestId('error')).toHaveTextContent('backend_unavailable')
    })

    it('startup: malformed /auth/me response preserves token', async () => {
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'valid-but-bad-me')
      vi.spyOn(authApi, 'getMe').mockResolvedValue({ wrong: 'shape' } as never)

      render(
        <TestWrapper>
          <AuthStateDisplay />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('no')
      })

      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe(
        'valid-but-bad-me'
      )
      expect(screen.getByTestId('authenticated')).toHaveTextContent('no')
      expect(screen.getByTestId('error')).toHaveTextContent('unknown')
    })

    it('invalid token causes redirect from protected route', async () => {
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'bad-token')
      vi.spyOn(authApi, 'getMe').mockRejectedValue(mockAxiosError(401))

      render(
        <MemoryRouter initialEntries={['/protected']}>
          <AuthProvider>
            <Routes>
              <Route
                path="/protected"
                element={
                  <AuthContext.Consumer>
                    {(ctx) =>
                      ctx.isLoading ? (
                        <div>loading</div>
                      ) : ctx.isAuthenticated ? (
                        <div>protected content</div>
                      ) : (
                        <div>redirect to login</div>
                      )
                    }
                  </AuthContext.Consumer>
                }
              />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      )

      await waitFor(() => {
        expect(screen.getByText('redirect to login')).toBeInTheDocument()
      })
    })

    it('token survives page-level provider remount within same tab', async () => {
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'persistent-token')
      setupDefaultAuthMocks()

      const { unmount } = render(
        <TestWrapper>
          <AuthStateDisplay />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('authenticated')).toHaveTextContent('yes')
      })
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe('persistent-token')

      // Simulate page-level unmount/remount
      unmount()

      render(
        <TestWrapper>
          <AuthStateDisplay />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('authenticated')).toHaveTextContent('yes')
      })
      expect(screen.getByTestId('username')).toHaveTextContent('engineer.demo')
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 2. LOGIN FLOW
  // ═══════════════════════════════════════════════════════════════

  describe('login flow', () => {
    it('successful login: stores token, sets user, authenticated', async () => {
      const loginSpy = vi.spyOn(authApi, 'login').mockResolvedValue({
        access_token: 'new-token-abc',
        token_type: 'Bearer',
        expires_in: 3600,
      })
      const getMeSpy = vi.spyOn(authApi, 'getMe').mockResolvedValue({
        id: 'user-1',
        username: 'engineer.demo',
        display_name: 'Engineer',
        roles: ['ENGINEER'],
      })

      function LoginPage() {
        const { login, error, isAuthenticated } = useAuth()
        return (
          <div>
            <button
              data-testid="login-btn"
              onClick={() => login('engineer.demo', 'DemoPass123!')}
            >
              login
            </button>
            <div data-testid="error">{error ?? 'none'}</div>
            <div data-testid="auth">{isAuthenticated ? 'yes' : 'no'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      await act(async () => {
        await screen.getByTestId('login-btn').click()
      })

      expect(loginSpy).toHaveBeenCalledWith({
        username: 'engineer.demo',
        password: 'DemoPass123!',
      })
      expect(getMeSpy).toHaveBeenCalledTimes(1)
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe(
        'new-token-abc'
      )
      expect(screen.getByTestId('auth')).toHaveTextContent('yes')
      expect(localStorage.length).toBe(0)
    })

    it('login with invalid credentials: no token set, error is invalid_credentials', async () => {
      vi.spyOn(authApi, 'login').mockRejectedValue(mockAxiosError(401))

      // Pre-seed a stale token that must be removed
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'stale-token')

      function LoginPage() {
        const { login, error, isLoading } = useAuth()
        return (
          <div>
            <button
              data-testid="login-btn"
              onClick={() => login('wrong.user', 'BadPassword')}
            >
              login
            </button>
            <div data-testid="error">{error ?? 'none'}</div>
            <div data-testid="loading">{isLoading ? 'yes' : 'no'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      // Wait for provider initialization
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('no')
      })

      await act(async () => {
        await screen.getByTestId('login-btn').click()
      })

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('no')
      })

      expect(screen.getByTestId('error')).toHaveTextContent('invalid_credentials')
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
    })

    // CRITICAL: post-login /me 500 preserves token
    it('login succeeds but /me 500: token preserved, user null, backend_unavailable', async () => {
      vi.spyOn(authApi, 'login').mockResolvedValue({
        access_token: 'fresh-token-5xx',
        token_type: 'Bearer',
        expires_in: 3600,
      })
      vi.spyOn(authApi, 'getMe').mockRejectedValue(mockAxiosError(500))

      function LoginPage() {
        const { login, error, isAuthenticated, user } = useAuth()
        return (
          <div>
            <button
              data-testid="login-btn"
              onClick={() => login('engineer.demo', 'DemoPass123!')}
            >
              login
            </button>
            <div data-testid="error">{error ?? 'none'}</div>
            <div data-testid="auth">{isAuthenticated ? 'yes' : 'no'}</div>
            <div data-testid="username">{user?.username ?? 'none'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      await act(async () => {
        await screen.getByTestId('login-btn').click()
      })

      await waitFor(() => {
        expect(screen.getByTestId('auth')).toHaveTextContent('no')
      })

      // Token MUST be preserved for retry
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe(
        'fresh-token-5xx'
      )
      expect(screen.getByTestId('error')).toHaveTextContent('backend_unavailable')
      expect(screen.getByTestId('username')).toHaveTextContent('none')
    })

    // CRITICAL: post-login /me network error preserves token
    it('login succeeds but /me network error: token preserved, backend_unavailable', async () => {
      vi.spyOn(authApi, 'login').mockResolvedValue({
        access_token: 'fresh-token-net',
        token_type: 'Bearer',
        expires_in: 3600,
      })
      vi.spyOn(authApi, 'getMe').mockRejectedValue(mockNetworkError())

      function LoginPage() {
        const { login, error, isAuthenticated } = useAuth()
        return (
          <div>
            <button
              data-testid="login-btn"
              onClick={() => login('engineer.demo', 'DemoPass123!')}
            >
              login
            </button>
            <div data-testid="error">{error ?? 'none'}</div>
            <div data-testid="auth">{isAuthenticated ? 'yes' : 'no'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      await act(async () => {
        await screen.getByTestId('login-btn').click()
      })

      await waitFor(() => {
        expect(screen.getByTestId('auth')).toHaveTextContent('no')
      })

      // Token MUST be preserved for retry
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe(
        'fresh-token-net'
      )
      expect(screen.getByTestId('error')).toHaveTextContent('backend_unavailable')
    })

    it('login succeeds but /me 401: token removed, session_invalid', async () => {
      vi.spyOn(authApi, 'login').mockResolvedValue({
        access_token: 'fresh-token-401',
        token_type: 'Bearer',
        expires_in: 3600,
      })
      vi.spyOn(authApi, 'getMe').mockRejectedValue(mockAxiosError(401))

      function LoginPage() {
        const { login, error, isAuthenticated } = useAuth()
        return (
          <div>
            <button
              data-testid="login-btn"
              onClick={() => login('engineer.demo', 'DemoPass123!')}
            >
              login
            </button>
            <div data-testid="error">{error ?? 'none'}</div>
            <div data-testid="auth">{isAuthenticated ? 'yes' : 'no'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      await act(async () => {
        await screen.getByTestId('login-btn').click()
      })

      await waitFor(() => {
        expect(screen.getByTestId('auth')).toHaveTextContent('no')
      })

      // Token MUST be removed (401 = definitively invalid)
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
      expect(screen.getByTestId('error')).toHaveTextContent('session_invalid')
    })

    it('password is never written to sessionStorage', async () => {
      vi.spyOn(authApi, 'login').mockResolvedValue({
        access_token: 'token-xyz',
        token_type: 'Bearer',
        expires_in: 3600,
      })

      function LoginPage() {
        const { login } = useAuth()
        return (
          <button
            data-testid="login-btn"
            onClick={() => login('engineer.demo', 'SuperSecretPassword!')}
          >
            login
          </button>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      await act(async () => {
        await screen.getByTestId('login-btn').click()
      })

      // Verify no password stored anywhere
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i)
        if (!key) continue
        const value = sessionStorage.getItem(key)
        expect(value).not.toContain('SuperSecretPassword!')
      }
    })

    it('malformed login response: no authenticated state, no token retained', async () => {
      vi.spyOn(authApi, 'login').mockResolvedValue({
        access_token: '',
        token_type: 'JWT',
        expires_in: 3600,
      })

      function LoginPage() {
        const { login, error, isAuthenticated } = useAuth()
        return (
          <div>
            <button
              data-testid="login-btn"
              onClick={() => login('user', 'pass')}
            >
              login
            </button>
            <div data-testid="error">{error ?? 'none'}</div>
            <div data-testid="auth">{isAuthenticated ? 'yes' : 'no'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      await act(async () => {
        await screen.getByTestId('login-btn').click()
      })

      await waitFor(() => {
        expect(screen.getByTestId('auth')).toHaveTextContent('no')
      })
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 3. LOGOUT FLOW
  // ═══════════════════════════════════════════════════════════════

  describe('logout flow', () => {
    it('removes token, clears user, clears axios header', async () => {
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'valid-token')
      setupDefaultAuthMocks()

      const clearAuthSpy = vi.spyOn(apiModule, 'clearAuthHeader')

      function Dashboard() {
        const { user, isAuthenticated, logout } = useAuth()
        return (
          <div>
            <div data-testid="user">{user?.username ?? 'none'}</div>
            <div data-testid="auth">{isAuthenticated ? 'yes' : 'no'}</div>
            <button data-testid="logout-btn" onClick={logout}>
              logout
            </button>
          </div>
        )
      }

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('engineer.demo')
      })
      expect(screen.getByTestId('auth')).toHaveTextContent('yes')

      await act(async () => {
        await screen.getByTestId('logout-btn').click()
      })

      expect(screen.getByTestId('user')).toHaveTextContent('none')
      expect(screen.getByTestId('auth')).toHaveTextContent('no')
      expect(sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
      expect(localStorage.length).toBe(0)
      expect(clearAuthSpy).toHaveBeenCalled()
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 4. LOADING / DISABLED STATE
  // ═══════════════════════════════════════════════════════════════

  describe('login disabled during request', () => {
    it('submit button is disabled while login request is pending', async () => {
      const user = userEvent.setup()

      // Use a deferred promise to control login timing
      let resolveLogin: ((v: unknown) => void) | null = null
      const loginPromise = new Promise((resolve) => {
        resolveLogin = resolve
      })

      vi.spyOn(authApi, 'login').mockReturnValue(
        loginPromise as Promise<Awaited<ReturnType<typeof authApi.login>>>
      )

      function LoginPage() {
        const { login, isLoading } = useAuth()
        return (
          <div>
            <input data-testid="username" defaultValue="test" />
            <input data-testid="password" defaultValue="pass" />
            <button
              data-testid="submit"
              disabled={isLoading}
              onClick={() => login('test', 'pass')}
            >
              {isLoading ? 'loading' : 'submit'}
            </button>
            <div data-testid="loading">{isLoading ? 'yes' : 'no'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      // Initially not loading
      expect(screen.getByTestId('loading')).toHaveTextContent('no')
      expect(screen.getByTestId('submit')).not.toBeDisabled()

      // Click to trigger login
      await act(async () => {
        await user.click(screen.getByTestId('submit'))
      })

      // Now should be loading and disabled
      await waitFor(() => {
        expect(screen.getByTestId('submit')).toBeDisabled()
      })
      expect(screen.getByTestId('loading')).toHaveTextContent('yes')
      expect(screen.getByTestId('submit')).toHaveTextContent('loading')

      // Resolve to clean up
      resolveLogin!({
        access_token: 'tok',
        token_type: 'Bearer',
        expires_in: 3600,
      })
    })

    it('duplicate submit does not issue a second login request', async () => {
      const user = userEvent.setup()

      const loginSpy = vi.spyOn(authApi, 'login').mockImplementation(
        () =>
          new Promise((resolve) => {
            // Delay to allow multiple clicks during pending
            setTimeout(() => {
              resolve({
                access_token: 'tok',
                token_type: 'Bearer',
                expires_in: 3600,
              })
            }, 100)
          })
      )

      function LoginPage() {
        const { login, isLoading } = useAuth()
        return (
          <button
            data-testid="submit"
            onClick={() => login('test', 'pass')}
            disabled={isLoading}
          >
            submit
          </button>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      // Click once
      await act(async () => {
        await user.click(screen.getByTestId('submit'))
      })

      // Submit is now disabled — cannot click again
      expect(screen.getByTestId('submit')).toBeDisabled()

      // Wait for the request to complete
      await waitFor(() => {
        expect(loginSpy).toHaveBeenCalledTimes(1)
      })
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 5. STORAGE SECURITY
  // ═══════════════════════════════════════════════════════════════

  describe('storage security', () => {
    it('localStorage remains completely unused after login', async () => {
      vi.spyOn(authApi, 'login').mockResolvedValue({
        access_token: 'tok',
        token_type: 'Bearer',
        expires_in: 3600,
      })

      function LoginPage() {
        const { login } = useAuth()
        return (
          <button data-testid="login-btn" onClick={() => login('u', 'p')}>
            login
          </button>
        )
      }

      render(
        <TestWrapper>
          <LoginPage />
        </TestWrapper>
      )

      await act(async () => {
        await screen.getByTestId('login-btn').click()
      })

      expect(localStorage.length).toBe(0)
    })

    it('storage key is the single exported constant', () => {
      expect(ACCESS_TOKEN_STORAGE_KEY).toBe('forgemind_access_token')
    })
  })
})
