import { useTranslation } from 'react-i18next'
import { LogOut, Menu } from 'lucide-react'

import type { AuthUser } from '@/contexts/auth.context'
import { ROLE_LABEL_KEYS } from './navigation/navigation-config'
import { normalizeRoles } from './navigation/useNavigationPermissions'
import LocaleSwitcher from './LocaleSwitcher'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'

interface HeaderProps {
  user: AuthUser
  breadcrumbs: string[]
  onLogout: () => void
  onOpenMobileMenu?: () => void
  menuButtonRef?: React.Ref<HTMLButtonElement>
  mobileMenuOpen?: boolean
}

/**
 * Top header bar rendered inside the authenticated shell.
 *
 * Contains:
 * - Mobile menu trigger (narrow viewports only)
 * - Breadcrumb / current page label
 * - Locale switcher (accessible, persists selection)
 * - User identity summary (localized role label)
 * - Logout control
 *
 * Localized per WP-UX-UA-01; role codes, routes and user identifiers are
 * machine content and remain untouched.
 */
export default function Header({
  user,
  breadcrumbs,
  onLogout,
  onOpenMobileMenu,
  menuButtonRef,
  mobileMenuOpen = false,
}: HeaderProps) {
  const { t } = useTranslation('shell')
  const displayName = user.display_name ?? user.username
  const normalized = normalizeRoles(user.roles)
  const primaryRole = Array.from(normalized)[0]
  const roleLabel = primaryRole ? t(ROLE_LABEL_KEYS[primaryRole]) : t('roleLabels.unknown')

  return (
    <header
      className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-steel-700 bg-steel-900 px-3 sm:px-6"
      aria-label={t('header.ariaLabel')}
    >
      <div className="flex min-w-0 items-center gap-2">
        {onOpenMobileMenu ? (
          <Button
            ref={menuButtonRef}
            variant="ghost"
            size="sm"
            onClick={onOpenMobileMenu}
            data-testid="mobile-menu-open"
            aria-label={t('mobileMenu.open')}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-navigation-drawer"
            className="md:hidden -ml-1 min-h-11 min-w-11 text-steel-300 hover:text-white hover:bg-steel-700"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </Button>
        ) : null}

        {/* Breadcrumb / current page */}
        <nav aria-label={t('header.breadcrumbAriaLabel')} className="min-w-0">
          <ol className="flex items-center gap-2 text-sm overflow-hidden">
            {breadcrumbs.map((crumb, idx) => (
              <li key={idx} className="flex min-w-0 items-center gap-2">
                {idx > 0 && (
                  <span className="text-steel-500" aria-hidden="true">
                    /
                  </span>
                )}
                <span
                  className={
                    idx === breadcrumbs.length - 1
                      ? 'truncate text-white font-medium'
                      : 'hidden text-steel-400 sm:inline'
                  }
                >
                  {crumb}
                </span>
              </li>
            ))}
          </ol>
        </nav>
      </div>

      <div className="flex shrink-0 items-center gap-2 sm:gap-4">
        {/* Locale switcher — desktop and mobile header both reachable */}
        <LocaleSwitcher />

        {/* User identity */}
        <div
          className="hidden flex-col items-end text-right md:flex"
          data-testid="header-user"
        >
          <span className="text-sm font-medium text-white">{displayName}</span>
          <span className="text-xs text-steel-400">{roleLabel}</span>
        </div>

        <Separator
          orientation="vertical"
          className="h-8 bg-steel-700 hidden md:block"
        />

        {/* Logout */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onLogout}
          data-testid="header-logout"
          aria-label={t('signOut')}
          className="hidden h-11 w-11 items-center justify-center p-0 text-steel-300 hover:text-white hover:bg-steel-700 md:inline-flex md:min-h-11 md:min-w-11 md:px-3 md:w-auto md:gap-2"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          <span className="hidden md:inline">{t('signOut')}</span>
        </Button>
      </div>
    </header>
  )
}