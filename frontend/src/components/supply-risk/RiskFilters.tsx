/**
 * Risk filters component for WP-3.5.
 *
 * Client-side severity multi-filter and component-code text filter.
 * No server-side parameters introduced (Phase 3 §5.1).
 *
 * Localized per WP-UX-UA-03; severity chip values (CRITICAL/HIGH/MEDIUM/LOW)
 * are machine enums and remain untranslated (WP-UX-UA-04 scope).
 */

import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { resolveStatus } from '@/lib/status-registry'
import { useStatusTranslation } from '@/lib/status-i18n'

interface RiskFiltersProps {
  selectedSeverities: string[];
  onSeverityChange: (severities: string[]) => void;
  componentCodeFilter: string;
  onComponentCodeChange: (value: string) => void;
  onReset: () => void;
  hasActiveFilters: boolean;
}

const SEVERITY_OPTIONS = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const

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
  const { t } = useTranslation('supplyRisk')
  const { t: tStatus } = useStatusTranslation()

  function severityLabel(severity: string): string {
    const entry = resolveStatus('severity', severity)
    return entry.known ? tStatus(entry.labelKey) : severity
  }

  function toggleSeverity(severity: string) {
    if (selectedSeverities.includes(severity)) {
      onSeverityChange(selectedSeverities.filter((s) => s !== severity))
    } else {
      onSeverityChange([...selectedSeverities, severity])
    }
  }

  return (
    <div className="space-y-3" data-testid="risk-filters">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-steel-300">{t('filters.severity')}</span>
        {SEVERITY_OPTIONS.map((severity) => {
          const isSelected = selectedSeverities.includes(severity)
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
              {severityLabel(severity)}
            </button>
          )
        })}
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor="component-code-filter" className="text-sm font-medium text-steel-300">
          {t('filters.component')}
        </label>
        <input
          id="component-code-filter"
          type="text"
          value={componentCodeFilter}
          onChange={(e) => onComponentCodeChange(e.target.value)}
          placeholder={t('filters.componentPlaceholder')}
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
            {t('filters.reset')}
          </Button>
        )}
      </div>
    </div>
  )
}
