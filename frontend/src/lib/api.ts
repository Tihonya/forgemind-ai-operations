import axios from 'axios'
import { getAccessToken } from './storage'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * Attach Bearer token to all outgoing requests.
 * Reads token from sessionStorage on each request.
 */
api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/**
 * Remove authorization header (used on logout).
 */
export function clearAuthHeader(): void {
  // Clear internal axios defaults (if any)
  delete api.defaults.headers.common['Authorization']
}

/**
 * Callback type for 401 unauthorization handling.
 * The handler is responsible for: removing the access token, clearing the
 * auth header, clearing React auth state, and navigating to /login.
 *
 * It may be synchronous (returns void) or asynchronous (returns Promise<void>).
 * The interceptor normalizes both via Promise.resolve().
 */
export type OnUnauthorizedHandler = () => void | Promise<void>

/**
 * Module-level callback registration for 401 responses.
 * AuthProvider registers its handler on mount and unregisters on unmount.
 *
 * This is the only way api.ts reacts to 401 without importing React/router
 * or auth context directly — AuthProvider pushes the handler down.
 */
let onUnauthorizedHandler: OnUnauthorizedHandler | null = null

/**
 * Register or unregister the global 401 handler.
 * Passing null clears any previously registered handler.
 */
export function setOnUnauthorizedHandler(
  handler: OnUnauthorizedHandler | null,
): void {
  onUnauthorizedHandler = handler
  // Clear dedup state when handler changes to prevent stale flags
  // from blocking future invocations after unregistration/re-registration.
  if (!handler) {
    isHandlingUnauthorized = false
  }
}

/**
 * Deduplication flag: prevents concurrent 401 storms from triggering
 * multiple session invalidations.
 */
let isHandlingUnauthorized = false

/**
 * Axios response interceptor: handles 401 Unauthorized globally.
 *
 * - Auth requests (login, /auth/me) are excluded via X-FM-Auth-Request header.
 * - Only one handler invocation per 401 storm (dedup via isHandlingUnauthorized).
 * - Handler may be sync (void) or async (Promise<void>); both are normalized.
 * - Original error is always propagated via Promise.reject(error).
 * - 403, 5xx, network errors pass through unchanged.
 */
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = axios.isAxiosError(error) && error.response?.status

    if (
      status === 401 &&
      onUnauthorizedHandler != null &&
      !isHandlingUnauthorized &&
      !axios.isCancel(error) &&
      !(axios.isAxiosError(error) &&
        error.config?.headers?.['X-FM-Auth-Request'])
    ) {
      isHandlingUnauthorized = true
      try {
        Promise.resolve(onUnauthorizedHandler()).finally(() => {
          isHandlingUnauthorized = false
        })
      } catch {
        isHandlingUnauthorized = false
      }
    }

    return Promise.reject(error)
  },
)

export default api
