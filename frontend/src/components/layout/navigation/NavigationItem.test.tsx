import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import NavigationItem from './NavigationItem'
import type { NavigationItem as NavigationItemType } from './navigation-config'
import i18n from '@/i18n'

function createMockItem(overrides: Partial<NavigationItemType>): NavigationItemType {
  return {
    id: 'test',
    labelKey: 'shell:navigation.dashboard',
    label: 'Dashboard',
    icon: () => <span>icon</span>,
    roles: new Set(),
    ...overrides,
  } as NavigationItemType
}

describe('NavigationItem', () => {
  afterEach(() => {
    act(() => {
      void i18n.changeLanguage('uk')
    })
  })

  it('renders active route link with correct styling', () => {
    const item = createMockItem({ id: 'dashboard', path: '/' })
    render(
      <MemoryRouter initialEntries={['/']}>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    const link = screen.getByTestId('nav-link-dashboard')
    expect(link).toBeInTheDocument()
    expect(link.getAttribute('aria-current')).toBe('page')
  })

  it('renders inactive route link', () => {
    const item = createMockItem({
      id: 'supply-risk',
      labelKey: 'shell:navigation.supplyRisks',
      label: 'Supply Risk',
      path: '/supply-risk',
    })
    render(
      <MemoryRouter initialEntries={['/']}>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    const link = screen.getByTestId('nav-link-supply-risk')
    expect(link).toBeInTheDocument()
    expect(link.getAttribute('aria-current')).toBeNull()
  })

  it('renders disabled future-phase module with localized label and marker (uk default)', () => {
    const item = createMockItem({
      id: 'knowledge',
      labelKey: 'shell:navigation.knowledgeSources',
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
    expect(disabled).toHaveTextContent('Джерела знань')
    expect(disabled).toHaveTextContent('Фаза 4')
  })

  it('renders phase marker in English after switching', () => {
    act(() => {
      void i18n.changeLanguage('en')
    })
    const item = createMockItem({
      id: 'knowledge',
      labelKey: 'shell:navigation.knowledgeSources',
      label: 'Knowledge Sources',
      phase: 4,
    })
    render(
      <MemoryRouter>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    const disabled = screen.getByTestId('nav-disabled-knowledge')
    expect(disabled).toHaveTextContent('Knowledge Sources')
    expect(disabled).toHaveTextContent('Phase 4')
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

  it('falls back to the stable English label when no i18n key resolves', () => {
    const item = createMockItem({
      id: 'custom',
      labelKey: 'shell:navigation.notARealKey',
      label: 'Custom Item',
      path: '/custom',
    })
    render(
      <MemoryRouter>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    expect(screen.getByText('Custom Item')).toBeInTheDocument()
  })

  it('returns null if item has no path and no phase', () => {
    const item = createMockItem({ id: 'invalid', phase: undefined, path: undefined })
    const { container } = render(
      <MemoryRouter>
        <NavigationItem item={item} />
      </MemoryRouter>
    )
    expect(container.firstChild).toBeNull()
  })
})