/**
 * Severity badge component for WP-3.5.
 *
 * Maps canonical severity values (CRITICAL, HIGH, MEDIUM, LOW) to semantic colors.
 * Unknown severity values fall back to a neutral badge.
 */

const SEVERITY_STYLES: Record<string, string> = {
  CRITICAL: 'bg-red-600/20 text-red-300 border-red-600/40',
  HIGH: 'bg-amber-600/20 text-amber-300 border-amber-600/40',
  MEDIUM: 'bg-blue-600/20 text-blue-300 border-blue-600/40',
  LOW: 'bg-steel-600/20 text-steel-300 border-steel-600/40',
};

const FALLBACK_STYLE = 'bg-steel-600/20 text-steel-300 border-steel-600/40';

interface SeverityBadgeProps {
  severity: string;
}

/**
 * Render a severity badge with semantic color.
 *
 * Unknown severity values render with neutral styling (no crash, no silent skip).
 */
export function SeverityBadge({ severity }: SeverityBadgeProps) {
  const style = SEVERITY_STYLES[severity] ?? FALLBACK_STYLE;
  const display = severity || 'UNKNOWN';

  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${style}`}
      data-testid="severity-badge"
      data-severity={severity}
    >
      {display}
    </span>
  );
}
