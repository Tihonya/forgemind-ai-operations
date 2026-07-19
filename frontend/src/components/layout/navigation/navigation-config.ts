import type { ElementType } from 'react'
import {
  LayoutDashboard,
  ShieldAlert,
  BookOpen,
  Workflow,
  CheckCircle2,
  FileText,
  Settings,
} from 'lucide-react'

/**
 * Canonical demo roles from DEC-028.
 */
export type UserRole =
  | 'production_manager'
  | 'procurement_specialist'
  | 'ai_administrator'
  | 'auditor'
  | 'platform_admin'

/**
 * Navigation item definition.
 *
 * - `path` present for active routes (Phase 3 screens).
 * - `path` undefined for future-phase items (disable, show phase label).
 * - `phase` present → item belongs to a later phase, rendered disabled.
 * - `roles` → set of roles that can see this item.
 */
export interface NavigationItem {
  id: string
  label: string
  path?: string
  phase?: number
  icon: ElementType
  roles: Set<UserRole>
}

/**
 * Complete navigation registry.
 *
 * Rules (per wp_3_3_app_shell_spec.md §2):
 * - Dashboard: all authenticated roles (Phase 3)
 * - Supply Risk Analysis: production_manager, procurement_specialist, platform_admin (Phase 3)
 * - Knowledge Sources: ai_administrator, platform_admin (Phase 4)
 * - Workflow Runs: production_manager, procurement_specialist, ai_administrator, platform_admin (Phase 5)
 * - Approval Center: production_manager, procurement_specialist, platform_admin (Phase 6)
 * - Audit Log: auditor, platform_admin (Phase 6)
 * - Admin / Model Status: ai_administrator, platform_admin (Phase 7)
 * - Unknown or missing role: Dashboard only
 */
export const NAVIGATION_ITEMS: NavigationItem[] = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    path: '/',
    icon: LayoutDashboard,
    roles: new Set<UserRole>([
      'production_manager',
      'procurement_specialist',
      'ai_administrator',
      'auditor',
      'platform_admin',
    ]),
  },
  {
    id: 'supply-risk',
    label: 'Supply Risk Analysis',
    path: '/supply-risk',
    icon: ShieldAlert,
    roles: new Set<UserRole>([
      'production_manager',
      'procurement_specialist',
      'platform_admin',
    ]),
  },
  {
    id: 'knowledge',
    label: 'Knowledge Sources',
    phase: 4,
    icon: BookOpen,
    roles: new Set<UserRole>(['ai_administrator', 'platform_admin']),
  },
  {
    id: 'workflows',
    label: 'Workflow Runs',
    phase: 5,
    icon: Workflow,
    roles: new Set<UserRole>([
      'production_manager',
      'procurement_specialist',
      'ai_administrator',
      'platform_admin',
    ]),
  },
  {
    id: 'approvals',
    label: 'Approval Center',
    phase: 6,
    icon: CheckCircle2,
    roles: new Set<UserRole>([
      'production_manager',
      'procurement_specialist',
      'platform_admin',
    ]),
  },
  {
    id: 'audit',
    label: 'Audit Log',
    phase: 6,
    icon: FileText,
    roles: new Set<UserRole>(['auditor', 'platform_admin']),
  },
  {
    id: 'admin',
    label: 'Admin / Model Status',
    phase: 7,
    icon: Settings,
    roles: new Set<UserRole>(['ai_administrator', 'platform_admin']),
  },
]

/**
 * All canonical user roles.
 */
export const ALL_ROLES: UserRole[] = [
  'production_manager',
  'procurement_specialist',
  'ai_administrator',
  'auditor',
  'platform_admin',
]

/**
 * Platform admin role constant for clarity.
 */
export const PLATFORM_ADMIN_ROLE: UserRole = 'platform_admin'

/**
 * Human-readable role labels for display.
 */
export const ROLE_LABELS: Record<UserRole, string> = {
  production_manager: 'Production Manager',
  procurement_specialist: 'Procurement Specialist',
  ai_administrator: 'AI Administrator',
  auditor: 'Auditor',
  platform_admin: 'Platform Administrator',
}
