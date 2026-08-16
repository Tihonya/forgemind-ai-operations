import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SafeMetadata } from './audit-metadata-view'

describe('SafeMetadata', () => {
  it('renders null as a safe placeholder', () => {
    render(<SafeMetadata value={null} />)
    expect(screen.getByText('null')).toBeInTheDocument()
  })

  it('renders primitives verbatim', () => {
    render(
      <SafeMetadata
        value={{ string: 'hello', number: 42, boolean: true }}
      />,
    )
    expect(screen.getByText('hello')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('true')).toBeInTheDocument()
  })

  it('preserves the [REDACTED] sentinel verbatim', () => {
    render(<SafeMetadata value={{ api_key: '[REDACTED]', prompt: '[REDACTED]' }} />)
    const redacted = screen.getAllByText('[REDACTED]')
    expect(redacted).toHaveLength(2)
  })

  it('renders arrays', () => {
    render(<SafeMetadata value={{ tags: ['a', 'b', 'c'] }} />)
    expect(screen.getByText('a')).toBeInTheDocument()
    expect(screen.getByText('b')).toBeInTheDocument()
    expect(screen.getByText('c')).toBeInTheDocument()
  })

  it('renders nested objects', () => {
    render(
      <SafeMetadata
        value={{ outer: { inner: { leaf: 'value' } } }}
      />,
    )
    expect(screen.getByText('leaf:')).toBeInTheDocument()
    expect(screen.getByText('value')).toBeInTheDocument()
  })

  it('escapes HTML in values (no dangerous HTML injection)', () => {
    render(<SafeMetadata value={{ malicious: '<img src=x onerror=alert(1)>' }} />)
    const container = screen.getByTestId('audit-metadata')
    // The string is rendered as text, never as an actual <img> element.
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>')
  })

  it('does not crash on a deeply nested structure (bounded depth)', () => {
    // Build a value nested well beyond MAX_DEPTH.
    let deep: unknown = 'leaf'
    for (let i = 0; i < 50; i += 1) {
      deep = { nested: deep }
    }
    render(<SafeMetadata value={deep} />)
    expect(screen.getByTestId('audit-metadata')).toBeInTheDocument()
  })
})
