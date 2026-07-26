import api from './api'

export interface LoginRequest {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface UserResponse {
  id: string
  username: string
  display_name: string
  roles: string[]
}

/**
 * Authenticate user and receive JWT.
 * POST /api/v1/auth/login
 *
 * Marked with X-FM-Auth-Request so the global 401 interceptor does NOT
 * treat a login 401 as a session-expired event (it's an invalid-credentials
 * event, handled by AuthProvider.login).
 */
export async function login(credentials: LoginRequest): Promise<TokenResponse> {
  const response = await api.post<TokenResponse>('/auth/login', credentials, {
    headers: { 'X-FM-Auth-Request': 'true' },
  })
  return response.data
}

/**
 * Get current authenticated user.
 * GET /api/v1/auth/me
 * Requires valid Bearer token in Authorization header.
 *
 * Marked with X-FM-Auth-Request so the global 401 interceptor does NOT
 * treat a /me 401 as a session-expired event — session restoration and
 * post-login /me have their own 401 handling in AuthProvider.
 */
export async function getMe(): Promise<UserResponse> {
  const response = await api.get<UserResponse>('/auth/me', {
    headers: { 'X-FM-Auth-Request': 'true' },
  })
  return response.data
}
