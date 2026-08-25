import { useTranslation } from 'react-i18next';

import { useActivePlan } from '@/hooks/useActivePlan';
import ActivePlanWidget from '@/components/dashboard/ActivePlanWidget';
import RiskSummaryWidget from '@/components/dashboard/RiskSummaryWidget';
import HealthWidget from '@/components/dashboard/HealthWidget';
import DatasetStatusWidget from '@/components/dashboard/DatasetStatusWidget';
import LatestAIAnalysisWidget from '@/components/dashboard/LatestAIAnalysisWidget';
import AwaitingDecisionWidget from '@/components/dashboard/AwaitingDecisionWidget';
import { Container } from '@/components/ui/container';
import { PageHeader } from '@/components/ui/page-header';
import { SectionHeader } from '@/components/ui/section-header';

/**
 * Operations Dashboard — WP-UX-UA-02 reference screen.
 *
 * Structure (first-time comprehension):
 *   - PageHeader: page identity + concise purpose.
 *   - "Requires attention now": active plan + risk summary (primary).
 *   - "AI analysis and decisions": latest AI analysis + awaiting decision.
 *   - "Operational status": system health + dataset integrity.
 *
 * Grouping is semantic (<section> regions with h2 headings) so a first-time
 * user can scan purpose → attention → decisions → operations in task-priority
 * order. All values come from real backend responses — no fabricated data.
 *
 * WP-UX-UA-01 pilot boundary (unchanged): the page heading/purpose and the
 * new section headings are localized (dashboard.* catalog). Widget body
 * content remains English — that surface belongs to WP-UX-UA-03.
 */
export default function Dashboard() {
  const { t } = useTranslation('dashboard');
  const { activePlan } = useActivePlan();

  return (
    <Container className="space-y-8" data-testid="dashboard-page">
      <PageHeader title={t('heading')} description={t('purpose')} />

      {/* Primary: what requires attention now */}
      <section aria-label={t('sections.attention.title')} className="space-y-4">
        <SectionHeader
          title={t('sections.attention.title')}
          description={t('sections.attention.description')}
        />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-1">
            <ActivePlanWidget />
          </div>
          <div className="lg:col-span-2">
            <RiskSummaryWidget planCode={activePlan?.code ?? null} />
          </div>
        </div>
      </section>

      {/* AI analysis and pending decisions */}
      <section aria-label={t('sections.analysis.title')} className="space-y-4">
        <SectionHeader
          title={t('sections.analysis.title')}
          description={t('sections.analysis.description')}
        />
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <LatestAIAnalysisWidget />
          <AwaitingDecisionWidget />
        </div>
      </section>

      {/* Operational status */}
      <section aria-label={t('sections.operations.title')} className="space-y-4">
        <SectionHeader
          title={t('sections.operations.title')}
          description={t('sections.operations.description')}
        />
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <HealthWidget />
          <DatasetStatusWidget />
        </div>
      </section>
    </Container>
  );
}
