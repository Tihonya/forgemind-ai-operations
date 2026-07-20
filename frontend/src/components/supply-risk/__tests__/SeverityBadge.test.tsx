/**
 * Unit tests for SeverityBadge component (WP-3.5).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SeverityBadge } from '../SeverityBadge';

describe('SeverityBadge', () => {
  it('renders CRITICAL with correct data attribute', () => {
    render(<SeverityBadge severity="CRITICAL" />);
    const badge = screen.getByTestId('severity-badge');
    expect(badge).toHaveTextContent('CRITICAL');
    expect(badge).toHaveAttribute('data-severity', 'CRITICAL');
  });

  it('renders HIGH', () => {
    render(<SeverityBadge severity="HIGH" />);
    const badge = screen.getByTestId('severity-badge');
    expect(badge).toHaveTextContent('HIGH');
    expect(badge).toHaveAttribute('data-severity', 'HIGH');
  });

  it('renders MEDIUM', () => {
    render(<SeverityBadge severity="MEDIUM" />);
    expect(screen.getByTestId('severity-badge')).toHaveTextContent('MEDIUM');
  });

  it('renders LOW', () => {
    render(<SeverityBadge severity="LOW" />);
    expect(screen.getByTestId('severity-badge')).toHaveTextContent('LOW');
  });

  it('renders unknown severity with neutral styling and shows value', () => {
    render(<SeverityBadge severity="EXOTIC" />);
    const badge = screen.getByTestId('severity-badge');
    expect(badge).toHaveTextContent('EXOTIC');
    expect(badge).toHaveAttribute('data-severity', 'EXOTIC');
  });

  it('renders empty severity as UNKNOWN', () => {
    render(<SeverityBadge severity="" />);
    const badge = screen.getByTestId('severity-badge');
    expect(badge).toHaveTextContent('UNKNOWN');
  });
});
