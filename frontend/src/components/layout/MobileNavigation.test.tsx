import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import MobileNavigation from './MobileNavigation'
import type { AuthUser } from '@/contexts/auth.context'
import i18n from '@/i18n'

const user: AuthUser = {
  id: '1',
  username: 'manager',
  display_name: 'Manager User',
  roles: ['production_manager'],
}

describe('MobileNavigation', () => {
  afterEach(() => {
    act(() => {
      void i18n.changeLanguage('uk')
    })
  })

  function renderDrawer(open = true) {
    const returnFocusRef = { current: null }
    const onClose = vi.fn()
    const onLogout = vi.fn()
    render(
      <MemoryRouter initialEntries={['/']}>
        <MobileNavigation
          open={open}
          onClose={onClose}
          user={user}
          onLogout={onLogout}
          returnFocusRef={returnFocusRef}
        />
      </MemoryRouter>
    )
    return { onClose, onLogout }
  }

  it('renders nothing when closed', () => {
    const { container } = render(
      <MemoryRouter>
        <MobileNavigation
          open={false}
          onClose={vi.fn()}
          user={user}
          onLogout={vi.fn()}
          returnFocusRef={{ current: null }}
        />
      </MemoryRouter>
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders role-aware navigation with localized labels (uk default)', () => {
    renderDrawer()
    expect(screen.getByTestId('nav-link-dashboard')).toHaveTextContent('Огляд')
    expect(screen.getByTestId('nav-link-supply-risk')).toHaveTextContent('Ризики постачання')
    expect(screen.queryByTestId('nav-link-audit')).not.toBeInTheDocument()
  })

  it('preserves disabled-item behavior for future-phase modules', () => {
    const aiAdmin: AuthUser = {
      id: '2',
      username: 'ai_admin',
      roles: ['ai_administrator'],
    }
    render(
      <MemoryRouter>
        <MobileNavigation
          open
          onClose={vi.fn()}
          user={aiAdmin}
          onLogout={vi.fn()}
          returnFocusRef={{ current: null }}
        />
      </MemoryRouter>
    )
    expect(screen.getByTestId('nav-disabled-knowledge')).toBeInTheDocument()
    expect(screen.getByTestId('nav-disabled-knowledge')).toHaveAttribute('aria-disabled', 'true')
  })

  it('shows user identity, role label and sign-out inside the surface', () => {
    renderDrawer()
    expect(screen.getByTestId('mobile-user-summary')).toHaveTextContent('Manager User')
    expect(screen.getByTestId('mobile-user-summary')).toHaveTextContent('Керівник виробництва')
    expect(screen.getByTestId('mobile-menu-logout')).toBeInTheDocument()
  })

  it('closes via Escape key', () => {
    const { onClose } = renderDrawer()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('closes when a navigation link is activated', () => {
    const { onClose } = renderDrawer()
    fireEvent.click(screen.getByTestId('nav-link-supply-risk'))
    expect(onClose).toHaveBeenCalled()
  })

  it('focus returns to the trigger after close (effect contract)', () => {
    const trigger = { focus: vi.fn(), tabIndex: 0 } as unknown as HTMLElement
    const returnFocusRef = { current: trigger }
    const { rerender } = render(
      <MemoryRouter>
        <MobileNavigation
          open
          onClose={vi.fn()}
          user={user}
          onLogout={vi.fn()}
          returnFocusRef={returnFocusRef}
        />
      </MemoryRouter>
    )
    rerender(
      <MemoryRouter>
        <MobileNavigation
          open={false}
          onClose={vi.fn()}
          user={user}
          onLogout={vi.fn()}
          returnFocusRef={returnFocusRef}
        />
      </MemoryRouter>
    )
    expect(trigger.focus).toHaveBeenCalled()
  })

  it('calls onLogout from the sign-out action', () => {
    const { onLogout } = renderDrawer()
    fireEvent.click(screen.getByTestId('mobile-menu-logout'))
    expect(onLogout).toHaveBeenCalled()
  })
})