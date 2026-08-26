/**
 * Reusable component: renders the AI recommendation for a single risk
 * extracted from a workflow run's validated recommendation content.
 *
 * Used by:
 * - Supply Risk Detail (WP-UX-02) — compact/current-risk mode
 * - Workflow Run Detail (future) — full mode
 *
 * The component visibly separates four concepts:
 * A. Deterministic fact (contextual line — the risk is calculated, not AI)
 * B. AI recommendation (summary, impact, actions, rationale, approval)
 * C. Evidence used (RAG source references)
 * D. Human control (approval-required boundary)
 *
 * Localized per WP-UX-UA-03: interface chrome (labels, headings, actions) is
 * localized; provider/model-generated summary, impact, action title/rationale
 * and document identifiers remain untranslated (U5 owns model-output language).
 */

import { useTranslation } from 'react-i18next'
import { AlertCircle, ShieldCheck, FileText, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { SUPPORTED_ACTION_TYPE } from '@/lib/approval-api'
import type {
  RecommendedAction,
  RecommendationContent,
  RecommendationResponse,
  RecommendationRisk,
} from '@/lib/workflow-api'

interface RecommendationForRiskProps {
  /** The full recommendation response from the workflow run detail. */
  recommendation: RecommendationResponse | null;
  /** The risk_id to find inside the recommendation content (e.g. RISK-001). */
  riskId: string;
  /** The workflow run UUID, used for the "View full AI analysis" CTA. */
  runId: string;
  /** Invoked when the user selects "Передати на погодження" for an eligible action. */
  onSubmitForApproval?: (action: RecommendedAction) => void;
}

/**
 * Find the matching risk recommendation item by risk_id inside the
 * validated recommendation content. Returns null if not found or
 * if no content exists.
 */
function findRiskRecommendation(
  recommendation: RecommendationResponse | null,
  riskId: string,
): RecommendationRisk | null {
  if (recommendation === null) return null
  const content: RecommendationContent | null = recommendation.content
  if (content === null) return null
  return content.risks.find((r) => r.risk_id === riskId) ?? null
}

export default function RecommendationForRisk({
  recommendation,
  riskId,
  runId,
  onSubmitForApproval,
}: RecommendationForRiskProps) {
  const { t } = useTranslation('riskDetail')

  // COMPLETED + recommendation null — controlled integrity/absence state.
  if (recommendation === null) {
    return (
      <Card data-testid="recommendation-panel">
        <CardHeader>
          <CardTitle>{t('recommendation.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p
            className="text-sm text-muted-foreground"
            data-testid="no-recommendation-row"
          >
            {t('recommendation.noRecommendation')}
          </p>
          <Button asChild variant="outline" size="sm" className="mt-3">
            <Link to={`/workflow-runs/${runId}`} data-testid="view-full-analysis-no-rec">
              {t('recommendation.viewFullAnalysis')}
            </Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  // COMPLETED + content null — validated row exists but content is empty.
  if (recommendation.content === null) {
    return (
      <Card data-testid="recommendation-panel">
        <CardHeader>
          <CardTitle>{t('recommendation.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p
            className="text-sm text-muted-foreground"
            data-testid="no-validated-content"
          >
            {t('recommendation.noValidatedContent')}
          </p>
          <Button asChild variant="outline" size="sm" className="mt-3">
            <Link to={`/workflow-runs/${runId}`} data-testid="view-full-analysis-no-content">
              {t('recommendation.viewFullAnalysis')}
            </Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  const riskRec = findRiskRecommendation(recommendation, riskId)

  // COMPLETED + recommendation exists but does NOT contain the current risk.
  if (riskRec === null) {
    return (
      <Card data-testid="recommendation-panel">
        <CardHeader>
          <CardTitle>{t('recommendation.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p
            className="text-sm text-muted-foreground"
            data-testid="no-recommendation-for-risk"
          >
            {t('recommendation.noRecommendationForRisk')}
          </p>
          <Button asChild variant="outline" size="sm" className="mt-3">
            <Link to={`/workflow-runs/${runId}`} data-testid="view-full-analysis-absent">
              {t('recommendation.viewFullAnalysis')}
            </Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  // COMPLETED + matching current-risk recommendation — full presentation.
  const hasApprovalAction = riskRec.recommended_actions.some(
    (a) => a.requires_approval,
  )

  // The single controlled action eligible for approval creation (WP-UX-UA-05):
  // the supported action type that requires approval. Only this action can
  // originate an approval request; no identifier is parsed from display text.
  const eligibleAction =
    riskRec.recommended_actions.find(
      (a) => a.action_type === SUPPORTED_ACTION_TYPE && a.requires_approval,
    ) ?? null

  return (
    <Card data-testid="recommendation-panel">
      <CardHeader>
        <CardTitle>{t('recommendation.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* A. Deterministic fact — contextual line */}
        <div className="text-xs text-muted-foreground" data-testid="deterministic-context">
          <AlertCircle className="inline h-3 w-3 mr-1" aria-hidden="true" />
          {t('recommendation.deterministicContext')}
        </div>

        {/* B. AI Recommendation */}
        <div className="space-y-3" data-testid="ai-recommendation-content">
          <div>
            <span className="text-xs font-medium text-muted-foreground">{t('recommendation.aiSummary')}</span>{' '}
            <span className="text-sm" data-testid="rec-summary">{riskRec.summary}</span>
          </div>
          <div>
            <span className="text-xs font-medium text-muted-foreground">{t('recommendation.businessImpact')}</span>{' '}
            <span className="text-sm" data-testid="rec-business-impact">{riskRec.business_impact}</span>
          </div>
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{t('recommendation.recommendedActions')}</span>
            {riskRec.recommended_actions.map((action, idx) => (
              <div
                key={idx}
                className="ml-4 space-y-0.5 text-sm"
                data-testid={`rec-action-${idx}`}
              >
                <span className="font-medium">{action.title}</span>{' '}
                <span className="text-xs text-muted-foreground">({action.action_type})</span>
                <div className="text-xs text-muted-foreground" data-testid={`rec-action-rationale-${idx}`}>
                  {action.rationale}
                </div>
                {action.requires_approval && (
                  <div className="text-xs text-amber-300" data-testid={`rec-action-approval-${idx}`}>
                    {t('recommendation.humanApprovalRequired')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* C. Evidence Used */}
        {riskRec.sources.length > 0 && (
          <div className="space-y-1" data-testid="evidence-used">
            <span className="text-xs font-medium text-muted-foreground flex items-center gap-1">
              <FileText className="h-3 w-3" aria-hidden="true" />
              {t('recommendation.evidenceUsed')}
            </span>
            {riskRec.sources.map((source, idx) => (
              <div
                key={idx}
                className="ml-4 text-xs text-muted-foreground"
                data-testid={`evidence-source-${idx}`}
              >
                {source.document_id} (v{source.version})
              </div>
            ))}
          </div>
        )}

        {/* D. Human Control — approval boundary */}
        {hasApprovalAction && (
          <div
            className="flex items-start gap-2 rounded-md border border-amber-600/30 bg-amber-600/10 px-3 py-2"
            data-testid="human-approval-boundary"
          >
            <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-400" aria-hidden="true" />
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-300">
                {t('recommendation.humanApprovalRequired')}
              </p>
              <p className="mt-0.5 text-xs text-amber-400/80">
                {t('recommendation.approvalBoundary')}
              </p>
            </div>
          </div>
        )}

        {/* Primary action — guided approval creation (WP-UX-UA-05) */}
        {eligibleAction && onSubmitForApproval && (
          <Button
            onClick={() => onSubmitForApproval(eligibleAction)}
            data-testid="submit-for-approval"
          >
            {t('recommendation.submitForApproval')}
            <ArrowRight className="ml-1 h-4 w-4" aria-hidden="true" />
          </Button>
        )}

        {hasApprovalAction && !eligibleAction && (
          <p className="text-xs text-muted-foreground" data-testid="no-eligible-action">
            {t('recommendation.noEligibleAction')}
          </p>
        )}

        {/* Next action — View full AI analysis */}
        <Button asChild variant="outline" size="sm">
          <Link to={`/workflow-runs/${runId}`} data-testid="view-full-analysis">
            {t('recommendation.viewFullAnalysis')}
          </Link>
        </Button>
      </CardContent>
    </Card>
  )
}
