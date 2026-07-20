/**
 * Risk filters component for WP-3.5.
 *
 * Client-side severity multi-filter and component-code text filter.
 * No server-side parameters introduced (Phase 3 §5.1).
 */

import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';

interface RiskFiltersProps {
  selectedSeverities: string[];
  onSeverityChange: (severities: string[]) => void;
  componentCodeFilter: string;
  onComponentCodeChange: (value: string) => void;
  onReset: () => void;
  hasActiveFilters: boolean;
}

const SEVERITY_OPTIONS = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const;

/**
 * Render severity chip group and component-code text input.
 */
export function RiskFilters({
  selectedSeverities,
  onSeverityChange,
  componentCodeFilter,
  onComponentCodeChange,
  onReset,
  hasActiveFilters,
}: RiskFiltersProps) {
  function toggleSeverity(severity: string) {
    if (selectedSeverities.includes(severity)) {
      onSeverityChange(selectedSeverities.filter((s) => s !== severity));
    } else {
      onSeverityChange([...selectedSeverities, severity]);
    }
  }

  return (
    <div className="space-y-3" data-testid="risk-filters">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-steel-300">Severity:</span>
        {SEVERITY_OPTIONS.map((severity) => {
          const isSelected = selectedSeverities.includes(severity);
          return (
            <button
              key={severity}
              type="button"
              onClick={() => toggleSeverity(severity)}
              className={`rounded-md border px-3 py-1 text-xs font-medium transition-colors ${
                isSelected
                  ? 'border-primary-500/60 bg-primary-600/20 text-primary-300'
                  : 'border-steel-700 bg-steel-800/40 text-steel-400 hover:bg-steel-700/40'
              }`}
              data-testid={`severity-filter-${severity.toLowerCase()}`}
              aria-pressed={isSelected}
            >
              {severity}
            </button>
          );
        })}
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor="component-code-filter" className="text-sm font-medium text-steel-300">
          Component:
        </label>
        <input
          id="component-code-filter"
          type="text"
          value={componentCodeFilter}
          onChange={(e) => onComponentCodeChange(e.target.value)}
          placeholder="Search by component code..."
          className="flex-1 rounded-md border border-steel-700 bg-steel-800/40 px-3 py-1.5 text-sm text-white placeholder:text-steel-500 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          data-testid="component-code-filter"
        />
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onReset}
            className="text-steel-400 hover:text-steel-200"
            data-testid="reset-filters"
          >
            <X className="mr-1 h-3 w-3" aria-hidden="true" />
            Reset
          </Button>
        )}
      </div>
    </div>
  );
}
