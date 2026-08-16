import { Navigate, Outlet } from 'react-router-dom'

import { normalizeRoles } from '@/components/layout/navigation/useNavigationPermissions'
import type { UserRole } from '@/components/layout/navigation/navigation-config'
import { useAuth } from '@/contexts/auth.context'

interface RequireRoleProps {
  roles: ReadonlySet<UserRole>
  fallbackPath?: string
}

/**
 * Route-level role guard (DEC-052 M1 five-role model).
 *
 * Wraps a child route so that only callers holding at least one of the
 * allowed canonical roles may render it. Behavior mirrors the established
 * auth boundary (``ProtectedRoute``):
 *
 * - While auth state is loading it renders nothing (no redirect flicker).
 * - Unauthenticated callers are redirected to ``/login``.
 * - Authenticated callers missing an allowed role are redirected to
 *   ``fallbackPath`` (the dashboard by default) BEFORE any guarded content
 *   mounts, so an unauthorized caller receives zero route content.
 *
 * This is a UX/route boundary only; the backend remains the authoritative
 * source of 401/403 enforcement and no frontend guard replaces it.
 */
export default function RequireRole({
  roles,
  fallbackPath = '/',
}: RequireRoleProps) {
  const { user, isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return null
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  const normalized = normalizeRoles(user?.roles)
  const allowed = Array.from(roles).some((role) => normalized.has(role))

  if (!allowed) {
    return <Navigate to={fallbackPath} replace />
  }

  return <Outlet />
}
