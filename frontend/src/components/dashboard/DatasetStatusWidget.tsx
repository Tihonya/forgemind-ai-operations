import { useTranslation } from 'react-i18next'
import { Database, CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useDatasetStatus } from '@/hooks/useDatasetStatus'
import { resolveStatus } from '@/lib/status-registry'
import { useStatusTranslation } from '@/lib/status-i18n'
import type { DatasetStatusResponse } from '@/lib/dataset-api'
import { Button } from '@/components/ui/button'

interface StatusDisplayProps {
  status: DatasetStatusResponse['status'];
}

/**
 * Dataset status values ("valid"/"invalid"/"not_loaded") — localized
 * registry presentation (WP-UX-UA-04). The raw machine code remains
 * available on ``data-code`` and the unknown fallback preserves it.
 */
function StatusDisplay({ status }: StatusDisplayProps) {
  const { t } = useStatusTranslation()
  const entry = resolveStatus('dataset', status)
  const label = entry.known ? t(entry.labelKey) : status

  const icon = entry.known
    ? (status === 'valid' ? CheckCircle2 : status === 'invalid' ? AlertTriangle : AlertCircle)
    : AlertCircle

  const Icon = icon

  return (
    <div
      className="flex items-start gap-2"
      data-testid={`dataset-status-${status}`}
      data-code={entry.code}
    >
      <Icon className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span>
        <span
          className={`block text-lg font-semibold ${
            entry.known ? DATASET_TONE_TEXT[entry.tone] ?? 'text-steel-200' : 'text-steel-200'
          }`}
        >
          {label}
        </span>
        <p className="text-xs text-steel-400">{t(entry.descriptionKey)}</p>
      </span>
    </div>
  )
}

/** Registry tone → dataset status text class. */
const DATASET_TONE_TEXT: Record<string, string> = {
  neutral: 'text-steel-400',
  info: 'text-blue-400',
  success: 'text-emerald-400',
  warning: 'text-amber-400',
  danger: 'text-red-400',
}

function DatasetContent({
  data,
  t,
}: {
  data: DatasetStatusResponse;
  t: (key: string) => string;
}) {
  return (
    <div className="space-y-3" data-testid="dataset-content">
      <StatusDisplay status={data.status} />
      <div className="space-y-1 border-t border-steel-700 pt-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-steel-400">{t('widgets.datasetStatus.version')}</span>
          <span className="text-xs font-medium text-steel-200" data-testid="dataset-version">
            {data.dataset_version}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-steel-400">{t('widgets.datasetStatus.algorithm')}</span>
          <span className="text-xs font-medium text-steel-200" data-testid="dataset-algorithm">
            {data.checksum_algorithm}
          </span>
        </div>
        {data.actual_checksum !== null && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-steel-400">{t('widgets.datasetStatus.checksumMatch')}</span>
            <span
              className={`text-xs font-medium ${
                data.actual_checksum === data.expected_checksum
                  ? 'text-emerald-400'
                  : 'text-amber-400'
              }`}
              data-testid="dataset-checksum-match"
            >
              {data.actual_checksum === data.expected_checksum
                ? t('widgets.datasetStatus.yes')
                : t('widgets.datasetStatus.no')}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Dataset Status widget.
 *
 * Displays Golden Dataset integrity verification status.
 * Requires Bearer token authentication.
 */
export default function DatasetStatusWidget() {
  const { t } = useTranslation('dashboard')
  const { data, isLoading, isError, refetch } = useDatasetStatus()

  return (
    <Card data-testid="dataset-status-widget">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <Database className="h-4 w-4 text-steel-500" aria-hidden="true" />
          {t('widgets.datasetStatus.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-3" data-testid="dataset-status-loading">
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-4 w-48" />
          </div>
        )}
        {isError && (
          <div className="space-y-2" data-testid="dataset-status-error">
            <p className="text-sm text-red-400" role="alert">
              {t('widgets.datasetStatus.error')}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              data-testid="dataset-status-retry"
              className="border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
            >
              {t('common:actions.retry')}
            </Button>
          </div>
        )}
        {!isLoading && !isError && data && <DatasetContent data={data} t={t} />}
      </CardContent>
    </Card>
  )
}