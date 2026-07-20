import { Activity, CheckCircle2, AlertCircle, XCircle } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useHealth } from '@/hooks/useHealth';
import type { HealthCheckResponse } from '@/lib/health-api';
import { Button } from '@/components/ui/button';

interface StatusIconProps {
  status: HealthCheckResponse['status'];
}

function StatusIcon({ status }: StatusIconProps) {
  switch (status) {
    case 'healthy':
      return (
        <CheckCircle2
          className="h-5 w-5 text-emerald-400"
          aria-hidden="true"
          data-testid="health-icon-healthy"
        />
      );
    case 'degraded':
      return (
        <AlertCircle
          className="h-5 w-5 text-amber-400"
          aria-hidden="true"
          data-testid="health-icon-degraded"
        />
      );
    case 'unhealthy':
      return (
        <XCircle
          className="h-5 w-5 text-red-400"
          aria-hidden="true"
          data-testid="health-icon-unhealthy"
        />
      );
  }
}

function statusLabel(status: HealthCheckResponse['status']): string {
  switch (status) {
    case 'healthy':
      return 'Healthy';
    case 'degraded':
      return 'Degraded';
    case 'unhealthy':
      return 'Unhealthy';
  }
}

function statusColor(status: HealthCheckResponse['status']): string {
  switch (status) {
    case 'healthy':
      return 'text-emerald-400';
    case 'degraded':
      return 'text-amber-400';
    case 'unhealthy':
      return 'text-red-400';
  }
}

function DependencyRow({ name, value }: { name: string; value: string }) {
  const isOk = value === 'ok' || (name === 'alembic_revision' && value !== 'unknown');

  return (
    <div className="flex items-center justify-between py-1" data-testid={`health-dep-${name}`}>
      <span className="text-xs text-steel-400 capitalize">{name.replace('_', ' ')}</span>
      <span className={`text-xs font-medium ${isOk ? 'text-emerald-400' : 'text-amber-400'}`}>
        {value}
      </span>
    </div>
  );
}

function HealthContent({ data }: { data: HealthCheckResponse }) {
  const checks = data.checks;

  return (
    <div className="space-y-3" data-testid="health-content">
      <div className="flex items-center gap-2">
        <StatusIcon status={data.status} />
        <span className={`text-lg font-semibold ${statusColor(data.status)}`} data-testid="health-status">
          {statusLabel(data.status)}
        </span>
      </div>
      <div className="space-y-0.5 border-t border-steel-700 pt-3">
        <DependencyRow name="postgresql" value={checks.postgresql} />
        <DependencyRow name="redis" value={checks.redis} />
        <DependencyRow name="worker" value={checks.worker} />
        <DependencyRow name="alembic_revision" value={checks.alembic_revision} />
      </div>
    </div>
  );
}

/**
 * API Health widget.
 *
 * Displays overall system health status and individual dependency checks.
 * Uses the public /health endpoint (no authentication required).
 */
export default function HealthWidget() {
  const { data, isLoading, isError, refetch } = useHealth();

  return (
    <Card className="bg-steel-900/60 border-steel-700" data-testid="health-widget">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <Activity className="h-4 w-4 text-steel-500" aria-hidden="true" />
          System Health
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
              Health check unavailable
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              data-testid="health-retry"
              className="border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
            >
              Retry
            </Button>
          </div>
        )}
        {!isLoading && !isError && data && <HealthContent data={data} />}
      </CardContent>
    </Card>
  );
}
