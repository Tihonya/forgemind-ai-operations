import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PageHeader } from '../page-header'
import { SectionHeader } from '../section-header'
import { KeyValue, KeyValueList } from '../key-value'
import { Container } from '../container'
import { IconButton } from '../icon-button'

describe('PageHeader', () => {
  it('renders an h1 title, purpose text, and optional action', () => {
    render(
      <PageHeader
        title="Операційний огляд"
        description="Короткий опис"
        action={<button type="button">Дія</button>}
      />,
    )
    expect(
      screen.getByRole('heading', { name: 'Операційний огляд', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByText('Короткий опис')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Дія' })).toBeInTheDocument()
  })
})

describe('SectionHeader', () => {
  it('renders an h2 title (preserves heading hierarchy under h1)', () => {
    render(<SectionHeader title="Потребує уваги зараз" />)
    expect(
      screen.getByRole('heading', { name: 'Потребує уваги зараз', level: 2 }),
    ).toBeInTheDocument()
  })
})

describe('KeyValue / KeyValueList', () => {
  it('renders a semantic dl/dt/dd metadata pair', () => {
    const { container } = render(
      <KeyValueList>
        <KeyValue label="Ідентифікатор">RISK-001</KeyValue>
      </KeyValueList>,
    )
    expect(container.querySelector('dl')).toBeInTheDocument()
    expect(screen.getByText('Ідентифікатор').tagName).toBe('DT')
    expect(screen.getByText('RISK-001').tagName).toBe('DD')
  })

  it('wraps long values (break-words) instead of overflowing', () => {
    const longValue = 'a'.repeat(120)
    render(<KeyValue label="ID">{longValue}</KeyValue>)
    expect(screen.getByText(longValue).className).toContain('break-words')
  })
})

describe('Container', () => {
  it('applies the wide content width by default', () => {
    const { container } = render(<Container>content</Container>)
    expect(container.firstChild).toHaveClass('max-w-content')
  })

  it('applies the narrow width when narrow is set', () => {
    const { container } = render(<Container narrow>content</Container>)
    expect(container.firstChild).toHaveClass('max-w-content-narrow')
  })
})

describe('IconButton', () => {
  it('renders a ≥44px icon button with an accessible name', () => {
    render(<IconButton label="Закрити меню" icon={<span>×</span>} />)
    const button = screen.getByRole('button', { name: 'Закрити меню' })
    expect(button.className).toContain('h-11')
    expect(button.className).toContain('w-11')
  })
})
