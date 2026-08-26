/**
 * Approval-creation guidance panel (WP-UX-UA-05).
 *
 * Replaces the removed manual UUID form on the Approval Center. The normal
 * creation path begins from a completed AI recommendation (on the risk
 * detail screen), so this panel explains that path and links to it. No blank
 * recommendation-UUID input is presented as a primary workflow.
 */

import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Info, ArrowRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function ApprovalCreateGuidance() {
  const { t } = useTranslation('approval')

  return (
    <Card className="bg-steel-900/60 border-steel-700" data-testid="approval-guidance">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-300">
          <Info className="h-4 w-4 text-steel-500" aria-hidden="true" />
          {t('guidance.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-steel-400">{t('guidance.body')}</p>
        <Button asChild variant="outline" size="sm" className="mt-3">
          <Link to="/supply-risk" data-testid="guidance-cta">
            {t('guidance.cta')}
            <ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  )
}
