/**
 * StatusExplanation component tests (WP-UX-UA-04).
 *
 * Notes on jsdom constraints (documented, not skipped silently):
 * - A native <details> element keeps its content in the DOM even when
 *   collapsed, so visibility is asserted through the ``open`` attribute.
 * - jsdom does not route Tab to a native <summary> or synthesize its Enter
 *   activation; the click() activation used here is the same activation
 *   behavior real browsers run for Enter/Space on a focused summary.
 */
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import i18n from '@/i18n';
import StatusExplanation from '../StatusExplanation';

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

describe('StatusExplanation — inline variant', () => {
  it('shows the localized plain-language description directly', () => {
    render(<StatusExplanation domain="approval" code="PENDING" variant="inline" />);
    const el = screen.getByTestId('status-explanation');
    expect(el.tagName).toBe('SPAN');
    expect(el).toHaveTextContent(
      'waiting for an authorized user to approve or reject it',
    );
  });

  it('renders the uk description under the uk locale', async () => {
    await act(async () => {
      await i18n.changeLanguage('uk');
    });
    render(<StatusExplanation domain="approval" code="PENDING" variant="inline" />);
    expect(screen.getByTestId('status-explanation')).toHaveTextContent(
      'очікує погодження або відхилення уповноваженим користувачем',
    );
  });
});

describe('StatusExplanation — details variant (accessible disclosure)', () => {
  it('starts collapsed and never reveals meaning until activated', () => {
    render(<StatusExplanation domain="approval" code="PENDING" />);
    const details = screen.getByTestId('status-explanation') as HTMLDetailsElement;
    expect(details.open).toBe(false);
  });

  it('opens on trigger activation and closes on a second activation', async () => {
    const user = userEvent.setup();
    render(<StatusExplanation domain="approval" code="PENDING" />);
    const details = screen.getByTestId('status-explanation') as HTMLDetailsElement;
    const summary = details.querySelector('summary');
    expect(summary).not.toBeNull();

    await user.click(summary as HTMLElement);
    expect(details.open).toBe(true);
    expect(
      screen.getByText(/waiting for an authorized user to approve or reject it/),
    ).toBeInTheDocument();

    await user.click(summary as HTMLElement);
    expect(details.open).toBe(false);
  });

  it('the trigger carries an accessible name in the active locale', async () => {
    await act(async () => {
      await i18n.changeLanguage('uk');
    });
    render(<StatusExplanation domain="severity" code="LOW" />);
    const summary = screen
      .getByTestId('status-explanation')
      .querySelector('summary');
    expect(summary).toHaveAttribute(
      'aria-label',
      'Показати або сховати пояснення статусу',
    );
  });

  it('localizes the explanation heading (same mounted component)', async () => {
    render(<StatusExplanation domain="severity" code="LOW" />);
    expect(screen.getByText('Explanation')).toBeInTheDocument();
    await act(async () => {
      await i18n.changeLanguage('uk');
    });
    expect(screen.getByText('Пояснення')).toBeInTheDocument();
    expect(screen.queryByText('Explanation')).not.toBeInTheDocument();
  });

  it('renders the uk explanation content when opened', async () => {
    const user = userEvent.setup();
    await act(async () => {
      await i18n.changeLanguage('uk');
    });
    render(<StatusExplanation domain="severity" code="LOW" />);
    const summary = screen
      .getByTestId('status-explanation')
      .querySelector('summary');
    await user.click(summary as HTMLElement);
    expect(
      screen.getByText('Незначний ризик; регулярного моніторингу достатньо.'),
    ).toBeInTheDocument();
  });
});

describe('StatusExplanation — unknown codes', () => {
  it('shows the diagnostic fallback explanation and the preserved raw code', () => {
    render(<StatusExplanation domain="plan" code="SOME_FUTURE_CODE" />);
    const el = screen.getByTestId('status-explanation');
    expect(el).toHaveTextContent('The system has no explanation for this value.');
    expect(el).toHaveTextContent('SOME_FUTURE_CODE');
  });
});