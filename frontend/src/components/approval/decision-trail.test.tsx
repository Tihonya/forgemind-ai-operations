import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import i18n from '@/i18n'
import { DecisionTrail } from './decision-trail'
import { shortRef } from '@/lib/references'
import type { ProcurementTaskResponse } from '@/lib/procurement-api'

beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})

function task(overrides: Partial<ProcurementTaskResponse> = {}): ProcurementTaskResponse {
  return {
    id: '99999999-8888-7777-6666-555555555555',
    correlation_id: '11111111-2222-3333-4444-555555555555',
    approval_request_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    recommendation_id: '22222222-3333-4444-5555-666666666666',
    workflow_run_id: '33333333-4444-5555-6666-777777777777',
    risk_id: 'RISK-001',
    action_type: 'CREATE_PROCUREMENT_TASK',
    component_code: 'CTRL-X4',
    quantity: '250',
    binding_hash: 'a'.repeat(64),
    task_state: 'CREATED',
    requested_by: '44444444-5555-6666-7777-888888888888',
    requested_by_username: 'manager.demo',
    approved_by: '55555555-6666-7777-8888-999999999999',
    approved_by_username: 'procurement.demo',
    created_at: '2026-08-15T11:00:00Z',
    ...overrides,
  }
}

function renderTrail(props: Partial<Parameters<typeof DecisionTrail>[0]> = {}) {
  return render(
    <MemoryRouter>
      <DecisionTrail
        riskId="RISK-001"
        workflowRunId="33333333-4444-5555-6666-777777777777"
        recommendationId="22222222-3333-4444-5555-666666666666"
        correlationId="11111111-2222-3333-4444-555555555555"
        approvalStatus="PENDING"
        approvalRequestId="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        {...props}
      />
    </MemoryRouter>,
  )
}

describe('shortRef', () => {
  it('derives a prefixed short reference from a UUID', () => {
    expect(shortRef('REC', '22222222-3333-4444-5555-666666666666')).toBe('REC-22222222')
  })

  it('returns a bare short reference for an empty prefix', () => {
    expect(shortRef('', '11111111-2222-3333-4444-555555555555')).toBe('11111111')
  })

  it('returns an em dash for a missing id', () => {
    expect(shortRef('REC', null)).toBe('—')
  })
})

describe('DecisionTrail', () => {
  it('renders all six stages', () => {
    renderTrail()
    for (const stage of ['risk', 'analysis', 'recommendation', 'approval', 'task', 'audit']) {
      expect(screen.getByTestId(`trail-ref-${stage}`)).toBeInTheDocument()
    }
  })

  it('links the risk stage back to its risk detail', () => {
    renderTrail()
    expect(screen.getByTestId('trail-link-risk')).toHaveAttribute(
      'href',
      '/supply-risk/RISK-001',
    )
  })

  it('links the analysis stage to its workflow run', () => {
    renderTrail()
    expect(screen.getByTestId('trail-link-analysis')).toHaveAttribute(
      'href',
      '/workflow-runs/33333333-4444-5555-6666-777777777777',
    )
  })

  it('marks the approval stage as current', () => {
    renderTrail()
    expect(screen.getByTestId('trail-current-approval')).toBeInTheDocument()
  })

  it('shows an honest "not created" state for the task stage when no task exists', () => {
    renderTrail()
    expect(screen.getByTestId('trail-ref-task')).toHaveTextContent('Not created yet')
  })

  it('shows the task reference when a procurement task is present', () => {
    renderTrail({ procurementTask: task() })
    expect(screen.getByTestId('trail-ref-task')).toHaveTextContent('TASK-99999999')
  })

  it('does not link the audit stage when the role cannot view the audit log', () => {
    renderTrail({ canViewAudit: false })
    expect(screen.queryByTestId('trail-link-audit')).not.toBeInTheDocument()
    expect(screen.getByTestId('trail-unavailable-audit')).toBeInTheDocument()
  })

  it('links the audit stage to the correlation-filtered audit log when authorized', () => {
    renderTrail({ canViewAudit: true })
    expect(screen.getByTestId('trail-link-audit')).toHaveAttribute(
      'href',
      '/audit-log?correlation_id=11111111-2222-3333-4444-555555555555',
    )
  })
})
