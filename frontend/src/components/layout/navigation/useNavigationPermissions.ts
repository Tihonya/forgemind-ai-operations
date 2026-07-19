import { useMemo } from 'react'

import {
  ALL_ROLES,
  NAVIGATION_ITEMS,
  type NavigationItem,
  type UserRole,
} from './navigation-config'

/**
 * Normalize a list of role strings into a validated UserRole set.
 * Unknown role strings are silently ignored (defensive filter).
 */
export function normalizeRoles(roles: string[] | undefined): Set<UserRole> {
  if (!roles || roles.length === 0) return new Set<UserRole>()
  const knownRoles = new Set<string>(ALL_ROLES)
  return new Set(
    roles.filter(
      (r): r is UserRole => typeof r === 'string' && knownRoles.has(r)
    )
  )
}

/**
 * Compute the set of navigation items visible to a given set of roles.
 *
 * Rules (per wp_3_3_app_shell_spec.md §2):
 * - Unknown or missing role: Dashboard only.
 * - Multiple roles: deduplicated union.
 * - platform_admin sees all items.
 */
export function filterNavigationForRoles(
  items: readonly NavigationItem[],
  roles: Set<UserRole>
): NavigationItem[] {
  // Unknown / missing role → Dashboard only
  if (roles.size === 0) {
    return items.filter((item) => item.id === 'dashboard')
  }

  return items.filter(
    (item) =>
      item.roles.size > 0 &&
      Array.from(item.roles).some((r) => roles.has(r))
  )
}

/**
 * React hook: compute navigation items visible to the current user's roles.
 *
 * @param roles - Raw role strings from AuthUser (may include unknowns)
 *
 * Rules:
 * - Unknown or missing role → Dashboard only
 * - Deduplication of items by id (navigation registry is inherently unique)
 * - UX-only visibility; backend authorization remains authoritative
 */
export function useNavigationPermissions(roles: string[] | undefined): {
  navigationItems: NavigationItem[]
  unknownRole: boolean
} {
  return useMemo(() => {
    const normalized = normalizeRoles(roles)
    const unknownRole = normalized.size === 0
    const navigationItems = filterNavigationForRoles(NAVIGATION_ITEMS, normalized)
    return { navigationItems, unknownRole }
  }, [roles])
}
