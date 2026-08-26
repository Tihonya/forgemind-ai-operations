/**
 * Awaiting Decision widget — role-aware (WP-UX-UA-05).
 *
 * Shows the exact count of PENDING approval requests and a CTA to the
 * Approval Center. For roles without approval read authority (AUDITOR,
 * ENGINEER), the widget does NOT issue the forbidden request and instead
 * renders a localized explanatory state — never a red technical failure.
 */

import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { CheckSquare, ArrowRight } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/auth.context'
import { useApprovalRequests } from '@/hooks/use-approval-requests'

/** Backend approval read roles (mirrors ``_READ_ROLES`` in approval.py). */
const APPROVAL_READ_ROLES = new Set([
  'PRODUCTION_MANAGER',
  'PROCUREMENT_SPECIALIST',
  'AI_ADMINISTRATOR',
])

function hasApprovalRead(roles: string[]): boolean {
  return roles.some((r) => APPROVAL_READ_ROLES.has(r.trim().toUpperCase()))
}

export default function AwaitingDecisionWidget() {
  const { t } = useTranslation('dashboard')
  const { user } = useAuth()
  const roles = user?.roles ?? []
  const canViewApprovals = hasApprovalRead(roles)

  const { total: pendingCount, isLoading, isError, refetch } = useApprovalRequests({
    status: 'PENDING',
    limit: 1,
    offset: 0,
    enabled: canViewApprovals,
  })

  if (!canViewApprovals) {
    return (
      <Card data-testid="awaiting-decision-widget">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
            <CheckSquare className="h-4 w-4 text-steel-500" aria-hidden="true" />
            {t('widgets.awaitingDecision.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-steel-400" data-testid="awaiting-decision-role-unavailable">
            {t('widgets.awaitingDecision.roleUnavailable')}
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card data-testid="awaiting-decision-widget">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <CheckSquare className="h-4 w-4 text-steel-500" aria-hidden="true" />
          {t('widgets.awaitingDecision.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="space-y-3" data-testid="awaiting-decision-loading">
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-4 w-32" />
          </div>
        )}

        {isError && (
          <div className="space-y-2" data-testid="awaiting-decision-error">
            <p className="text-sm text-red-400" role="alert">
              {t('widgets.awaitingDecision.error')}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void refetch()
              }}
              data-testid="awaiting-decision-retry"
              className="border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
            >
              {t('common:actions.retry')}
            </Button>
          </div>
        )}

        {!isLoading && !isError && (
          <div className="space-y-3" data-testid="awaiting-decision-content">
            {pendingCount === 0 ? (
              <div data-testid="awaiting-decision-zero">
                <p className="text-sm text-steel-400">
                  {t('widgets.awaitingDecision.zero')}
                </p>
              </div>
            ) : (
              <div data-testid="awaiting-decision-pending">
                <p className="text-2xl font-bold text-white">
                  {pendingCount}
                </p>
                <p className="text-xs text-steel-400">
                  {t('widgets.awaitingDecision.waiting', { count: pendingCount })}
                </p>
              </div>
            )}
            <Button
              asChild
              variant="outline"
              size="sm"
              data-testid="awaiting-decision-cta"
            >
              <Link to="/approval-center">
                {t('widgets.awaitingDecision.review')}
                <ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
