import { NavLink } from 'react-router-dom'

import { cn } from '@/lib/utils'
import type { NavigationItem } from './navigation-config'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface NavigationItemProps {
  item: NavigationItem
}

/**
 * Single navigation entry rendered inside the sidebar.
 *
 * - Active routes (path defined): NavLink with active-state styling.
 * - Future-phase items (phase defined): disabled element with tooltip.
 */
export default function NavigationEntry({ item }: NavigationItemProps) {
  if (item.phase !== undefined) {
    return <DisabledFutureModule item={item} />
  }

  if (!item.path) {
    return null
  }

  const Icon = item.icon

  return (
    <NavLink
      to={item.path}
      end={item.path === '/'}
      className={({ isActive: navActive }) =>
        cn(
          'flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors border-l-2',
          navActive
            ? 'bg-steel-800 text-white border-primary-500'
            : 'text-steel-400 border-transparent hover:bg-steel-800/50 hover:text-steel-100'
        )
      }
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      <span>{item.label}</span>
    </NavLink>
  )
}

interface DisabledFutureModuleProps {
  item: NavigationItem
}

function DisabledFutureModule({ item }: DisabledFutureModuleProps) {
  const Icon = item.icon

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            role="menuitem"
            aria-disabled="true"
            data-testid={`nav-disabled-${item.id}`}
            className="flex items-center gap-3 px-4 py-2.5 text-sm text-steel-600 border-l-2 border-transparent cursor-not-allowed select-none"
            onClick={(e) => e.preventDefault()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
              }
            }}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            <span>{item.label}</span>
            <span className="ml-auto text-xs text-steel-500">Phase {item.phase}</span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          <p>Available in Phase {item.phase}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
