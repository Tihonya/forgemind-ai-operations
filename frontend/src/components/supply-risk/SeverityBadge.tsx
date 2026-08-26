/**
 * Severity badge component for WP-3.5, registry-backed since WP-UX-UA-04.
 *
 * Renders the localized label for canonical severity values (CRITICAL, HIGH,
 * MEDIUM, LOW) with the registry semantic tone (icon + classes). Unknown
 * severity values fail safely: neutral tone, preserved machine code as
 * technical metadata, and the localized unknown label — never a crash and
 * never a silent skip.
 */

import StatusBadgeExplained from '@/components/status/StatusBadgeExplained'

interface SeverityBadgeProps {
  severity: string;
}

/**
 * Render a localized severity badge with a tooltip explanation.
 */
export function SeverityBadge({ severity }: SeverityBadgeProps) {
  return (
    <StatusBadgeExplained
      domain="severity"
      code={severity}
      testId="severity-badge"
    />
  )
}