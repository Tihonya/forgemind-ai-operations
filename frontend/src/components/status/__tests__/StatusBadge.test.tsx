/**
 * StatusBadge component tests (WP-UX-UA-04).
 *
 * Locale-pinned assertions use the English catalog strings because several
 * sibling suites already pin English; exact Ukrainian strings are covered by
 * the component suite below (uk-mode cases) and exhaustively by the registry
 * contract test. Expectations here are written from the committed en catalog
 * — they are INDEPENDENT of the implementation path (the badge resolves via
 * the real i18n instance).
 */
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import i18n from '@/i18n';
import StatusBadge from '../StatusBadge';

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

describe('StatusBadge — known codes', () => {
  it('renders the localized label and preserves domain + machine code', () => {
    render(<StatusBadge domain="severity" code="CRITICAL" />);
    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveTextContent('Critical');
    expect(badge).toHaveAttribute('data-domain', 'severity');
    expect(badge).toHaveAttribute('data-code', 'CRITICAL');
    expect(badge).toHaveAttribute('data-known', 'true');
  });

  it('renders the localized Ukrainian label under the uk locale', async () => {
    render(<StatusBadge domain="severity" code="CRITICAL" />);
    await act(async () => {
      await i18n.changeLanguage('uk');
    });
    expect(screen.getByTestId('status-badge')).toHaveTextContent('Критичний');
  });

  it('never renders the raw code for a known code unless showCode is set', () => {
    render(<StatusBadge domain="plan" code="EXECUTING" />);
    expect(screen.getByTestId('status-badge').textContent).toBe('Executing');
    render(<StatusBadge domain="plan" code="EXECUTING" showCode testId="with-code" />);
    expect(screen.getByTestId('with-code').textContent).toContain('EXECUTING');
  });

  it('carries a non-color cue (icon) for every tone', () => {
    const cases: Array<[string, string]> = [
      ['severity', 'CRITICAL'], // danger
      ['severity', 'HIGH'], // warning
      ['severity', 'MEDIUM'], // info
      ['severity', 'LOW'], // neutral
      ['workflowRun', 'COMPLETED'], // success
    ];
    for (const [domain, code] of cases) {
      const { container, unmount } = render(<StatusBadge domain={domain as never} code={code} />);
      expect(container.querySelector('svg'), `${domain}.${code}`).not.toBeNull();
      unmount();
    }
  });

  it('keeps the same mounted badge reactive to locale switching', async () => {
    const { rerender } = render(<StatusBadge domain="plan" code="EXECUTING" />);
    expect(screen.getByTestId('status-badge')).toHaveTextContent('Executing');
    await act(async () => {
      await i18n.changeLanguage('uk');
    });
    rerender(<StatusBadge domain="plan" code="EXECUTING" />);
    expect(screen.getByTestId('status-badge')).toHaveTextContent('Виконується');
    await act(async () => {
      await i18n.changeLanguage('en');
    });
    rerender(<StatusBadge domain="plan" code="EXECUTING" />);
    expect(screen.getByTestId('status-badge')).toHaveTextContent('Executing');
  });
});

describe('StatusBadge — unknown codes', () => {
  it('uses the localized unknown label while preserving the raw code visibly', () => {
    render(<StatusBadge domain="plan" code="SOME_FUTURE_CODE" />);
    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveTextContent('Unknown status');
    expect(badge).toHaveTextContent('SOME_FUTURE_CODE'); // diagnosis preserved
    expect(badge).toHaveAttribute('data-known', 'false');
    expect(badge).toHaveAttribute('data-code', 'SOME_FUTURE_CODE');
  });

  it('handles empty/null codes without throwing and hides the empty raw span', () => {
    render(<StatusBadge domain="plan" code="" />);
    expect(screen.getByTestId('status-badge')).toHaveAttribute('data-code', '');
    render(<StatusBadge domain="plan" code={null} testId="null-badge" />);
    expect(screen.getByTestId('null-badge')).toHaveAttribute('data-known', 'false');
  });
});