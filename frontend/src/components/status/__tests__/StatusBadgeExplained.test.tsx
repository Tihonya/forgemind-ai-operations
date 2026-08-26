/**
 * StatusBadgeExplained component tests (WP-UX-UA-04).
 *
 * Interaction contract: the trigger is a REAL button with a ≥44×44 touch
 * wrap — focusable, keyboard-operable, click/tap-togglable; hover is NOT
 * required (the explanation is a tap-reachable popover, not a hover-only
 * tooltip). Escape closes and the trigger keeps focus. Unknown codes keep
 * the raw machine code inside the popover for diagnosis.
 */
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import i18n from '@/i18n';
import StatusBadgeExplained from '../StatusBadgeExplained';

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

describe('StatusBadgeExplained', () => {
  it('renders the localized badge inside a button trigger named by the label', () => {
    render(<StatusBadgeExplained domain="severity" code="CRITICAL" />);
    const trigger = screen.getByRole('button', { name: /Critical/ });
    expect(trigger).toBeInTheDocument();
    // Machine code preserved on the badge itself.
    expect(screen.getByTestId('status-badge')).toHaveAttribute(
      'data-code',
      'CRITICAL',
    );
  });

  it('opens on click (tap path) and exposes the localized explanation', async () => {
    const user = userEvent.setup();
    render(<StatusBadgeExplained domain="approval" code="PENDING" />);
    const trigger = screen.getByRole('button', { name: /Awaiting decision/ });
    await user.click(trigger);
    expect(screen.getByRole('note')).toHaveTextContent(
      'The request is waiting for an authorized user to approve or reject it',
    );
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(trigger).toHaveFocus();
  });

  it('closes on a second click and keeps focus on the trigger', async () => {
    const user = userEvent.setup();
    render(<StatusBadgeExplained domain="severity" code="LOW" />);
    const trigger = screen.getByRole('button', { name: /Low/ });
    await user.click(trigger);
    expect(screen.getByRole('note')).toBeInTheDocument();
    await user.click(trigger);
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup();
    render(<StatusBadgeExplained domain="severity" code="LOW" />);
    const trigger = screen.getByRole('button', { name: /Low/ });
    await user.click(trigger);
    expect(screen.getByRole('note')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('opens and closes with keyboard Enter activation (button semantics)', async () => {
    const user = userEvent.setup();
    render(<StatusBadgeExplained domain="severity" code="LOW" />);
    const trigger = screen.getByRole('button', { name: /Low/ });
    await user.tab();
    expect(trigger).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('note')).toBeInTheDocument();
    await user.keyboard('{Enter}');
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('closes when the user clicks/taps outside the popover', async () => {
    const user = userEvent.setup();
    render(
      <div>
        <StatusBadgeExplained domain="severity" code="LOW" />
        <button type="button">outside</button>
      </div>,
    );
    const trigger = screen.getByRole('button', { name: /Low/ });
    await user.click(trigger);
    expect(screen.getByRole('note')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'outside' }));
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('keeps the raw code visible in the popover for unknown codes', async () => {
    const user = userEvent.setup();
    render(<StatusBadgeExplained domain="plan" code="SOME_FUTURE_CODE" />);
    await user.click(screen.getByRole('button'));
    expect(screen.getByRole('note')).toHaveTextContent('SOME_FUTURE_CODE');
  });

  it('localizes label and explanation for the uk locale', async () => {
    const user = userEvent.setup();
    await act(async () => {
      await i18n.changeLanguage('uk');
    });
    render(<StatusBadgeExplained domain="severity" code="CRITICAL" />);
    const trigger = screen.getByRole('button', { name: /Критичний/ });
    expect(trigger).toBeInTheDocument();
    await user.click(trigger);
    expect(screen.getByRole('note')).toHaveTextContent(
      'Потребує негайної уваги: дефіцит може зупинити виробництво.',
    );
  });
});