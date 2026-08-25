import * as React from 'react'

import { cn } from '@/lib/utils'

export interface KeyValueProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Term / label. */
  label: React.ReactNode
  /** Value. */
  children: React.ReactNode
}

/**
 * Compact key–value metadata row. Renders a semantic ``dl``/``dt``/``dd``
 * pair so labels and values remain machine-readable, with safe wrapping for
 * long values (UUIDs, correlation IDs) and long Ukrainian labels.
 */
const KeyValue = React.forwardRef<HTMLDivElement, KeyValueProps>(
  ({ className, label, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex min-w-0 items-start justify-between gap-3 py-1',
        className
      )}
      {...props}
    >
      <dt className="shrink-0 text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-right text-xs font-medium text-foreground">
        {children}
      </dd>
    </div>
  )
)
KeyValue.displayName = 'KeyValue'

export interface KeyValueListProps extends React.HTMLAttributes<HTMLDListElement> {
  children: React.ReactNode
}

/**
 * Wrapper ``dl`` for a list of ``KeyValue`` rows, with an optional divider.
 */
const KeyValueList = React.forwardRef<HTMLDListElement, KeyValueListProps>(
  ({ className, ...props }, ref) => (
    <dl
      ref={ref}
      className={cn('divide-y divide-border', className)}
      {...props}
    />
  )
)
KeyValueList.displayName = 'KeyValueList'

export { KeyValue, KeyValueList }
