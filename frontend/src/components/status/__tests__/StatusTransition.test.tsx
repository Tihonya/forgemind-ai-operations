/**
 * StatusTransition component tests (WP-UX-UA-04, Phase 5 readiness).
 *
 * The primitive renders ONLY when both from and to statuses are supplied.
 * It localizes both endpoints through the registry, preserves machine codes
 * as technical metadata, and refuses to fabricate a transition when either
 * side is missing. It is intentionally NOT mounted in the live UI (no real
 * from_status/to_status pair exists in the API).
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import i18n from '@/i18n';
import StatusTransition from '../StatusTransition';

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

describe('StatusTransition — real transition pair', () => {
  it('renders previous → new status with localized labels and arrow direction', () => {
    render(
      <StatusTransition domain="plan" fromStatus="APPROVED" toStatus="EXECUTING" />,
    );
    const wrap = screen.getByTestId('status-transition');
    expect(screen.getByTestId('status-transition-from')).toHaveTextContent('Approved');
    expect(screen.getByTestId('status-transition-to')).toHaveTextContent('Executing');
    // The ChevronRight icon separates the pair (P → N direction cue).
    expect(wrap.querySelector('svg')).not.toBeNull();
  });

  it('preserves both machine codes as technical metadata', () => {
    render(
      <StatusTransition domain="plan" fromStatus="APPROVED" toStatus="EXECUTING" />,
    );
    expect(screen.getByTestId('status-transition-from')).toHaveAttribute(
      'data-code',
      'APPROVED',
    );
    expect(screen.getByTestId('status-transition-to')).toHaveAttribute(
      'data-code',
      'EXECUTING',
    );
  });

  it('renders the Ukrainian product wording under the uk locale', async () => {
    await i18n.changeLanguage('uk');
    render(
      <StatusTransition domain="workflowRun" fromStatus="PENDING" toStatus="COMPLETED" />,
    );
    expect(screen.getByTestId('status-transition-from')).toHaveTextContent('У черзі');
    expect(screen.getByTestId('status-transition-to')).toHaveTextContent('Завершено');
  });

  it('renders all optional metadata when supplied', () => {
    render(
      <StatusTransition
        domain="approval"
        fromStatus="PENDING"
        toStatus="APPROVED"
        actor="procurement.demo"
        timestamp="Jan 16, 2026"
        reason="Approved after review."
        correlationId="corr-abc-123"
      />,
    );
    const wrap = screen.getByTestId('status-transition');
    expect(wrap).toHaveTextContent('By:');
    expect(wrap).toHaveTextContent('procurement.demo');
    expect(wrap).toHaveTextContent('Jan 16, 2026');
    expect(wrap).toHaveTextContent('Approved after review.');
    expect(wrap).toHaveTextContent('corr-abc-123');
  });

  it('renders only the supplied optional metadata', () => {
    render(
      <StatusTransition
        domain="approval"
        fromStatus="PENDING"
        toStatus="APPROVED"
        actor="procurement.demo"
      />,
    );
    const wrap = screen.getByTestId('status-transition');
    expect(wrap).toHaveTextContent('procurement.demo');
    expect(wrap).not.toHaveTextContent('Time:');
    expect(wrap).not.toHaveTextContent('Reason:');
    expect(wrap).not.toHaveTextContent('Correlation ID:');
  });
});

describe('StatusTransition — fabrication prevention', () => {
  it('renders nothing when fromStatus is missing', () => {
    render(<StatusTransition domain="plan" fromStatus={null} toStatus="EXECUTING" />);
    expect(screen.queryByTestId('status-transition')).not.toBeInTheDocument();
  });

  it('renders nothing when toStatus is missing', () => {
    render(<StatusTransition domain="plan" fromStatus="APPROVED" toStatus="" />);
    expect(screen.queryByTestId('status-transition')).not.toBeInTheDocument();
  });

  it('renders nothing when both statuses are missing', () => {
    render(<StatusTransition domain="plan" fromStatus={undefined} toStatus={undefined} />);
    expect(screen.queryByTestId('status-transition')).not.toBeInTheDocument();
  });

  it('errors on unknown endpoint codes surface the unknown fallback, not invented text', () => {
    render(
      <StatusTransition domain="plan" fromStatus="SOME_FUTURE" toStatus="EXECUTING" />,
    );
    expect(screen.getByTestId('status-transition-from')).toHaveAttribute(
      'data-known',
      'false',
    );
    expect(screen.getByTestId('status-transition-from')).toHaveTextContent(
      'SOME_FUTURE',
    );
  });
});