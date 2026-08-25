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
 * - `id` — stable internal identifier (routing/permissions/tests). NEVER
 *   translated, NEVER changed by localization work.
 * - `path` — present for active routes (Phase 3 / Phase 6 screens); the
 *   route PATH is machine content and unchanged by localization.
 * - `phase` — present → item belongs to a later phase, rendered disabled.
 * - `labelKey` — semantic catalog key (`shell.navigation.<id>`) resolved at
 *   render time via react-i18next (WP-UX-UA-01). The English literal
 *   remains available as the safe non-i18n fallback.
 * - `roles` — set of roles that can see this item (permission model
 *   unchanged).
 */
export interface NavigationItem {
  id: string
  labelKey: string
  /** English fallback label (used only outside an i18n context). */
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
 * - Audit Log: auditor, ai_administrator (Phase 6 — active)
 * - Admin / Model Status: ai_administrator (Phase 7)
 * - Unknown or missing role: Dashboard only
 */

/**
 * Roles permitted to open the Audit Log route (DEC-052 M1).
 *
 * This is the single source of truth for the client-side route boundary: the
 * Audit Log navigation item and the ``RequireRole`` route guard both derive
 * from it, so visibility and access cannot drift apart. The backend
 * ``_AUDIT_READ_ROLES`` remains the authoritative enforcement.
 */
export const AUDIT_READ_ROLES: ReadonlySet<UserRole> = new Set<UserRole>([
  'auditor',
  'ai_administrator',
])

export const NAVIGATION_ITEMS: NavigationItem[] = [
  {
    id: 'dashboard',
    labelKey: 'shell:navigation.dashboard',
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
    labelKey: 'shell:navigation.supplyRisks',
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
    labelKey: 'shell:navigation.knowledgeSources',
    label: 'Knowledge Sources',
    phase: 4,
    icon: BookOpen,
    roles: new Set<UserRole>(['ai_administrator']),
  },
  {
    id: 'workflows',
    labelKey: 'shell:navigation.workflowRuns',
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
    labelKey: 'shell:navigation.approvalCenter',
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
    labelKey: 'shell:navigation.auditLog',
    label: 'Audit Log',
    path: '/audit-log',
    icon: FileText,
    roles: new Set(AUDIT_READ_ROLES),
  },
  {
    id: 'admin',
    labelKey: 'shell:navigation.admin',
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
 * Semantic i18n keys for role display labels (WP-UX-UA-01).
 *
 * Machine role codes stay English and are never translated (product
 * language contract). Only the presentation layer maps codes → localized
 * labels through the catalog.
 */
export const ROLE_LABEL_KEYS: Record<UserRole, string> = {
  production_manager: 'shell:roleLabels.productionManager',
  procurement_specialist: 'shell:roleLabels.procurementSpecialist',
  engineer: 'shell:roleLabels.engineer',
  ai_administrator: 'shell:roleLabels.aiAdministrator',
  auditor: 'shell:roleLabels.auditor',
}

/**
 * Backward-compatible English role label map (non-i18n fallback and
 * pre-i18n consumers). Localized rendering uses ``ROLE_LABEL_KEYS`` through
 * the catalogs; this map keeps machine-code → English display parity for
 * any call site outside a React tree.
 */
export const ROLE_LABELS: Record<UserRole, string> = {
  production_manager: 'Production Manager',
  procurement_specialist: 'Procurement Specialist',
  engineer: 'Engineer',
  ai_administrator: 'AI Administrator',
  auditor: 'Auditor',
}