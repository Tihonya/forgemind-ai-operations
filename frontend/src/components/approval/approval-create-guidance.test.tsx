import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import i18n from '@/i18n'
import { ApprovalCreateGuidance } from './approval-create-guidance'

beforeEach(async () => {
  localStorage.setItem('forgemind_locale', 'en')
  await i18n.changeLanguage('en')
})

describe('ApprovalCreateGuidance', () => {
  it('explains the recommendation-originated path with a link to risks', () => {
    render(
      <MemoryRouter>
        <ApprovalCreateGuidance />
      </MemoryRouter>,
    )
    expect(screen.getByText('How to create an approval request')).toBeInTheDocument()
    const cta = screen.getByTestId('guidance-cta')
    expect(cta.closest('a')).toHaveAttribute('href', '/supply-risk')
  })

  it('does not present a manual UUID input', () => {
    render(
      <MemoryRouter>
        <ApprovalCreateGuidance />
      </MemoryRouter>,
    )
    expect(screen.queryByTestId('create-recommendation-id')).not.toBeInTheDocument()
  })
})
