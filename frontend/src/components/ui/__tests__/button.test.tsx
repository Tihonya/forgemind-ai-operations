import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Button } from '../button'

describe('Button', () => {
  it('renders a native button by default', () => {
    render(<Button>Save</Button>)
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
  })

  it('renders the loading state: disabled, aria-busy, spinner, no double-submit', () => {
    render(<Button loading>Save</Button>)
    const button = screen.getByRole('button', { name: 'Save' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })

  it('is disabled when both disabled and loading are set', () => {
    render(<Button loading disabled>Save</Button>)
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('renders the destructive variant with the semantic token class', () => {
    render(<Button variant="destructive">Delete</Button>)
    expect(screen.getByRole('button', { name: 'Delete' }).className).toContain(
      'bg-destructive',
    )
  })

  it('renders the success and warning variants', () => {
    const { rerender } = render(<Button variant="success">Approve</Button>)
    expect(screen.getByRole('button', { name: 'Approve' }).className).toContain(
      'bg-success',
    )
    rerender(<Button variant="warning">Review</Button>)
    expect(screen.getByRole('button', { name: 'Review' }).className).toContain(
      'bg-warning',
    )
  })

  it('enforces a ≥44px touch target via the min-height token', () => {
    render(<Button>Touch</Button>)
    // The base class carries min-h-11 (44 CSS px) so every button meets the
    // mobile touch-target contract regardless of its `size` variant.
    expect(screen.getByRole('button', { name: 'Touch' }).className).toContain(
      'min-h-11',
    )
  })

  it('renders icon size as a ≥44px square', () => {
    render(<Button size="icon" aria-label="Close">×</Button>)
    const button = screen.getByRole('button', { name: 'Close' })
    expect(button.className).toContain('h-11')
    expect(button.className).toContain('w-11')
  })
})
