/**
 * Unit tests for SeverityBadge component (WP-3.5; registry-backed since
 * WP-UX-UA-04).
 *
 * The active locale is pinned to English for label assertions (the same
 * pattern as the other WP-UX-UA-03 tests); Ukrainian exact-string coverage
 * lives in the registry test suite. The machine code is asserted through
 * ``data-code`` (never a translated attribute).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, beforeEach } from 'vitest';

import i18n from '@/i18n';
import { SeverityBadge } from '../SeverityBadge';

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

describe('SeverityBadge', () => {
  it('renders CRITICAL with the machine code preserved on data-code', () => {
    render(<SeverityBadge severity="CRITICAL" />);
    const badge = screen.getByTestId('severity-badge');
    expect(badge).toHaveTextContent('Critical');
    expect(badge).toHaveAttribute('data-code', 'CRITICAL');
    expect(badge).toHaveAttribute('data-domain', 'severity');
    expect(badge).toHaveAttribute('data-known', 'true');
  });

  it('renders HIGH', () => {
    render(<SeverityBadge severity="HIGH" />);
    const badge = screen.getByTestId('severity-badge');
    expect(badge).toHaveTextContent('High');
    expect(badge).toHaveAttribute('data-code', 'HIGH');
  });

  it('renders MEDIUM', () => {
    render(<SeverityBadge severity="MEDIUM" />);
    expect(screen.getByTestId('severity-badge')).toHaveTextContent('Medium');
  });

  it('renders LOW', () => {
    render(<SeverityBadge severity="LOW" />);
    expect(screen.getByTestId('severity-badge')).toHaveTextContent('Low');
  });

  it('renders an unknown severity with neutral styling and the preserved raw value', () => {
    render(<SeverityBadge severity="EXOTIC" />);
    const badge = screen.getByTestId('severity-badge');
    expect(badge).toHaveTextContent('Unknown status');
    expect(badge).toHaveTextContent('EXOTIC');
    expect(badge).toHaveAttribute('data-code', 'EXOTIC');
    expect(badge).toHaveAttribute('data-known', 'false');
  });

  it('renders empty severity as the neutral unknown presentation', () => {
    render(<SeverityBadge severity="" />);
    const badge = screen.getByTestId('severity-badge');
    expect(badge).toHaveTextContent('Unknown status');
    expect(badge).toHaveAttribute('data-known', 'false');
  });
});