import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import Sidebar from './Sidebar'
import type { AuthUser } from '@/contexts/auth.context'

function renderSidebar(user: AuthUser) {
  return render(
    <MemoryRouter>
      <Sidebar user={user} />
    </MemoryRouter>
  )
}

describe('Sidebar', () => {
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

  it('renders user summary with displayName and role', () => {
    const user: AuthUser = {
      id: '1',
      username: 'admin',
      display_name: 'Admin User',
      roles: ['platform_admin'],
    }
    renderSidebar(user)
    expect(screen.getByText('Admin User')).toBeInTheDocument()
    expect(screen.getByText('Platform Administrator')).toBeInTheDocument()
  })

  it('renders Dashboard for production_manager', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument()
  })

  it('renders Supply Risk Analysis for production_manager', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByRole('link', { name: /supply risk/i })).toBeInTheDocument()
  })

  it('renders Workflow Runs for production_manager (disabled)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-disabled-workflows')).toBeInTheDocument()
  })

  it('renders Approval Center for production_manager (disabled)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-disabled-approvals')).toBeInTheDocument()
  })

  it('does NOT render Knowledge Sources for production_manager', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    expect(screen.queryByRole('link', { name: /knowledge sources/i })).not.toBeInTheDocument()
  })

  it('does NOT render Audit Log link for production_manager', () => {
    const user: AuthUser = {
      id: '1',
      username: 'pm',
      roles: ['production_manager'],
    }
    renderSidebar(user)
    // Audit log is a future module, should not be visible for production_manager
    expect(screen.queryByRole('link', { name: /audit log/i })).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-disabled-audit')).not.toBeInTheDocument()
  })

  it('renders Knowledge Sources for ai_administrator', () => {
    const user: AuthUser = {
      id: '1',
      username: 'ai_admin',
      roles: ['ai_administrator'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-disabled-knowledge')).toBeInTheDocument()
  })

  it('renders Audit Log for auditor (disabled)', () => {
    const user: AuthUser = {
      id: '1',
      username: 'auditor',
      roles: ['auditor'],
    }
    renderSidebar(user)
    expect(screen.getByTestId('nav-disabled-audit')).toBeInTheDocument()
  })

  it('renders all items for platform_admin', () => {
    const user: AuthUser = {
      id: '1',
      username: 'platform_admin',
      roles: ['platform_admin'],
    }
    renderSidebar(user)
    // Active routes (dashboard)
    expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /supply risk/i })).toBeInTheDocument()
    // Future modules (disabled)
    expect(screen.getByTestId('nav-disabled-knowledge')).toBeInTheDocument()
    expect(screen.getByTestId('nav-disabled-workflows')).toBeInTheDocument()
    expect(screen.getByTestId('nav-disabled-approvals')).toBeInTheDocument()
    expect(screen.getByTestId('nav-disabled-audit')).toBeInTheDocument()
    expect(screen.getByTestId('nav-disabled-admin')).toBeInTheDocument()
  })

  it('renders only Dashboard for unknown role', () => {
    const user: AuthUser = {
      id: '1',
      username: 'unknown',
      roles: [],
    }
    renderSidebar(user)
    expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /supply risk/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /audit log/i })).not.toBeInTheDocument()
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
