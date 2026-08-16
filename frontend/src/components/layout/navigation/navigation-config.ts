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
 * Canonical backend roles (DEC-052 M1). The unsupported ``platform_admin``
 * role has been removed from the Phase 6 authorization model; the union is
 * exactly the five canonical roles: PRODUCTION_MANAGER, PROCUREMENT_SPECIALIST,
 * ENGINEER, AI_ADMINISTRATOR, AUDITOR.
 */
export type UserRole =
  | 'production_manager'
  | 'procurement_specialist'
  | 'engineer'
  | 'ai_administrator'
  | 'auditor'

/**
 * Navigation item definition.
 *
 * - `path` present for active routes (Phase 3 / Phase 6 screens).
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
 * Rules (per wp_3_3_app_shell_spec.md §2, reconciled to DEC-052 M1):
 * - Dashboard: all authenticated roles (production_manager,
 *   procurement_specialist, engineer, ai_administrator, auditor)
 * - Supply Risk Analysis: production_manager, procurement_specialist (Phase 3)
 * - Knowledge Sources: ai_administrator (Phase 4)
 * - Workflow Runs: production_manager, procurement_specialist,
 *   ai_administrator (Phase 5)
 * - Approval Center: production_manager, procurement_specialist,
 *   ai_administrator (Phase 6 — active)
 * - Audit Log: auditor (Phase 6)
 * - Admin / Model Status: ai_administrator (Phase 7)
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
      'engineer',
      'ai_administrator',
      'auditor',
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
    ]),
  },
  {
    id: 'knowledge',
    label: 'Knowledge Sources',
    phase: 4,
    icon: BookOpen,
    roles: new Set<UserRole>(['ai_administrator']),
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
    ]),
  },
  {
    id: 'approvals',
    label: 'Approval Center',
    path: '/approval-center',
    icon: CheckCircle2,
    roles: new Set<UserRole>([
      'production_manager',
      'procurement_specialist',
      'ai_administrator',
    ]),
  },
  {
    id: 'audit',
    label: 'Audit Log',
    phase: 6,
    icon: FileText,
    roles: new Set<UserRole>(['auditor']),
  },
  {
    id: 'admin',
    label: 'Admin / Model Status',
    phase: 7,
    icon: Settings,
    roles: new Set<UserRole>(['ai_administrator']),
  },
]

/**
 * All canonical user roles.
 */
export const ALL_ROLES: UserRole[] = [
  'production_manager',
  'procurement_specialist',
  'engineer',
  'ai_administrator',
  'auditor',
]

/**
 * Human-readable role labels for display.
 */
export const ROLE_LABELS: Record<UserRole, string> = {
  production_manager: 'Production Manager',
  procurement_specialist: 'Procurement Specialist',
  engineer: 'Engineer',
  ai_administrator: 'AI Administrator',
  auditor: 'Auditor',
}
