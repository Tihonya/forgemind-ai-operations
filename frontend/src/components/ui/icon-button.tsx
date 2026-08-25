import * as React from 'react'

import { Button, type ButtonProps } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface IconButtonProps
  extends Omit<ButtonProps, 'children' | 'aria-label' | 'size'> {
  /**
   * Accessible name for the icon-only button. REQUIRED — an icon-only
   * control without a name is invisible to assistive technology. Rendered
   * as the button's ``aria-label``.
   */
  label: string
  /** The icon element (single lucide icon). */
  icon: React.ReactNode
}

/**
 * Accessible icon-button pattern: a square ≥44×44 CSS px control that
 * requires an accessible name. Never conveys meaning through the icon alone.
 */
const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, label, icon, variant = 'ghost', ...props }, ref) => (
    <Button
      ref={ref}
      type="button"
      variant={variant}
      size="icon"
      aria-label={label}
      className={cn(className)}
      {...props}
    >
      {icon}
    </Button>
  )
)
IconButton.displayName = 'IconButton'

export { IconButton }
