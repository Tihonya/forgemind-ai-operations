import { Bot, Clock, CheckSquare } from 'lucide-react';

import { useActivePlan } from '@/hooks/useActivePlan';
import ActivePlanWidget from '@/components/dashboard/ActivePlanWidget';
import RiskSummaryWidget from '@/components/dashboard/RiskSummaryWidget';
import HealthWidget from '@/components/dashboard/HealthWidget';
import DatasetStatusWidget from '@/components/dashboard/DatasetStatusWidget';
import PlaceholderWidget from '@/components/dashboard/PlaceholderWidget';

/**
 * Executive Dashboard — WP-3.4.
 *
 * Displays:
 * - Active production plan (primary)
 * - Risk severity summary (primary)
 * - System health (operational)
 * - Dataset status (operational)
 * - Placeholder widgets for future phases
 *
 * All values come from real backend responses.
 * No hardcoded Golden Scenario values.
 */
export default function Dashboard() {
  const { activePlan } = useActivePlan();

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* Page heading */}
      <div>
        <h1 className="text-2xl font-bold text-white">Executive Dashboard</h1>
        <p className="text-sm text-steel-400">
          Operational overview and active supply-risk indicators
        </p>
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

      {/* Operational widgets */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <HealthWidget />
        <DatasetStatusWidget />
      </div>

      {/* Future capability placeholders */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <PlaceholderWidget
          title="Latest Agent Runs"
          message="Unavailable — Phase 5"
          icon={<Bot className="h-4 w-4" aria-hidden="true" />}
        />
        <PlaceholderWidget
          title="Pending Approvals"
          message="Unavailable — Phase 6"
          icon={<CheckSquare className="h-4 w-4" aria-hidden="true" />}
        />
        <PlaceholderWidget
          title="Estimated Time Saved"
          message="Metric available in Phase 5"
          icon={<Clock className="h-4 w-4" aria-hidden="true" />}
        />
      </div>
    </div>
  );
}
