import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import NavigationItem from './NavigationItem'
import type { NavigationItem as NavigationItemType } from './navigation-config'

function createMockItem(overrides: Partial<NavigationItemType>): NavigationItemType {
  return {
    id: 'test',
    label: 'Test Item',
    icon: () => <span>icon</span>,
    roles: new Set(),
    ...overrides,
  } as NavigationItemType
}

describe('NavigationItem', () => {
  it('renders active route link with correct styling', () => {
    const item = createMockItem({ id: 'dashboard', label: 'Dashboard', path: '/' })
    render(
      <MemoryRouter initialEntries={['/']}>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    const link = screen.getByRole('link', { name: /dashboard/i })
    expect(link).toBeInTheDocument()
    expect(link.getAttribute('aria-current')).toBe('page')
  })

  it('renders inactive route link', () => {
    const item = createMockItem({ id: 'supply-risk', label: 'Supply Risk', path: '/supply-risk' })
    render(
      <MemoryRouter initialEntries={['/']}>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    const link = screen.getByRole('link', { name: /supply risk/i })
    expect(link).toBeInTheDocument()
    expect(link.getAttribute('aria-current')).toBeNull()
  })

  it('renders disabled future-phase module', () => {
    const item = createMockItem({
      id: 'knowledge',
      label: 'Knowledge Sources',
      phase: 4,
    })
    render(
      <MemoryRouter>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    const disabled = screen.getByTestId('nav-disabled-knowledge')
    expect(disabled).toBeInTheDocument()
    expect(disabled.getAttribute('aria-disabled')).toBe('true')
    expect(screen.getByText(/phase 4/i)).toBeInTheDocument()
  })

  it('prevents click on disabled future module', () => {
    const item = createMockItem({ id: 'workflows', label: 'Workflows', phase: 5 })
    render(
      <MemoryRouter>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    const disabled = screen.getByTestId('nav-disabled-workflows')
    disabled.click()
    // No navigation occurs (disabled is not a link)
    expect(disabled.tagName).toBe('DIV')
  })

  it('returns null if item has no path and no phase', () => {
    const item = createMockItem({ id: 'invalid' })
    const { container } = render(
      <MemoryRouter>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    expect(container.firstChild).toBeNull()
  })
})
