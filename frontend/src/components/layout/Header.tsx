import { LogOut } from 'lucide-react'

import type { AuthUser } from '@/contexts/auth.context'
import { ROLE_LABELS, type UserRole } from './navigation/navigation-config'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'

interface HeaderProps {
  user: AuthUser
  breadcrumbs: string[]
  onLogout: () => void
}

/**
 * Top header bar rendered inside the authenticated shell.
 *
 * Contains:
 * - Breadcrumb / current page label
 * - User identity summary
 * - Logout control
 */
export default function Header({ user, breadcrumbs, onLogout }: HeaderProps) {
  const displayName = user.display_name ?? user.username
  const primaryRole: UserRole | undefined = user.roles[0] as UserRole | undefined
  const roleLabel = primaryRole ? ROLE_LABELS[primaryRole] : 'User'

  return (
    <header
      className="flex h-16 items-center justify-between gap-4 border-b border-steel-700 bg-steel-900 px-6"
      aria-label="Application header"
    >
      {/* Breadcrumb / current page */}
      <nav aria-label="Breadcrumb">
        <ol className="flex items-center gap-2 text-sm">
          {breadcrumbs.map((crumb, idx) => (
            <li key={idx} className="flex items-center gap-2">
              {idx > 0 && <span className="text-steel-500">/</span>}
              <span
                className={
                  idx === breadcrumbs.length - 1
                    ? 'text-white font-medium'
                    : 'text-steel-400'
                }
              >
                {crumb}
              </span>
            </li>
          ))}
        </ol>
      </nav>

      <div className="flex items-center gap-4">
        {/* User identity */}
        <div className="hidden flex-col items-end text-right sm:flex" data-testid="header-user">
          <span className="text-sm font-medium text-white">{displayName}</span>
          <span className="text-xs text-steel-400">{roleLabel}</span>
        </div>

        <Separator orientation="vertical" className="h-8 bg-steel-700 hidden sm:block" />

        {/* Logout */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onLogout}
          data-testid="header-logout"
          aria-label="Sign out"
          className="text-steel-300 hover:text-white hover:bg-steel-700"
        >
          <LogOut className="h-4 w-4 mr-2" aria-hidden="true" />
          Sign out
        </Button>
      </div>
    </header>
  )
}
