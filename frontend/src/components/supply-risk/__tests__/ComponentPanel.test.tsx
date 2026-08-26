import { render, screen } from '@testing-library/react';
import { describe, expect, it, beforeEach } from 'vitest';

import i18n from '@/i18n';
import { ComponentPanel } from '../ComponentPanel';

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

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

  it('displays alternatives with localized status badges when present', () => {
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
    // Localized registry badge; the machine code stays on data-code.
    expect(screen.getByTestId('alternative-status-ALT-001')).toHaveTextContent('Approved');
    expect(screen.getByTestId('alternative-status-ALT-001')).toHaveAttribute(
      'data-code',
      'APPROVED',
    );
    expect(screen.getByText('ALT-002')).toBeInTheDocument();
    expect(screen.getByTestId('alternative-status-ALT-002')).toHaveTextContent('Proposed');
    expect(screen.getByTestId('alternative-status-ALT-002')).toHaveAttribute(
      'data-code',
      'PROPOSED',
    );
  });

  it('does not display alternatives section when empty', () => {
    const component = {
      code: 'COMP-001',
      name: 'Widget A',
      unit: 'EA',
      alternatives: [],
    };

    render(<ComponentPanel component={component} />);

    expect(screen.queryByText('ALT-001')).not.toBeInTheDocument();
  });
});