/**
 * Create-approval-request form (WP-REC-04D).
 *
 * Thin client over POST /approval-requests. The action type is fixed to the
 * single controlled action (CREATE_PROCUREMENT_TASK); the executable
 * component/quantity values are validated by the backend against the
 * deterministic risk engine. Duplicate submission is prevented while a
 * request is in flight.
 */

import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  getApprovalErrorMessage,
  SUPPORTED_ACTION_TYPE,
  type ApprovalRequestCreate,
} from '@/lib/approval-api'

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const INPUT_CLASS =
  'w-full bg-steel-900 border border-steel-600 rounded-md px-3 py-2 text-sm text-white placeholder-steel-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50'

function isValidPositiveDecimal(value: string): boolean {
  const trimmed = value.trim()
  if (trimmed === '') return false
  const num = Number(trimmed)
  return Number.isFinite(num) && num > 0
}

interface CreateApprovalRequestFormProps {
  onCreate: (payload: ApprovalRequestCreate) => Promise<void>
}

export function CreateApprovalRequestForm({
  onCreate,
}: CreateApprovalRequestFormProps) {
  const [recommendationId, setRecommendationId] = useState('')
  const [riskId, setRiskId] = useState('')
  const [componentCode, setComponentCode] = useState('')
  const [quantity, setQuantity] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const canSubmit =
    UUID_PATTERN.test(recommendationId.trim()) &&
    riskId.trim() !== '' &&
    componentCode.trim() !== '' &&
    isValidPositiveDecimal(quantity) &&
    !pending

  function clearFields() {
    setRecommendationId('')
    setRiskId('')
    setComponentCode('')
    setQuantity('')
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setPending(true)
    setError(null)
    setSuccess(false)
    try {
      await onCreate({
        recommendation_id: recommendationId.trim(),
        risk_id: riskId.trim(),
        action_type: SUPPORTED_ACTION_TYPE,
        component_code: componentCode.trim(),
        quantity: quantity.trim(),
      })
      setSuccess(true)
      clearFields()
    } catch (err) {
      setError(getApprovalErrorMessage(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <Card className="bg-steel-900/60 border-steel-700">
      <CardHeader>
        <CardTitle className="text-sm font-medium text-steel-300">
          Create Approval Request
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label
                htmlFor="approval-recommendation-id"
                className="block text-sm font-medium text-steel-300"
              >
                Recommendation ID
              </label>
              <input
                id="approval-recommendation-id"
                type="text"
                value={recommendationId}
                onChange={(e) => setRecommendationId(e.target.value)}
                placeholder="UUID of a validated recommendation"
                disabled={pending}
                className={INPUT_CLASS}
                data-testid="create-recommendation-id"
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="approval-risk-id"
                className="block text-sm font-medium text-steel-300"
              >
                Risk ID
              </label>
              <input
                id="approval-risk-id"
                type="text"
                value={riskId}
                onChange={(e) => setRiskId(e.target.value)}
                placeholder="e.g. RISK-001"
                disabled={pending}
                className={INPUT_CLASS}
                data-testid="create-risk-id"
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="approval-component-code"
                className="block text-sm font-medium text-steel-300"
              >
                Component code
              </label>
              <input
                id="approval-component-code"
                type="text"
                value={componentCode}
                onChange={(e) => setComponentCode(e.target.value)}
                placeholder="e.g. CTRL-X4"
                disabled={pending}
                className={INPUT_CLASS}
                data-testid="create-component-code"
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="approval-quantity"
                className="block text-sm font-medium text-steel-300"
              >
                Quantity
              </label>
              <input
                id="approval-quantity"
                type="text"
                inputMode="decimal"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="Positive quantity"
                disabled={pending}
                className={INPUT_CLASS}
                data-testid="create-quantity"
              />
            </div>
          </div>

          <div className="text-xs text-steel-500">
            Action type:{' '}
            <span className="font-medium text-steel-300" data-testid="create-action-type">
              {SUPPORTED_ACTION_TYPE}
            </span>{' '}
            — the only controlled action supported in this release.
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-md border border-red-600/30 bg-red-600/10 px-3 py-2 text-sm text-red-300"
              data-testid="create-error"
            >
              {error}
            </div>
          )}

          {success && (
            <div
              role="status"
              className="rounded-md border border-green-600/30 bg-green-600/10 px-3 py-2 text-sm text-green-300"
              data-testid="create-success"
            >
              Approval request created.
            </div>
          )}

          <Button type="submit" disabled={!canSubmit} data-testid="create-submit">
            {pending ? 'Creating…' : 'Create approval request'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
