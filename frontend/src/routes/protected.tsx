import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from '@/contexts/auth.context'

/**
 * ProtectedRoute guards the authenticated area.
 *
 * - While auth state is loading, renders nothing (prevents redirect flicker).
 * - If unauthenticated, redirects to /login.
 * - If authenticated, renders child routes via <Outlet />.
 */
export default function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div
        className="min-h-screen bg-steel-900 flex items-center justify-center"
        data-testid="auth-loading"
        aria-label="Loading session"
      />
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
