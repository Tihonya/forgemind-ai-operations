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

  it('suppresses binding_hash keys and values at every nesting level', () => {
    const hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    const { container } = render(
      <SafeMetadata
        value={{
          action_type: 'CREATE_PROCUREMENT_TASK',
          binding_hash: hash,
          after: { bindingHash: hash, status: 'APPROVED' },
          nested: { deep: { 'binding-hash': hash, ok: true } },
          items: [{ binding_hash: hash, quantity: '250' }],
          redacted: '[REDACTED]',
        }}
      />,
    )
    const text = container.textContent ?? ''
    expect(text).not.toContain('binding_hash')
    expect(text).not.toContain('bindingHash')
    expect(text).not.toContain('binding-hash')
    expect(text).not.toContain(hash)
  })

  it('still renders safe metadata adjacent to suppressed binding_hash entries', () => {
    const hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    render(
      <SafeMetadata
        value={{
          action_type: 'CREATE_PROCUREMENT_TASK',
          binding_hash: hash,
          approval_request_id: 'req-1',
          component_code: 'CTRL-X4',
          quantity: '250',
          reason: 'sufficient',
        }}
      />,
    )
    expect(screen.getByText('action_type:')).toBeInTheDocument()
    expect(screen.getByText('CREATE_PROCUREMENT_TASK')).toBeInTheDocument()
    expect(screen.getByText('approval_request_id:')).toBeInTheDocument()
    expect(screen.getByText('req-1')).toBeInTheDocument()
    expect(screen.getByText('component_code:')).toBeInTheDocument()
    expect(screen.getByText('CTRL-X4')).toBeInTheDocument()
    expect(screen.getByText('quantity:')).toBeInTheDocument()
    expect(screen.getByText('250')).toBeInTheDocument()
    expect(screen.getByText('reason:')).toBeInTheDocument()
    expect(screen.getByText('sufficient')).toBeInTheDocument()
  })

  it('preserves [REDACTED] values alongside suppressed binding_hash entries', () => {
    const hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    const { container } = render(
      <SafeMetadata value={{ api_key: '[REDACTED]', binding_hash: hash }} />,
    )
    expect(screen.getByText('[REDACTED]')).toBeInTheDocument()
    expect(container.textContent).not.toContain('binding_hash')
    expect(container.textContent).not.toContain(hash)
  })
})
