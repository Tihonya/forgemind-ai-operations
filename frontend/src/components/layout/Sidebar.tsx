import { useMemo } from 'react'

import type { AuthUser } from '@/contexts/auth.context'
import { useNavigationPermissions } from './navigation/useNavigationPermissions'
import NavigationEntry from './navigation/NavigationItem'
import { ROLE_LABELS, type UserRole } from './navigation/navigation-config'

/**
 * ForgeMind logo mark (stylised "F").
 */
function LogoMark() {
  return (
    <div
      aria-hidden="true"
      className="h-8 w-8 rounded bg-primary-500 flex items-center justify-center font-bold text-white"
    >
      F
    </div>
  )
}

interface SidebarProps {
  user: AuthUser
}

/**
 * Primary navigation sidebar.
 *
 * Renders:
 * - ForgeMind logo + product name
 * - Role-aware navigation items (filtered by useNavigationPermissions)
 * - User profile summary at the bottom
 */
export default function Sidebar({ user }: SidebarProps) {
  const displayName = user.display_name ?? user.username
  const roleLabel = useMemo(() => {
    const primaryRole = user.roles[0] as UserRole | undefined
    return primaryRole ? ROLE_LABELS[primaryRole] : 'User'
  }, [user.roles])

  const { navigationItems } = useNavigationPermissions(user.roles)

  return (
    <aside
      aria-label="Primary navigation"
      className="flex h-screen w-64 flex-col bg-steel-900 border-r border-steel-700"
    >
      {/* Brand */}
      <div className="flex h-16 items-center gap-3 px-5 border-b border-steel-700">
        <LogoMark />
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold text-white">ForgeMind</span>
          <span className="text-xs text-steel-400">Supply Risk Intelligence</span>
        </div>
      </div>

      {/* Navigation */}
      <nav aria-label="Main navigation" className="flex-1 overflow-y-auto px-4 py-6 space-y-1">
        {navigationItems.map((item) => (
          <NavigationEntry key={item.id} item={item} />
        ))}
      </nav>

      {/* User summary */}
      <div className="border-t border-steel-700 px-5 py-4">
        <div
          className="flex w-full items-center gap-3"
          data-testid="sidebar-user-summary"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-steel-700 text-xs font-semibold text-white">
            {displayName.slice(0, 2).toUpperCase()}
          </div>
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-medium text-white">
              {displayName}
            </span>
            <span className="truncate text-xs text-steel-400">{roleLabel}</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
