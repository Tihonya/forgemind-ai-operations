import * as React from 'react'

import { cn } from '@/lib/utils'

export interface ContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Narrower reading/forms width; default is the wide operational width. */
  narrow?: boolean
}

/**
 * Responsive content container. Centers content with the shared content
 * widths (see tailwind.config.ts ``maxWidth``) and applies consistent
 * horizontal padding, so changed surfaces never re-invent gutter spacing.
 */
const Container = React.forwardRef<HTMLDivElement, ContainerProps>(
  ({ className, narrow = false, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'mx-auto w-full px-4 sm:px-6',
        narrow ? 'max-w-content-narrow' : 'max-w-content',
        className
      )}
      {...props}
    />
  )
)
Container.displayName = 'Container'

export { Container }
