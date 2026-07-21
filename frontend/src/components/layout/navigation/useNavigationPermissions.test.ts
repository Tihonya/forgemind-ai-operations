import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  useNavigationPermissions,
  normalizeRoles,
  filterNavigationForRoles,
} from './useNavigationPermissions'
import { NAVIGATION_ITEMS, type NavigationItem, type UserRole } from './navigation-config'

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

  it('normalizes UPPERCASE backend role codes to lowercase', () => {
    const result = normalizeRoles([
      'PRODUCTION_MANAGER',
      'PROCUREMENT_SPECIALIST',
      'AI_ADMINISTRATOR',
      'AUDITOR',
    ])
    expect(result.size).toBe(4)
    expect(result.has('production_manager')).toBe(true)
    expect(result.has('procurement_specialist')).toBe(true)
    expect(result.has('ai_administrator')).toBe(true)
    expect(result.has('auditor')).toBe(true)
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
    // 'UNKNOWN_ROLE' is not a valid UserRole, so it's filtered out (size check above)
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

  it('platform_admin sees all items', () => {
    const roles = new Set<UserRole>(['platform_admin'])
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, roles)
    expect(result).toHaveLength(NAVIGATION_ITEMS.length)
  })

  it('merges multiple roles into deduplicated union', () => {
    const roles = new Set<UserRole>(['production_manager', 'auditor'])
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, roles)
    const ids = result.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('audit')
    // No duplicates
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('ai_administrator sees Dashboard, Knowledge, Workflows, Admin', () => {
    const roles = new Set<UserRole>(['ai_administrator'])
    const result = filterNavigationForRoles(NAVIGATION_ITEMS, roles)
    const ids = result.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('knowledge')
    expect(ids).toContain('workflows')
    expect(ids).toContain('admin')
    expect(ids).not.toContain('supply-risk')
    expect(ids).not.toContain('audit')
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
      useNavigationPermissions(['production_manager'])
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
  })

  it('returns correct items for PRODUCTION_MANAGER (uppercase backend)', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['PRODUCTION_MANAGER'])
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
      useNavigationPermissions(['PROCUREMENT_SPECIALIST'])
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('workflows')
    expect(ids).toContain('approvals')
  })

  it('returns all items for platform_admin', () => {
    const { result } = renderHook(() => useNavigationPermissions(['platform_admin']))
    expect(result.current.navigationItems).toHaveLength(NAVIGATION_ITEMS.length)
  })

  it('deduplicates multi-role navigation', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['production_manager', 'auditor'])
    )
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('handles mixed uppercase and lowercase roles', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['PRODUCTION_MANAGER', 'auditor'])
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).toContain('dashboard')
    expect(ids).toContain('supply-risk')
    expect(ids).toContain('audit')
  })

  it('AI_ADMINISTRATOR does not see Supply Risk Analysis', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['AI_ADMINISTRATOR'])
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).not.toContain('supply-risk')
    expect(ids).toContain('dashboard')
    expect(ids).toContain('knowledge')
  })

  it('AUDITOR does not see Supply Risk Analysis', () => {
    const { result } = renderHook(() =>
      useNavigationPermissions(['AUDITOR'])
    )
    expect(result.current.unknownRole).toBe(false)
    const ids = result.current.navigationItems.map((i: NavigationItem) => i.id)
    expect(ids).not.toContain('supply-risk')
    expect(ids).toContain('dashboard')
    expect(ids).toContain('audit')
  })
})
