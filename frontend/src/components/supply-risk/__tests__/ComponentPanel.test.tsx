import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ComponentPanel } from '../ComponentPanel';

describe('ComponentPanel', () => {
  it('displays component code', () => {
    const component = {
      code: 'COMP-001',
      name: 'Widget A',
      unit: 'EA',
      alternatives: [],
    };

    render(<ComponentPanel component={component} />);

    expect(screen.getByText('COMP-001')).toBeInTheDocument();
    // Note: ComponentPanel does not display component.name in current implementation
  });

  it('displays alternatives when present', () => {
    const component = {
      code: 'COMP-001',
      name: 'Widget A',
      unit: 'EA',
      alternatives: [
        { alternative_code: 'ALT-001', status: 'APPROVED', rationale: 'Equivalent' },
        { alternative_code: 'ALT-002', status: 'PROPOSED' },
      ],
    };

    render(<ComponentPanel component={component} />);

    expect(screen.getByText('ALT-001')).toBeInTheDocument();
    // Alternatives are rendered as "— STATUS"
    expect(screen.getByText(/— APPROVED/)).toBeInTheDocument();
    expect(screen.getByText('ALT-002')).toBeInTheDocument();
    expect(screen.getByText(/— PROPOSED/)).toBeInTheDocument();
  });

  it('does not display alternatives section when empty', () => {
    const component = {
      code: 'COMP-001',
      name: 'Widget A',
      unit: 'EA',
      alternatives: [],
    };

    render(<ComponentPanel component={component} />);

    expect(screen.queryByText('Alternatives')).not.toBeInTheDocument();
  });
});
