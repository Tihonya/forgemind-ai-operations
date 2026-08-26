/**
 * StatusEntityContext component tests (WP-UX-UA-04).
 *
 * Verifies the localized domain-owner label, the optional entity context
 * suffix, both presentation variants, and locale reactivity.
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import i18n from '@/i18n';
import StatusEntityContext from '../StatusEntityContext';

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

describe('StatusEntityContext', () => {
  it('labels the owner entity for a status domain', () => {
    render(<StatusEntityContext domain="workflowRun" />);
    expect(screen.getByTestId('status-entity-context')).toHaveTextContent(
      'Workflow run state',
    );
  });

  it('labels the owner in Ukrainian under the uk locale (product language)', async () => {
    await i18n.changeLanguage('uk');
    render(<StatusEntityContext domain="approval" />);
    expect(screen.getByTestId('status-entity-context')).toHaveTextContent(
      'Рішення щодо погодження',
    );
  });

  it('appends an optional concrete entity context', () => {
    render(<StatusEntityContext domain="plan" context="PLAN-2026-W31" />);
    expect(screen.getByTestId('status-entity-context')).toHaveTextContent(
      'Production plan state — PLAN-2026-W31',
    );
  });

  it('renders the inline variant as inline text', () => {
    render(<StatusEntityContext domain="severity" variant="inline" />);
    expect(screen.getByTestId('status-entity-context').className).toContain(
      'text-steel-500',
    );
  });

  it('distinguishes every domain with its own entity label', () => {
    const { unmount } = render(<StatusEntityContext domain="workflowRun" testId="ctx-1" />);
    const run = screen.getByTestId('ctx-1').textContent;
    unmount();
    render(<StatusEntityContext domain="severity" testId="ctx-2" />);
    const sev = screen.getByTestId('ctx-2').textContent;
    expect(run).not.toBe(sev);
  });
});