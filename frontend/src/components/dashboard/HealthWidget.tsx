import { useTranslation } from 'react-i18next'
import { Activity, CheckCircle2, AlertCircle, XCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useHealth } from '@/hooks/useHealth'
import { resolveStatus } from '@/lib/status-registry'
import { useStatusTranslation } from '@/lib/status-i18n'
import type { HealthCheckResponse } from '@/lib/health-api'
import { Button } from '@/components/ui/button'

interface StatusIconProps {
  status: HealthCheckResponse['status'];
}

function StatusIcon({ status }: StatusIconProps) {
  // Icons (non-color cue) are keyed to the registry tone; the underlying
  // overall status labels come from the WP-UX-UA-04 status catalog.
  const Icon: LucideIcon = status === 'healthy' ? CheckCircle2 : status === 'degraded' ? AlertCircle : XCircle
  return (
    <Icon
      className="h-5 w-5"
      aria-hidden="true"
      data-testid={`health-icon-${status}`}
    />
  )
}

/**
 * Health status labels ("healthy"/"degraded"/"unhealthy") — localized via
 * the WP-UX-UA-04 status registry; raw machine codes remain untouched.
 */
function HealthContent({ data }: { data: HealthCheckResponse }) {
  const { t } = useStatusTranslation()
  const entry = resolveStatus('health', data.status)
  const label = entry.known ? t(entry.labelKey) : data.status

  const checks = data.checks

  return (
    <div className="space-y-3" data-testid="health-content">
      <div className="flex items-center gap-2" data-testid="health-status">
        <StatusIcon status={data.status} />
        <span className={`text-lg font-semibold ${HEALTH_TONE_TEXT[entry.tone]}`}>
          {label}
        </span>
      </div>
      <p className="text-xs text-steel-400">{t(entry.descriptionKey)}</p>
      <div className="space-y-0.5 border-t border-steel-700 pt-3">
        <DependencyRow name="postgresql" value={checks.postgresql} />
        <DependencyRow name="redis" value={checks.redis} />
        <DependencyRow name="worker" value={checks.worker} />
        <DependencyRow name="alembic_revision" value={checks.alembic_revision} />
      </div>
    </div>
  )
}

const HEALTH_TONE_TEXT: Record<string, string> = {
  neutral: 'text-steel-400',
  info: 'text-blue-400',
  success: 'text-emerald-400',
  warning: 'text-amber-400',
  danger: 'text-red-400',
}

function DependencyRow({ name, value }: { name: string; value: string }) {
  const { t } = useStatusTranslation()

  // The alembic revision is an identifier, not a status: it stays raw
  // technical metadata. Other dependency values are ok/error/unknown statuses
  // resolved through the registry.
  const isAlembic = name === 'alembic_revision'
  const entry = isAlembic ? null : resolveStatus('healthCheck', value)
  const label = isAlembic ? value : entry!.known ? t(entry!.labelKey) : value
  const tone = isAlembic
    ? value === 'unknown'
      ? 'warning'
      : 'neutral'
    : entry!.tone

  return (
    <div className="flex items-center justify-between py-1" data-testid={`health-dep-${name}`}>
      <span className="text-xs text-steel-400 capitalize">{name.replace('_', ' ')}</span>
      <span
        className={`min-w-0 text-xs font-medium ${HEALTH_TONE_TEXT[tone]} ${
          isAlembic ? 'break-all font-mono' : ''
        }`}
        data-status={isAlembic ? undefined : value}
      >
        {label}
      </span>
    </div>
  )
}

/**
 * API Health widget.
 *
 * Displays overall system health status and individual dependency checks.
 * Uses the public /health endpoint (no authentication required).
 */
export default function HealthWidget() {
  const { t } = useTranslation('dashboard')
  const { data, isLoading, isError, refetch } = useHealth()

  return (
    <Card data-testid="health-widget">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <Activity className="h-4 w-4 text-steel-500" aria-hidden="true" />
          {t('widgets.health.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-3" data-testid="health-loading">
            <Skeleton className="h-6 w-32" />
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
            </div>
          </div>
        )}
        {isError && (
          <div className="space-y-2" data-testid="health-error">
            <p className="text-sm text-red-400" role="alert">
              {t('widgets.health.error')}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              data-testid="health-retry"
              className="border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
            >
              {t('common:actions.retry')}
            </Button>
          </div>
        )}
        {!isLoading && !isError && data && <HealthContent data={data} />}
      </CardContent>
    </Card>
  )
}