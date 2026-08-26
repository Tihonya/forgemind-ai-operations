/**
 * StatusBadge (WP-UX-UA-04): localized, tone-consistent status badge.
 *
 * Shows the localized label for a (domain, machine-code) pair with the
 * WP-UX-UA-02 semantic tone and a non-color cue (per-tone icon). The
 * original machine code is preserved — always on ``data-code``/``data-domain``
 * attributes for diagnostics, and visibly inside the badge body when
 * ``showCode`` is set or when the code is unknown (diagnosability contract).
 *
 * Meaning is never conveyed by color alone: every tone carries a distinct
 * icon glyph in addition to its semantic classes. Background/text pairs are
 * the repository-established badge classes, contrast-verified AA against the
 * dark default background (red-300 #fca5a5 10.5:1, amber-300 #fcd34d 13.9:1,
 * emerald-300 #6ee7b7 13.1:1, blue-300 #93c5fd 11.1:1, steel-300 #cbd5e1
 * 13.5:1 — see /tmp/wp-ux-ua-04-visual-evidence/tone-contrast.txt).
 */

import {
  AlertTriangle,
  Circle,
  CircleHelp,
  CheckCircle2,
  Clock,
  XCircle,
  type LucideIcon,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { resolveStatus, type StatusDomain } from '@/lib/status-registry'
import { useStatusTranslation } from '@/lib/status-i18n'

/** Tone → Tailwind classes (repository badge conventions, contrast-verified). */
const TONE_CLASSES: Record<string, string> = {
  neutral: 'bg-steel-700/40 text-steel-300 border-steel-600/40',
  info: 'bg-blue-600/20 text-blue-300 border-blue-600/40',
  success: 'bg-emerald-600/20 text-emerald-300 border-emerald-600/40',
  warning: 'bg-amber-600/20 text-amber-300 border-amber-600/40',
  danger: 'bg-red-600/20 text-red-300 border-red-600/40',
}

/** Tone → default icon (non-color cue). */
const TONE_ICONS: Record<string, LucideIcon> = {
  neutral: Circle,
  info: Clock,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
}

interface StatusBadgeProps {
  domain: StatusDomain
  code: string | null | undefined
  /** Optional icon replacing the tone default. */
  icon?: React.ReactNode
  /** Render the raw machine code (technical metadata) inside the badge. */
  showCode?: boolean
  /** Optional test id override. */
  testId?: string
}

/**
 * Render a localized, tone-consistent status badge.
 */
export default function StatusBadge({
  domain,
  code,
  icon,
  showCode = false,
  testId = 'status-badge',
}: StatusBadgeProps) {
  const entry = resolveStatus(domain, code)
  const { t } = useStatusTranslation()
  const label = t(entry.labelKey)
  const showRaw = (showCode || !entry.known) && entry.code !== ''
  const DefaultIcon = entry.known ? TONE_ICONS[entry.tone] : CircleHelp
  const Icon = icon ?? (DefaultIcon ? <DefaultIcon className="size-3 shrink-0" aria-hidden="true" /> : null)

  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium',
        TONE_CLASSES[entry.tone] ?? TONE_CLASSES.neutral,
      )}
      data-testid={testId}
      data-domain={entry.domain}
      data-code={entry.code ?? ''}
      data-known={entry.known ? 'true' : 'false'}
    >
      {Icon}
      <span className="min-w-0 break-words">{label}</span>
      {showRaw && (
        <span className="ml-0.5 min-w-0 font-mono text-[10px] opacity-70 break-all">
          {entry.code}
        </span>
      )}
    </span>
  )
}