import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RiskFilters } from '../RiskFilters';

const defaultProps = {
  selectedSeverities: [] as string[],
  onSeverityChange: vi.fn(),
  componentCodeFilter: '',
  onComponentCodeChange: vi.fn(),
  onReset: vi.fn(),
  hasActiveFilters: false,
};

describe('RiskFilters', () => {
  it('renders severity filter buttons', () => {
    render(<RiskFilters {...defaultProps} />);
    expect(screen.getByTestId('severity-filter-critical')).toBeInTheDocument();
    expect(screen.getByTestId('severity-filter-high')).toBeInTheDocument();
    expect(screen.getByTestId('severity-filter-medium')).toBeInTheDocument();
    expect(screen.getByTestId('severity-filter-low')).toBeInTheDocument();
  });

  it('marks selected severities as active', () => {
    render(<RiskFilters {...defaultProps} selectedSeverities={['CRITICAL', 'HIGH']} />);
    expect(screen.getByTestId('severity-filter-critical')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('severity-filter-high')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('severity-filter-medium')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('severity-filter-low')).toHaveAttribute('aria-pressed', 'false');
  });

  it('calls onSeverityChange when clicking a severity button', () => {
    const onSeverityChange = vi.fn();
    render(<RiskFilters {...defaultProps} onSeverityChange={onSeverityChange} />);
    
    fireEvent.click(screen.getByTestId('severity-filter-critical'));
    expect(onSeverityChange).toHaveBeenCalledWith(['CRITICAL']);
  });

  it('renders component code filter input', () => {
    render(<RiskFilters {...defaultProps} />);
    expect(screen.getByTestId('component-code-filter')).toBeInTheDocument();
  });

  it('calls onComponentCodeChange when typing in the filter', () => {
    const onComponentCodeChange = vi.fn();
    render(<RiskFilters {...defaultProps} onComponentCodeChange={onComponentCodeChange} />);
    
    fireEvent.change(screen.getByTestId('component-code-filter'), {
      target: { value: 'CTRL' },
    });
    expect(onComponentCodeChange).toHaveBeenCalledWith('CTRL');
  });

  it('shows reset button when hasActiveFilters is true', () => {
    render(<RiskFilters {...defaultProps} hasActiveFilters={true} />);
    expect(screen.getByTestId('reset-filters')).toBeInTheDocument();
  });

  it('hides reset button when hasActiveFilters is false', () => {
    render(<RiskFilters {...defaultProps} hasActiveFilters={false} />);
    expect(screen.queryByTestId('reset-filters')).not.toBeInTheDocument();
  });

  it('calls onReset when clicking reset button', () => {
    const onReset = vi.fn();
    render(<RiskFilters {...defaultProps} hasActiveFilters={true} onReset={onReset} />);
    
    fireEvent.click(screen.getByTestId('reset-filters'));
    expect(onReset).toHaveBeenCalled();
  });
});
