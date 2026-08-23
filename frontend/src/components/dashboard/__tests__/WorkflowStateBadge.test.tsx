import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import WorkflowStateBadge from '../WorkflowStateBadge';

describe('WorkflowStateBadge', () => {
  it('renders business label for COMPLETED', () => {
    render(<WorkflowStateBadge state="COMPLETED" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Completed',
    );
  });

  it('renders business label for PENDING', () => {
    render(<WorkflowStateBadge state="PENDING" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Queued',
    );
  });

  it('renders business label for RUNNING', () => {
    render(<WorkflowStateBadge state="RUNNING" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Analysis in progress',
    );
  });

  it('renders business label for AWAITING_VALIDATION', () => {
    render(<WorkflowStateBadge state="AWAITING_VALIDATION" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Validating result',
    );
  });

  it('renders business label for FAILED_PROVIDER', () => {
    render(<WorkflowStateBadge state="FAILED_PROVIDER" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'AI service unavailable',
    );
  });

  it('renders business label for FAILED_VALIDATION', () => {
    render(<WorkflowStateBadge state="FAILED_VALIDATION" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Validation failed',
    );
  });

  it('renders business label for FAILED_RETRIEVAL', () => {
    render(<WorkflowStateBadge state="FAILED_RETRIEVAL" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Evidence retrieval failed',
    );
  });

  it('renders business label for FAILED_INTERNAL', () => {
    render(<WorkflowStateBadge state="FAILED_INTERNAL" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Analysis failed',
    );
  });

  it('renders Unknown for null state', () => {
    render(<WorkflowStateBadge state={null} />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'Unknown',
    );
  });

  it('renders raw value for unknown state', () => {
    render(<WorkflowStateBadge state="SOME_NEW_STATE" />);
    expect(screen.getByTestId('workflow-state-badge')).toHaveTextContent(
      'SOME_NEW_STATE',
    );
  });
});
