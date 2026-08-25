import * as React from 'react'

import { cn } from '@/lib/utils'

export interface PageHeaderProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  /** Primary page/screen title. */
  title: React.ReactNode
  /** Concise purpose text shown under the title. */
  description?: React.ReactNode
  /** Optional primary action rendered on the trailing edge. */
  action?: React.ReactNode
}

/**
 * Consistent page header: an h1 title, a purpose line, and an optional
 * primary action. Establishes a single heading hierarchy across screens so
 * the page identity is always clear to a first-time user.
 */
const PageHeader = React.forwardRef<HTMLDivElement, PageHeaderProps>(
  ({ className, title, description, action, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between',
        className
      )}
      {...props}
    >
      <div className="min-w-0 space-y-1">
        <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
          {title}
        </h1>
        {description ? (
          <p className="text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
)
PageHeader.displayName = 'PageHeader'

export { PageHeader }
