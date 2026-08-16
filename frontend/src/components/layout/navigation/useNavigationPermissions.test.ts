import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  useNavigationPermissions,
  normalizeRoles,
  filterNavigationForRoles,
} from './useNavigationPermissions'
import {
  ALL_ROLES,
  NAVIGATION_ITEMS,
  type NavigationItem,
  type UserRole,
} from './navigation-config'

describe('normalizeRoles', () => {
  it('returns empty set for undefined', () => {
    const result = normalizeRoles(undefined)
    expect(result.size).toBe(0)
  })

  it('returns empty set for empty array', () => {
    const result = normalizeRoles([])
    expect(result.size).toBe(0)
  })

  it('filters out unknown roles', () => {
    const result = normalizeRoles(['production_manager', 'unknown_role', 'auditor'])
    expect(result.size).toBe(2)
    expect(result.has('production_manager')).toBe(true)
    expect(result.has('auditor')).toBe(true)
  })

  it('normalizes valid roles', () => {
    const result = normalizeRoles(['ai_administrator'])
    expect(result.size).toBe(1)
    expect(result.has('ai_administrator')).toBe(true)
  })

  it('normalizes UPPERCASE backend role codes to lowercase (all five canonical roles)', () => {
    const result = normalizeRoles([
      'PRODUCTION_MANAGER',
      'PROCUREMENT_SPECIALIST',
      'ENGINEER',
      'AI_ADMINISTRATOR',
      'AUDITOR',
    ])
    expect(result.size).toBe(5)
    expect(result.has('production_manager')).toBe(true)
    expect(result.has('procurement_specialist')).toBe(true)
    expect(result.has('engineer')).toBe(true)
    expect(result.has('ai_administrator')).toBe(true)
    expect(result.has('auditor')).toBe(true)
  })

  it('filters out the removed platform_admin role as unknown', () => {
    const result = normalizeRoles(['platform_admin'])
    expect(result.size).toBe(0)
  })

  it('handles mixed case roles defensively', () => {
    const result = normalizeRoles(['Production_Manager', 'PROCUREMENT_specialist'])
    expect(result.size).toBe(2)
    expect(result.has('production_manager')).toBe(true)
    expect(result.has('procurement_specialist')).toBe(true)
  })

  it('handles roles with leading/trailing whitespace', () => {
    const result = normalizeRoles(['  PRODUCTION_MANAGER  ', ' auditor '])
    expect(result.size).toBe(2)
    expect(result.has('production_manager')).toBe(true)
    expect(result.has('auditor')).toBe(true)
  })

  it('filters out unknown UPPERCASE roles', () => {
    const result = normalizeRoles(['PRODUCTION_MANAGER', 'UNKNOWN_ROLE', 'AUDITOR'])
    expect(result.size).toBe(2)
    expect(result.has('production_manager')).toBe(true)
    expect(result.has('auditor')).toBe(true)
  })
})

describe('ALL_ROLES', () => {
  it('contains exactly the five canonical roles', () => {
    expect(ALL_ROLES).toEqual([
      'production_manager',
      'procurement_specialist',
      'engineer',
      'ai_administrator',
      'auditor',
    ])
  })
})

describe('NAVIGATION_ITEMS', () => {
  it('no navigation item references the removed platform_admin role', () => {
    for (const item of NAVIGATION_ITEMS) {
      const roleCodes = Array.from(item.roles) as string[]
      expect(roleCodes).not.toContain('platform_admin')
    }
  })

  it('Approval Center navigation item is active (has a path, no phase)', () => {
    const approvals = NAVIGATION_ITEMS.find((item) => item.id === 'approvals')
    expect(approvals).toBeDefined()
    expect(approvals?.path).toBe('/approval-center')
    expect(approvals?.phase).toBeUndefined()
  })

  it('Audit Log navigation item is active (has a path, no phase) for auditor and ai_administrator', () => {
    const audit = NAVIGATION_ITEMS.find((item) => item.id === 'audit')
    expect(audit).toBeDefined()
    expect(audit?.path).toBe('/audit-log')
    expect(audit?.phase).toBeUndefined()
    expect(Array.from(audit?.roles ?? [])).toEqual(
      expect.arrayContaining(['auditor', 'ai_administrator']),
    )
    expect(Array.from(audit?.roles ?? [])).toHaveLength(2)
  })
})

describe('filterNavigationForRoles', () => {
  it('returns only Dashboard for unknown role', () => {
    const emptyRoles = new Set<UserRole>()
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, emptyRoles)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('dashboard')
  })

  it('production_manager sees expected items', () => {
    const roles = new Set<UserRole>(['production_manager'])
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, roles)
    const ids = result.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('workflows')
    expect(ids).toContain('approvals')
    expect(ids).not.toContain('knowledge')
    expect(ids).not.toContain('audit')
    expect(ids).not.toContain('admin')
  })

  it('auditor sees Dashboard and Audit Log only', () => {
    const roles = new Set<UserRole>(['auditor'])
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, roles)
    const ids = result.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('audit')
    expect(ids).not.toContain('supply-risk')
    expect(ids).not.toContain('workflows')
    expect(ids).not.toContain('approvals')
  })

  it('engineer sees Dashboard only', () => {
    const roles = new Set<UserRole>(['engineer'])
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, roles)
    const ids = result.map((i: NavigationItem) => i.id)
    expect(ids).toEqual(['dashboard'])
  })

  it('merges multiple roles into deduplicated union', () => {
    const roles = new Set<UserRole>(['production_manager', 'auditor'])
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, roles)
    const ids = result.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('audit')
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('ai_administrator sees Dashboard, Knowledge, Workflows, Approvals, Audit Log, Admin', () => {
    const roles = new Set<UserRole>(['ai_administrator'])
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, roles)
    const ids = result.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('knowledge')
    expect(ids).toContain('workflows')
    expect(ids).toContain('approvals')
    expect(ids).toContain('audit')
    expect(ids).toContain('admin')
    expect(ids).not.toContain('supply-risk')
  })

  it('procurement_specialist sees Dashboard, Supply Risk, Workflows, Approvals', () => {
    const roles = new Set<UserRole>(['procurement_specialist'])
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, roles)
    const ids = result.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('workflows')
    expect(ids).toContain('approvals')
    expect(ids).not.toContain('knowledge')
    expect(ids).not.toContain('audit')
    expect(ids).not.toContain('admin')
  })
})

describe('useNavigationPermissions hook', () => {
  it('returns Dashboard only for unknown roles', () => {
    const { result } = renderHook(() => useNavigationPermissions(undefined))
    expect(result.current.unknownRole).toBe(true)
    expect(result.current.navigationItems).toHaveLength(1)
    expect(result.current.navigationItems[0].id).toBe('dashboard')
  })

  it('returns correct items for production_manager', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['production_manager']),
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('approvals')
  })

  it('returns correct items for PRODUCTION_MANAGER (uppercase backend)', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['PRODUCTION_MANAGER']),
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('workflows')
    expect(ids).toContain('approvals')
  })

  it('returns correct items for PROCUREMENT_SPECIALIST (uppercase backend)', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['PROCUREMENT_SPECIALIST']),
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('workflows')
    expect(ids).toContain('approvals')
  })

  it('returns Dashboard only for ENGINEER (uppercase backend)', () => {
    const { result } = renderHook(() => useNavigationPermissions(['ENGINEER']))
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).toEqual(['dashboard'])
  })

  it('treats platform_admin as unknown (Dashboard only)', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['platform_admin']),
    )
    expect(result.current.unknownRole).toBe(true)
    expect(result.current.navigationItems).toHaveLength(1)
    expect(result.current.navigationItems[0].id).toBe('dashboard')
  })

  it('deduplicates multi-role navigation', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['production_manager', 'auditor']),
    )
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('handles mixed uppercase and lowercase roles', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['PRODUCTION_MANAGER', 'auditor']),
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('audit')
  })

  it('AI_ADMINISTRATOR sees Approvals and Audit Log (administrative read)', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['AI_ADMINISTRATOR']),
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).toContain('approvals')
    expect(ids).toContain('audit')
    expect(ids).not.toContain('supply-risk')
  })

  it('AUDITOR does not see Supply Risk Analysis or Approvals', () => {
    const { result } = renderHook(() => useNavigationPermissions(['AUDITOR']))
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).not.toContain('supply-risk')
    expect(ids).not.toContain('approvals')
    expect(ids).toContain('dashboard')
    expect(ids).toContain('audit')
  })

  // AT-005 role visibility regression per spec
  it('Production Manager and Procurement Specialist see Supply Risk Analysis (uppercase backend codes)', () => {
    const pm = renderHook(() => useNavigationPermissions(['PRODUCTION_MANAGER']))
    const ps = renderHook(() => useNavigationPermissions(['PROCUREMENT_SPECIALIST']))
    expect(pm.result.current.navigationItems.map((i) => i.id)).toContain('supply-risk')
    expect(ps.result.current.navigationItems.map((i) => i.id)).toContain('supply-risk')
  })

  it('AI Administrator and Auditor do not see Supply Risk Analysis (uppercase backend codes)', () => {
    const ai = renderHook(() => useNavigationPermissions(['AI_ADMINISTRATOR']))
    const aud = renderHook(() => useNavigationPermissions(['AUDITOR']))
    expect(ai.result.current.navigationItems.map((i) => i.id)).not.toContain('supply-risk')
    expect(aud.result.current.navigationItems.map((i) => i.id)).not.toContain('supply-risk')
  })
})
