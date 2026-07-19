import { Outlet, useLocation } from 'react-router-dom'
import { useMemo } from 'react'

import { useAuth } from '@/contexts/auth.context'
import Sidebar from './Sidebar'
import Header from './Header'
import { NAVIGATION_ITEMS } from './navigation/navigation-config'

function buildBreadcrumbs(pathname: string): string[] {
  if (pathname === '/' || pathname === '') return ['Dashboard']
  const navItem = NAVIGATION_ITEMS.find((item) => item.path === pathname)
  if (navItem) return ['ForgeMind', navItem.label]
  // Unknown active path — render raw last segment
  const lastSegment = pathname.split('/').filter(Boolean).pop() ?? ''
  const label = lastSegment
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(' ')
  return ['ForgeMind', label]
}

/**
 * Authenticated application shell.
 *
 * Wraps route children (<Outlet />) with the persistent layout chrome:
 * - Sidebar (role-aware navigation)
 * - Header (breadcrumb + user identity + logout)
 */
export default function AuthenticatedLayout() {
  const { user, logout } = useAuth()
  const location = useLocation()

  const breadcrumbs = useMemo(
    () => buildBreadcrumbs(location.pathname),
    [location.pathname]
  )

  if (!user) return null

  return (
    <div className="flex h-screen overflow-hidden bg-steel-950 text-steel-100">
      <Sidebar user={user} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header user={user} breadcrumbs={breadcrumbs} onLogout={logout} />
        <main className="flex-1 overflow-y-auto bg-steel-950 p-6" aria-label="Main content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
