/* eslint-disable react-refresh/only-export-components */
import axios from 'axios'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { PropsWithChildren, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { clearAuthHeader as clearAxiosAuthHeader } from '@/lib/api'
import { getMe, login as loginApi, UserResponse } from '@/lib/auth-api'
import {
  getAccessToken,
  removeAccessToken,
  setAccessToken,
} from '@/lib/storage'

export interface AuthUser {
  id: string
  username: string
  display_name?: string
  roles: string[]
}

export type AuthError =
  | 'invalid_credentials'
  | 'backend_unavailable'
  | 'session_invalid'
  | 'unknown'

export interface AuthContextValue {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  error: AuthError | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  clearError: () => void
}

const initialContextValue: AuthContextValue = {
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,
  login: async () => {
    throw new Error('AuthProvider not mounted')
  },
  logout: () => {
    throw new Error('AuthProvider not mounted')
  },
  clearError: () => {
    /* noop */
  },
}

export const AuthContext = createContext<AuthContextValue>(initialContextValue)

export function useAuth(): AuthContextValue {
  return useContext(AuthContext)
}

interface AuthProviderInnerProps {
  children: ReactNode
  initialToken: string | null
}

interface MeFailure {
  error: AuthError
  shouldRemoveToken: boolean
}

/**
 * Classify a failure from GET /auth/me.
 *
 * 401 — the server definitively rejects the token. Treat as invalid session.
 *       Token MUST be removed so a redirect to /login occurs on next attempt.
 *
 * 5xx — the server is up but rejecting all requests for reasons unrelated to
 *       token validity (maintenance, bug, overload). Token MAY still be valid.
 *       Token MUST be preserved so a retry can succeed without re-login.
 *
 * No HTTP response — network outage / timeout / DNS / CORS. The token has not
 * been verified or rejected. Token MUST be preserved.
 *
 * Non-axios / malformed — the response body could not be parsed. Authentication
 * state is unverifiable but not definitively broken. Token MUST be preserved.
 *
 * 403 — not emitted by the ForgeMind /auth/me contract (which returns 200 or
 *       401 only). Treat like any other non-401 status: preserve token.
 */
export function classifyMeFailure(err: unknown): MeFailure {
  if (axios.isAxiosError(err)) {
    if (err.response) {
      const status = err.response.status
      if (status === 401) {
        return { error: 'session_invalid', shouldRemoveToken: true }
      }
      if (status >= 500) {
        return { error: 'backend_unavailable', shouldRemoveToken: false }
      }
      // 3xx / 2xx / 4xx (other than 401): preserve token, mark unknown
      return { error: 'unknown', shouldRemoveToken: false }
    }
    // No HTTP response: network/TLS/DNS/CORS/timeout
    return { error: 'backend_unavailable', shouldRemoveToken: false }
  }
  // Non-axios error (thrown manually e.g. malformed response body)
  return { error: 'unknown', shouldRemoveToken: false }
}

/**
 * Classify a failure from POST /auth/login.
 *
 * 401 — invalid credentials. No token was issued; no token to remove.
 * 5xx — backend down. No token issued.
 * No response — network error. No token issued.
 * Malformed response body — no token issued.
 */
export function classifyLoginFailure(err: unknown): AuthError {
  if (axios.isAxiosError(err)) {
    if (err.response) {
      const status = err.response.status
      if (status === 401) return 'invalid_credentials'
      if (status >= 500) return 'backend_unavailable'
      return 'unknown'
    }
    return 'backend_unavailable'
  }
  return 'unknown'
}

/**
 * Validate a GET /auth/me response shape.
 * Returns null (meaning invalid) if required fields are missing.
 */
function validateUserResponse(me: unknown): UserResponse | null {
  if (!me || typeof me !== 'object') return null
  const m = me as Record<string, unknown>
  if (typeof m['id'] !== 'string') return null
  if (typeof m['username'] !== 'string') return null
  if (!Array.isArray(m['roles'])) return null
  return me as UserResponse
}

/**
 * Raw GET /auth/me — calls getMe() but returns unknown for runtime validation.
 * Test-friendly: tests can mock authApi.getMe to return valid/invalid data.
 */
async function getMeRaw(): Promise<unknown> {
  return await getMe()
}

/**
 * Sentinel errors for internal classification.
 */
class MalformedLoginResponseError extends Error {
  constructor() {
    super('malformed_login_response')
    this.name = 'MalformedLoginResponseError'
  }
}

class MalformedMeResponseError extends Error {
  constructor() {
    super('malformed_me_response')
    this.name = 'MalformedMeResponseError'
  }
}

function AuthProviderInner({
  children,
  initialToken,
}: AuthProviderInnerProps): ReactNode {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(initialToken !== null)
  const [error, setError] = useState<AuthError | null>(null)
  const navigate = useNavigate()
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  /**
   * Attempt to restore session from a stored token.
   *
   * - Calls GET /auth/me using the existing token.
   * - On 401: token is invalid → remove + clear state.
   * - On 5xx / network / malformed: token is preserved → keep in storage for
   *   retry; user remains unauthenticated; backend_unavailable/unknown exposed.
   * - Never marks authenticated without a verified user.
   */
  const restoreSession = useCallback(async () => {
    setIsLoading(true)
    try {
      const rawMe = await getMeRaw()
      const validMe = validateUserResponse(rawMe)
      if (!validMe) {
        // Malformed success response — preserve token but fail session
        throw new MalformedMeResponseError()
      }
      if (!mountedRef.current) return
      setUser({
        id: validMe.id,
        username: validMe.username,
        display_name: validMe.display_name,
        roles: validMe.roles,
      })
      setError(null)
    } catch (err) {
      if (!mountedRef.current) return
      const failure = classifyMeFailure(err)
      if (failure.shouldRemoveToken) {
        removeAccessToken()
        clearAxiosAuthHeader()
      }
      setUser(null)
      setError(failure.error)
    } finally {
      if (mountedRef.current) {
        setIsLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    if (initialToken) {
      void restoreSession().catch(() => {
        if (mountedRef.current) {
          setUser(null)
          setIsLoading(false)
        }
      })
    } else {
      setIsLoading(false)
    }
  }, [initialToken, restoreSession])

  /**
   * Login flow with correct token handling on /me failure:
   *
   * 1. POST /auth/login. On failure → no token exists, clear any stale state.
   * 2. Validate response shape. On malformed → no token stored yet.
   * 3. Store access token in sessionStorage.
   * 4. GET /auth/me. On 401 → remove token (invalid). On 5xx/network →
   *    PRESERVE token so a retry can succeed.
   * 5. Only after verified user → set authenticated + navigate.
   */
  const login = useCallback(
    async (username: string, password: string) => {
      setError(null)
      setIsLoading(true)
      try {
        // --- Step 1: /auth/login ---
        const tokenResponse = await loginApi({ username, password })

        if (
          typeof tokenResponse.access_token !== 'string' ||
          tokenResponse.access_token.length === 0 ||
          tokenResponse.token_type !== 'Bearer'
        ) {
          throw new MalformedLoginResponseError()
        }

        // --- Step 2: Store token ---
        setAccessToken(tokenResponse.access_token)

        // --- Step 3: /auth/me — with correct failure handling ---
        let validMe: UserResponse | null = null
        try {
          const rawMe = await getMeRaw()
          validMe = validateUserResponse(rawMe)
          if (!validMe) {
            throw new MalformedMeResponseError()
          }
        } catch (meErr) {
          const failure = classifyMeFailure(meErr)
          if (failure.shouldRemoveToken) {
            removeAccessToken()
            clearAxiosAuthHeader()
          }
          setUser(null)
          if (mountedRef.current) setError(failure.error)
          // DO NOT navigate. Token (if preserved) stays for retry.
          return
        }

        if (!mountedRef.current) return

        setUser({
          id: validMe.id,
          username: validMe.username,
          display_name: validMe.display_name,
          roles: validMe.roles,
        })

        navigate('/', { replace: true })
      } catch (err) {
        // /auth/login endpoint failure (or malformed response)
        // No token was issued in this attempt — clear any stale token.
        removeAccessToken()
        clearAxiosAuthHeader()
        setUser(null)

        if (mountedRef.current) {
          setError(classifyLoginFailure(err))
        }
      } finally {
        if (mountedRef.current) {
          setIsLoading(false)
        }
      }
    },
    [navigate]
  )

  const logout = useCallback(() => {
    removeAccessToken()
    clearAxiosAuthHeader()
    setUser(null)
    setError(null)
    navigate('/login', { replace: true })
  }, [navigate])

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: user !== null,
      isLoading,
      error,
      login,
      logout,
      clearError,
    }),
    [user, isLoading, error, login, logout, clearError]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/**
 * Wrapper component: reads token from sessionStorage at mount time
 * (browser-only) and passes to the inner provider.
 */
export function AuthProvider({ children }: PropsWithChildren): ReactNode {
  const token = typeof window !== 'undefined' ? getAccessToken() : null
  return <AuthProviderInner initialToken={token}>{children}</AuthProviderInner>
}
