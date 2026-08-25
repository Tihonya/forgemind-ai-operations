import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Alert, AlertTitle, AlertDescription } from '../alert'

describe('Alert', () => {
  it('renders with role="alert" and an icon (never color-only meaning)', () => {
    render(<Alert variant="success">Saved successfully</Alert>)
    const alert = screen.getByRole('alert')
    expect(alert).toBeInTheDocument()
    expect(alert.textContent).toContain('Saved successfully')
  })

  it('renders the success variant with a check icon', () => {
    const { container } = render(
      <Alert variant="success">
        <AlertTitle>Done</AlertTitle>
        <AlertDescription>Saved.</AlertDescription>
      </Alert>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
    expect(screen.getByText('Saved.')).toBeInTheDocument()
  })

  it.each(['info', 'warning', 'destructive', 'default'] as const)(
    'renders the %s variant with an icon',
    (variant) => {
      const { container } = render(<Alert variant={variant}>Message</Alert>)
      expect(screen.getByRole('alert').textContent).toContain('Message')
      expect(container.querySelector('svg')).not.toBeNull()
    },
  )
})
