import { useTranslation } from 'react-i18next';

import { useActivePlan } from '@/hooks/useActivePlan';
import ActivePlanWidget from '@/components/dashboard/ActivePlanWidget';
import RiskSummaryWidget from '@/components/dashboard/RiskSummaryWidget';
import HealthWidget from '@/components/dashboard/HealthWidget';
import DatasetStatusWidget from '@/components/dashboard/DatasetStatusWidget';
import LatestAIAnalysisWidget from '@/components/dashboard/LatestAIAnalysisWidget';
import AwaitingDecisionWidget from '@/components/dashboard/AwaitingDecisionWidget';

/**
 * Operations Dashboard — WP-UX-01.
 *
 * Displays:
 * - Active production plan (primary)
 * - Risk severity summary (primary)
 * - Latest AI Analysis — live, state-aware widget (primary)
 * - Awaiting Decision — live approval count (primary)
 * - System health (operational)
 * - Dataset status (operational)
 *
 * No stale Phase placeholders. No invented metrics.
 * All values come from real backend responses.
 *
 * WP-UX-UA-01 pilot boundary: the page heading and purpose text are
 * localized (dashboard.* catalog). Widget content remains English — that
 * surface belongs to WP-UX-UA-03 and is an expected transitional state,
 * not a defect.
 */
export default function Dashboard() {
  const { t } = useTranslation('dashboard');
  const { activePlan } = useActivePlan();

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* Page heading (localized pilot copy) */}
      <div>
        <h1 className="text-2xl font-bold text-white">{t('heading')}</h1>
        <p className="text-sm text-steel-400">{t('purpose')}</p>
      </div>

      {/* Primary widgets — full width */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <ActivePlanWidget />
        </div>
        <div className="lg:col-span-2">
          <RiskSummaryWidget planCode={activePlan?.code ?? null} />
        </div>
      </div>

      {/* Live state-aware widgets */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <LatestAIAnalysisWidget />
        <AwaitingDecisionWidget />
      </div>

      {/* Operational widgets */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <HealthWidget />
        <DatasetStatusWidget />
      </div>
    </div>
  );
}