import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PlaceholderWidget from '../PlaceholderWidget';

describe('PlaceholderWidget', () => {
  it('renders placeholder with title and message', () => {
    render(
      <PlaceholderWidget
        title="Future Feature"
        message="Coming in Phase 5"
      />
    );

    expect(screen.getByText('Future Feature')).toBeInTheDocument();
    expect(screen.getByText('Coming in Phase 5')).toBeInTheDocument();
  });

  it('renders with placeholder-widget testid', () => {
    render(
      <PlaceholderWidget
        title="Test"
        message="Test message"
      />
    );

    const widget = screen.getByTestId('placeholder-widget');
    expect(widget).toBeInTheDocument();
    expect(widget).toHaveClass('opacity-60');
  });

  it('renders custom icon when provided', () => {
    const CustomIcon = () => <span data-testid="custom-icon">Icon</span>;

    render(
      <PlaceholderWidget
        title="Test"
        message="Test message"
        icon={<CustomIcon />}
      />
    );

    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });

  it('does not make any network calls', () => {
    const fetchSpy = vi.spyOn(global, 'fetch');

    render(
      <PlaceholderWidget
        title="Test"
        message="Test message"
      />
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
