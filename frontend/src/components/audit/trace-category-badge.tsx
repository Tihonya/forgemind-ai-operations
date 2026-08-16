/**
 * Trace category badge (AT-012 complete-trace remediation).
 *
 * Renders a readable, color-coded badge for each of the nine canonical trace
 * categories (user action → write action). An icon + text label ensure color
 * is not the only signal. Unknown categories degrade to a neutral badge
 * showing the raw value (no crash, no silent skip).
 */

import {
  Bot,
  Calculator,
  CheckCircle2,
  FilePlus2,
  FileText,
  Package,
  Search,
  Sparkles,
} from 'lucide-react'
import type { ElementType } from 'react'

import { formatTraceCategory } from '@/lib/audit-api'

interface BadgeStyle {
  label: string
  icon: ElementType
  className: string
}

const KNOWN_STYLES: Record<string, BadgeStyle> = {
  user_action: {
    label: 'User action',
    icon: FileText,
    className: 'bg-steel-600/20 text-steel-300 border-steel-600/40',
  },
  deterministic_calculation: {
    label: 'Deterministic calculation',
    icon: Calculator,
    className: 'bg-sky-600/20 text-sky-300 border-sky-600/40',
  },
  retrieval: {
    label: 'Retrieval',
    icon: Search,
    className: 'bg-cyan-600/20 text-cyan-300 border-cyan-600/40',
  },
  model_call: {
    label: 'Model call',
    icon: Bot,
    className: 'bg-violet-600/20 text-violet-300 border-violet-600/40',
  },
  structured_validation: {
    label: 'Structured validation',
    icon: CheckCircle2,
    className: 'bg-indigo-600/20 text-indigo-300 border-indigo-600/40',
  },
  recommendation: {
    label: 'Recommendation',
    icon: Sparkles,
    className: 'bg-amber-600/20 text-amber-300 border-amber-600/40',
  },
  approval_request: {
    label: 'Approval request',
    icon: FilePlus2,
    className: 'bg-sky-600/20 text-sky-300 border-sky-600/40',
  },
  human_decision: {
    label: 'Human decision',
    icon: CheckCircle2,
    className: 'bg-green-600/20 text-green-300 border-green-600/40',
  },
  write_action: {
    label: 'Write action',
    icon: Package,
    className: 'bg-green-600/20 text-green-300 border-green-600/40',
  },
}

const FALLBACK_STYLE: BadgeStyle = {
  label: '',
  icon: FileText,
  className: 'bg-steel-600/20 text-steel-300 border-steel-600/40',
}

interface TraceCategoryBadgeProps {
  category: string
}

export function TraceCategoryBadge({ category }: TraceCategoryBadgeProps) {
  const style = KNOWN_STYLES[category] ?? FALLBACK_STYLE
  const label = KNOWN_STYLES[category]
    ? KNOWN_STYLES[category].label
    : formatTraceCategory(category)
  const Icon = style.icon

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium ${style.className}`}
      data-testid="trace-category-badge"
      data-category={category}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      <span>{label}</span>
    </span>
  )
}
