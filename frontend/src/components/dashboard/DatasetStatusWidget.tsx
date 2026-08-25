import { useTranslation } from 'react-i18next'
import { Database, CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useDatasetStatus } from '@/hooks/useDatasetStatus'
import type { DatasetStatusResponse } from '@/lib/dataset-api'
import { Button } from '@/components/ui/button'

interface StatusDisplayProps {
  status: DatasetStatusResponse['status'];
}

/**
 * Dataset status values ("Valid"/"Invalid"/"Not Loaded") and their plain
 * explanations are machine-status labels owned by WP-UX-UA-04; they remain
 * English here and are inventoried as intentional machine-code exceptions.
 */
function StatusDisplay({ status }: StatusDisplayProps) {
  switch (status) {
    case 'valid':
      return (
        <div className="flex items-center gap-2" data-testid="dataset-status-valid">
          <CheckCircle2 className="h-5 w-5 text-emerald-400" aria-hidden="true" />
          <span className="text-lg font-semibold text-emerald-400">Valid</span>
        </div>
      )
    case 'invalid':
      return (
        <div className="flex items-center gap-2" data-testid="dataset-status-invalid">
          <AlertTriangle className="h-5 w-5 text-amber-400" aria-hidden="true" />
          <span className="text-lg font-semibold text-amber-400">Invalid</span>
        </div>
      )
    case 'not_loaded':
      return (
        <div className="flex items-center gap-2" data-testid="dataset-status-not-loaded">
          <AlertCircle className="h-5 w-5 text-steel-400" aria-hidden="true" />
          <span className="text-lg font-semibold text-steel-400">Not Loaded</span>
        </div>
      )
  }
}

function statusDescription(status: DatasetStatusResponse['status']): string {
  switch (status) {
    case 'valid':
      return 'Dataset matches approved Golden Dataset fixture.'
    case 'invalid':
      return 'Dataset differs from the approved fixture.'
    case 'not_loaded':
      return 'No Golden Dataset has been loaded.'
  }
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
      <p className="text-xs text-steel-400">{statusDescription(data.status)}</p>
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
