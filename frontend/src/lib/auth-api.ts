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
 */
export async function login(credentials: LoginRequest): Promise<TokenResponse> {
  const response = await api.post<TokenResponse>('/auth/login', credentials)
  return response.data
}

/**
 * Get current authenticated user.
 * GET /api/v1/auth/me
 * Requires valid Bearer token in Authorization header.
 */
export async function getMe(): Promise<UserResponse> {
  const response = await api.get<UserResponse>('/auth/me')
  return response.data
}
