/**
 * Trace category badge (AT-012 complete-trace remediation lineage,
 * registry-backed since WP-UX-UA-04).
 *
 * Renders a readable, icon-carrying badge for each of the nine canonical
 * trace categories (user action → write action). Labels come from the
 * localized status registry (``status`` catalog); per-category icons are
 * retained, so color is never the only signal. Unknown categories degrade to
 * a neutral badge that preserves the raw value as technical metadata (no
 * crash, no silent skip).
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

import { useStatusTranslation } from '@/lib/status-i18n'
import { resolveStatus } from '@/lib/status-registry'

/** Per-category non-color cue (icon), retained from the AT-012 surface. */
const CATEGORY_ICONS: Record<string, ElementType> = {
  user_action: FileText,
  deterministic_calculation: Calculator,
  retrieval: Search,
  model_call: Bot,
  structured_validation: CheckCircle2,
  recommendation: Sparkles,
  approval_request: FilePlus2,
  human_decision: CheckCircle2,
  write_action: Package,
}

interface TraceCategoryBadgeProps {
  category: string;
}

export function TraceCategoryBadge({ category }: TraceCategoryBadgeProps) {
  const { t } = useStatusTranslation()
  const entry = resolveStatus('traceCategory', category)
  const Icon = entry.known ? CATEGORY_ICONS[entry.code] ?? FileText : FileText
  const label = t(entry.labelKey)
  const showRaw = !entry.known && entry.code !== ''

  return (
    <span
      className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-steel-600/40 bg-steel-700/40 px-2 py-0.5 text-xs font-medium text-steel-300"
      data-testid="trace-category-badge"
      data-category={category}
      data-code={entry.code}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="min-w-0 break-words">{label}</span>
      {showRaw && (
        <span className="ml-0.5 min-w-0 font-mono text-[10px] opacity-70 break-all">
          {entry.code}
        </span>
      )}
    </span>
  )
}