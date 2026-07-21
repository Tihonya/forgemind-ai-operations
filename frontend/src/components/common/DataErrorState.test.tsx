import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DataErrorState } from './DataErrorState';

describe('DataErrorState', () => {
  it('renders error message with default title', () => {
    render(<DataErrorState message="Network error" />);
    
    expect(screen.getByText('Unable to load data')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('renders custom title when provided', () => {
    render(<DataErrorState title="Custom error" message="Something failed" />);
    
    expect(screen.getByText('Custom error')).toBeInTheDocument();
    expect(screen.getByText('Something failed')).toBeInTheDocument();
  });

  it('does not render retry button when onRetry is not provided', () => {
    render(<DataErrorState message="Error" />);
    
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders retry button when onRetry is provided', () => {
    const onRetry = vi.fn();
    render(<DataErrorState message="Error" onRetry={onRetry} />);
    
    const retryButton = screen.getByRole('button', { name: /retry/i });
    expect(retryButton).toBeInTheDocument();
  });

  it('calls onRetry when retry button is clicked', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<DataErrorState message="Error" onRetry={onRetry} />);
    
    const retryButton = screen.getByRole('button', { name: /retry/i });
    await user.click(retryButton);
    
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('uses custom testId when provided', () => {
    render(<DataErrorState message="Error" testId="custom-error" />);
    
    expect(screen.getByTestId('custom-error')).toBeInTheDocument();
  });

  it('uses default testId when not provided', () => {
    render(<DataErrorState message="Error" />);
    
    expect(screen.getByTestId('data-error-state')).toBeInTheDocument();
  });
});
