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

export default api
