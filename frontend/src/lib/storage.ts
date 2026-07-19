/**
 * Session storage key for access token.
 * Phase 3 MVP: sessionStorage only. No localStorage. No passwords.
 */
export const ACCESS_TOKEN_STORAGE_KEY = 'forgemind_access_token'

/**
 * Read access token from sessionStorage.
 * Returns null if no token exists.
 */
export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
}

/**
 * Store access token in sessionStorage.
 * Never store passwords.
 */
export function setAccessToken(token: string): void {
  sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token)
}

/**
 * Remove access token from sessionStorage.
 */
export function removeAccessToken(): void {
  sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
}
