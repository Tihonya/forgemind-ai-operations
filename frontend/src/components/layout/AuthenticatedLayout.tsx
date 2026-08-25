import { Outlet, useLocation } from 'react-router-dom'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '@/contexts/auth.context'
import Sidebar from './Sidebar'
import Header from './Header'
import MobileNavigation from './MobileNavigation'
import { NAVIGATION_ITEMS } from './navigation/navigation-config'

function buildBreadcrumbs(
  pathname: string,
  t: (key: string) => string,
): string[] {
  if (pathname === '/' || pathname === '') return [t('shell:navigation.dashboard')]
  const navItem = NAVIGATION_ITEMS.find((item) => item.path === pathname)
  if (navItem) return ['ForgeMind', t(navItem.labelKey)]
  // Unknown active path — render raw last segment (entity IDs / detail
  // routes are machine content; WP-UX-UA-01 does not translate them).
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
 * - Sidebar (role-aware, localized navigation; desktop)
 * - Mobile navigation drawer (narrow viewports)
 * - Header (localized breadcrumb + user identity + locale switcher + logout)
 *
 * Mobile behavior is part of this package (not deferred): at narrow
 * viewports the sidebar yields to an accessible menu-triggered drawer with
 * role/permission-aware items, reachable sign-out, focus management and
 * Escape dismissal.
 */
export default function AuthenticatedLayout() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const { t } = useTranslation('shell')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const menuTriggerRef = useRef<HTMLButtonElement | null>(null)

  const breadcrumbs = useMemo(
    () => buildBreadcrumbs(location.pathname, t),
    [location.pathname, t],
  )

  // Close the mobile surface on every route change (e.g. activation from
  // a nav selection or an external navigation).
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  if (!user) return null

  const logoutAndCloseMenu = () => {
    setMobileMenuOpen(false)
    logout()
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-primary-600 focus:px-4 focus:py-2 focus:text-white focus:rounded"
      >
        {t('a11y.skipToContent')}
      </a>
      <Sidebar user={user} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header
          user={user}
          breadcrumbs={breadcrumbs}
          onLogout={logout}
          onOpenMobileMenu={() => setMobileMenuOpen(true)}
          menuButtonRef={menuTriggerRef}
          mobileMenuOpen={mobileMenuOpen}
        />
        <main
          id="main-content"
          className="flex-1 overflow-y-auto bg-background p-4 sm:p-6"
          aria-label={t('a11y.mainContent')}
        >
          <Outlet />
        </main>
      </div>
      <MobileNavigation
        open={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
        user={user}
        onLogout={logoutAndCloseMenu}
        returnFocusRef={menuTriggerRef}
      />
    </div>
  )
}