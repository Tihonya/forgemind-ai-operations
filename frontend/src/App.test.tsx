import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App', () => {
  it('renders through providers and shows root route', () => {
    render(<App />)
    expect(screen.getByText('ForgeMind')).toBeInTheDocument()
    expect(screen.getByText('Phase 3.1 scaffold ready')).toBeInTheDocument()
  })

  it('renders not-found state for unknown route', () => {
    window.history.pushState({}, 'Unknown page', '/nonexistent-path')
    render(<App />)
    expect(screen.getByText('404')).toBeInTheDocument()
    expect(screen.getByText('Page not found')).toBeInTheDocument()
  })
})
