/**
 * StatusBadgeExplained (WP-UX-UA-04): StatusBadge with an accessible,
 * tap-reachable explanation popover.
 *
 * Interaction contract (unit-tested + E2E-verified in a hasTouch context):
 * - The trigger is a REAL 44×44-friendly button (min-h-11 / min-w-11 wrap)
 *   with the localized status label as its accessible name.
 * - Click / tap / Enter / Space toggle the popover — hover is NOT required
 *   (and the popover does not depend on Radix hover semantics).
 * - Escape closes the popover and the trigger keeps focus (focus-return
 *   contract by construction).
 * - Outside pointerdown while open closes it (announced via
 *   ``aria-expanded``).
 * - The popover is aria-controlled by the trigger and carries the
 *   localized plain-language explanation; unknown codes keep the raw
 *   machine code visible for diagnosis.
 *
 * No animation is used, so reduced-motion preferences are not violated.
 */

import { useEffect, useId, useRef, useState } from 'react'

import StatusBadge from '@/components/status/StatusBadge'
import { resolveStatus, type StatusDomain } from '@/lib/status-registry'
import { useStatusTranslation } from '@/lib/status-i18n'

interface StatusBadgeExplainedProps {
  domain: StatusDomain
  code: string | null | undefined
  showCode?: boolean
  testId?: string
}

export default function StatusBadgeExplained({
  domain,
  code,
  showCode = false,
  testId,
}: StatusBadgeExplainedProps) {
  const entry = resolveStatus(domain, code)
  const { t } = useStatusTranslation()
  const [open, setOpen] = useState(false)
  const popoverId = useId()
  const rootRef = useRef<HTMLSpanElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  // Outside pointerdown closes the popover (tap-away dismissal).
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: Event) => {
      if (
        rootRef.current &&
        !rootRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  return (
    <span ref={rootRef} className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        aria-label={t(entry.labelKey)}
        aria-expanded={open}
        aria-controls={popoverId}
        onClick={() => {
          setOpen((current) => !current)
          if (!open) triggerRef.current?.focus()
        }}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && open) {
            setOpen(false)
            triggerRef.current?.focus()
          }
        }}
        className="inline-flex max-w-full cursor-help items-center justify-center rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="flex min-h-11 min-w-11 items-center justify-center">
          <StatusBadge
            domain={domain}
            code={code}
            showCode={showCode}
            testId={testId}
          />
        </span>
      </button>
      {open && (
        <span
          id={popoverId}
          role="note"
          className="absolute left-0 top-full z-50 mt-1 max-w-72 rounded-md border border-steel-700 bg-steel-800 px-3 py-2 text-xs leading-relaxed text-steel-200 shadow-md"
        >
          {t(entry.descriptionKey)}
          {!entry.known && entry.code !== '' && (
            <span className="mt-1 block break-all font-mono text-[10px] text-steel-400">
              {entry.code}
            </span>
          )}
        </span>
      )}
    </span>
  )
}