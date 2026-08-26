import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'

import i18n from '@/i18n'
import { TraceCategoryBadge } from './trace-category-badge'

beforeEach(async () => {
  await i18n.changeLanguage('en')
})

const KNOWN_CATEGORIES: Record<string, string> = {
  user_action: 'User action',
  deterministic_calculation: 'Deterministic calculation',
  retrieval: 'Retrieval',
  model_call: 'Model call',
  structured_validation: 'Structured validation',
  recommendation: 'Recommendation',
  approval_request: 'Approval request',
  human_decision: 'Human decision',
  write_action: 'Write action',
}

describe('TraceCategoryBadge', () => {
  it('renders a readable label for every known category', () => {
    for (const [category, label] of Object.entries(KNOWN_CATEGORIES)) {
      const { unmount } = render(<TraceCategoryBadge category={category} />)
      expect(screen.getByTestId('trace-category-badge')).toBeInTheDocument()
      expect(screen.getByText(label)).toBeInTheDocument()
      expect(screen.getByTestId('trace-category-badge')).toHaveAttribute(
        'data-category',
        category,
      )
      unmount()
    }
  })

  it('falls back to the raw value for an unknown category', () => {
    render(<TraceCategoryBadge category="some_unknown_category" />)
    expect(screen.getByText('some_unknown_category')).toBeInTheDocument()
  })
})
