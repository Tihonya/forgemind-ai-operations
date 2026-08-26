import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import Sidebar from './Sidebar'
import type { AuthUser } from '@/contexts/auth.context'
import i18n from '@/i18n'

function renderSidebar(user: AuthUser) {
  return render(
    <MemoryRouter>
      <Sidebar user={user} />
    </MemoryRouter>
  )
}

describe('Sidebar', () => {
  afterEach(() => {
    act(() => {
      void i18n.changeLanguage('uk')
    })
  })

  it('renders ForgeMind brand', () => {
    const user: AuthUser = {
      id: '1',
      username: 'test_user',
      display_name: 'Test User',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByText('ForgeMind')).toBeInTheDocument()
    expect(screen.getByText('Supply Risk Intelligence')).toBeInTheDocument()
  })

  it('renders user summary with displayName and localized role (uk default)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'manager',
      display_name: 'Manager User',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByText('Manager User')).toBeInTheDocument()
    expect(screen.getByText('Керівник виробництва')).toBeInTheDocument()
  })

  it('renders localized role labels in English after switching', () => {
    act(() => {
      void i18n.changeLanguage('en')
    })
    const user: AuthUser = {
      id: '1',
      username: 'manager',
      display_name: 'Manager User',
      roles: ['procurement_specialist'],
    }
    renderSidebar(user)
    expect(screen.getByText('Procurement Specialist')).toBeInTheDocument()
  })

  it('renders Ukrainian Dashboard label for production_manager (uk default)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-link-dashboard')).toHaveTextContent('Огляд')
    expect(screen.getByTestId('nav-link-dashboard')).toHaveAttribute('href', '/')
  })

  it('renders Ukrainian Supply Risk Analysis label for production_manager', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-link-supply-risk')).toHaveTextContent('Ризики постачання')
  })

  it('renders Workflow Runs for production_manager (disabled, localized marker)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-disabled-workflows')).toBeInTheDocument()
    expect(screen.getByTestId('nav-disabled-workflows')).toHaveTextContent('Запуски аналізу')
    expect(screen.getByTestId('nav-disabled-workflows')).toHaveTextContent('Незабаром')
  })

  it('renders Approval Center link for production_manager (active, localized)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-link-approvals')).toHaveTextContent('Центр погодження')
    expect(screen.getByTestId('nav-link-approvals')).toHaveAttribute('href', '/approval-center')
  })

  it('renders Approval Center link for procurement_specialist (active)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'ps',
      roles: ['procurement_specialist'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-link-approvals')).toBeInTheDocument()
  })

  it('does NOT render Knowledge Sources for production_manager', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.queryByTestId('nav-disabled-knowledge')).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-link-knowledge')).not.toBeInTheDocument()
  })

  it('does NOT render Audit Log link for production_manager', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.queryByTestId('nav-link-audit')).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-disabled-audit')).not.toBeInTheDocument()
  })

  it('renders Knowledge Sources (disabled) for ai_administrator with localized label', () => {
    const user: AuthUser = {
      id: '1',
      username: 'ai_admin',
      roles: ['ai_administrator'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-disabled-knowledge')).toBeInTheDocument()
    expect(screen.getByTestId('nav-disabled-knowledge')).toHaveTextContent('Джерела знань')
  })

  it('renders Audit Log link for auditor (active, localized)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'auditor',
      roles: ['auditor'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-link-audit')).toHaveTextContent('Журнал аудиту')
    expect(screen.getByTestId('nav-link-audit')).toHaveAttribute('href', '/audit-log')
  })

  it('renders Audit Log link for ai_administrator (active)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'ai_admin',
      roles: ['ai_administrator'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-link-audit')).toBeInTheDocument()
  })

  it('renders only Dashboard for engineer', () => {
    const user: AuthUser = {
      id: '1',
      username: 'engineer',
      roles: ['engineer'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-link-dashboard')).toBeInTheDocument()
    expect(screen.queryByTestId('nav-link-supply-risk')).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-disabled-approvals')).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-disabled-audit')).not.toBeInTheDocument()
  })

  it('renders only Dashboard for unknown role', () => {
    const user: AuthUser = {
      id: '1',
      username: 'unknown',
      roles: [],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-link-dashboard')).toBeInTheDocument()
    expect(screen.queryByTestId('nav-link-supply-risk')).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-link-audit')).not.toBeInTheDocument()
  })

  it('renders Admin / Model Status (disabled) for ai_administrator with Ukrainian label', () => {
    const user: AuthUser = {
      id: '1',
      username: 'ai_admin',
      roles: ['ai_administrator'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-disabled-admin')).toBeInTheDocument()
    expect(screen.getByTestId('nav-disabled-admin')).toHaveTextContent('Адміністрування')
  })

  it('merges multi-role navigation without duplicates', () => {
    const user: AuthUser = {
      id: '1',
      username: 'multi',
      roles: ['production_manager', 'auditor'],
    }
    renderSidebar(user)
    const links = screen.getAllByRole('link')
    const labels = links.map((l) => l.textContent)
    expect(new Set(labels).size).toBe(labels.length)
  })
})