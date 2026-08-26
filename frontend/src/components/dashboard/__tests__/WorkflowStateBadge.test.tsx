import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import i18n from '@/i18n';
import WorkflowStateBadge from '../WorkflowStateBadge';

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

describe('WorkflowStateBadge', () => {
  it('renders business label for COMPLETED', () => {
    render(<WorkflowStateBadge state="COMPLETED" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent('Completed');
    expect(screen.getByTestId('workflow-state-badge')).toHaveAttribute('data-code', 'COMPLETED');
  });

  it('renders business label for PENDING', () => {
    render(<WorkflowStateBadge state="PENDING" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent('Queued');
  });

  it('renders business label for RUNNING', () => {
    render(<WorkflowStateBadge state="RUNNING" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent('Analysis in progress');
  });

  it('renders business label for AWAITING_VALIDATION', () => {
    render(<WorkflowStateBadge state="AWAITING_VALIDATION" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent('Validating result');
  });

  it('renders business label for FAILED_PROVIDER', () => {
    render(<WorkflowStateBadge state="FAILED_PROVIDER" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent('AI service unavailable');
  });

  it('renders business label for FAILED_VALIDATION', () => {
    render(<WorkflowStateBadge state="FAILED_VALIDATION" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent('Validation failed');
  });

  it('renders business label for FAILED_RETRIEVAL', () => {
    render(<WorkflowStateBadge state="FAILED_RETRIEVAL" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent('Evidence retrieval failed');
  });

  it('renders business label for FAILED_INTERNAL', () => {
    render(<WorkflowStateBadge state="FAILED_INTERNAL" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent('Analysis failed');
  });

  it('renders the neutral unknown presentation for null state', () => {
    render(<WorkflowStateBadge state={null} />);
    const badge = screen.getByTestId('workflow-state-badge');
    expect(badge).toHaveTextContent('Unknown status');
    expect(badge).toHaveAttribute('data-known', 'false');
  });

  it('preserves the raw value for an unknown state', () => {
    render(<WorkflowStateBadge state="SOME_NEW_STATE" />);
    const badge = screen.getByTestId('workflow-state-badge');
    expect(badge).toHaveTextContent('SOME_NEW_STATE');
    expect(badge).toHaveAttribute('data-code', 'SOME_NEW_STATE');
    expect(badge).toHaveAttribute('data-known', 'false');
  });
});