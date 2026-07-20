import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { DataEmptyState } from './DataEmptyState';

describe('DataEmptyState', () => {
  it('renders primary text', () => {
    render(<DataEmptyState primaryText="No data available" />);
    
    expect(screen.getByText('No data available')).toBeInTheDocument();
  });

  it('renders secondary text when provided', () => {
    render(
      <DataEmptyState 
        primaryText="No data" 
        secondaryText="Try adjusting your filters" 
      />
    );
    
    expect(screen.getByText('No data')).toBeInTheDocument();
    expect(screen.getByText('Try adjusting your filters')).toBeInTheDocument();
  });

  it('does not render secondary text when not provided', () => {
    render(<DataEmptyState primaryText="No data" />);
    
    expect(screen.getByText('No data')).toBeInTheDocument();
    expect(screen.queryByText('Try adjusting your filters')).not.toBeInTheDocument();
  });

  it('renders default Package icon when no icon provided', () => {
    const { container } = render(<DataEmptyState primaryText="No data" />);
    
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('renders custom icon when provided', () => {
    const customIcon = <span data-testid="custom-icon">📦</span>;
    render(<DataEmptyState primaryText="No data" icon={customIcon} />);
    
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });

  it('uses custom testId when provided', () => {
    render(<DataEmptyState primaryText="No data" testId="custom-empty" />);
    
    expect(screen.getByTestId('custom-empty')).toBeInTheDocument();
  });

  it('uses default testId when not provided', () => {
    render(<DataEmptyState primaryText="No data" />);
    
    expect(screen.getByTestId('data-empty-state')).toBeInTheDocument();
  });
});
