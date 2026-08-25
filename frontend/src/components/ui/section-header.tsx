import * as React from 'react'

import { cn } from '@/lib/utils'

export interface SectionHeaderProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  /** Section title (rendered as an h2). */
  title: React.ReactNode
  /** Optional short description. */
  description?: React.ReactNode
  /** Optional trailing action. */
  action?: React.ReactNode
}

/**
 * Section header used to group related content under a page header. Keeps
 * the heading hierarchy intact (h1 → h2 → …) and gives each operational
 * region a scannable label.
 */
const SectionHeader = React.forwardRef<HTMLDivElement, SectionHeaderProps>(
  ({ className, title, description, action, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex items-end justify-between gap-2',
        className
      )}
      {...props}
    >
      <div className="min-w-0 space-y-0.5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h2>
        {description ? (
          <p className="text-xs text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
)
SectionHeader.displayName = 'SectionHeader'

export { SectionHeader }
