import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

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
 * Single navigation entry rendered inside the sidebar (or the mobile
 * navigation surface).
 *
 * - Active routes (path defined): NavLink with active-state styling.
 * - Future-phase items (phase defined): disabled element with tooltip.
 * - Labels are resolved through ``item.labelKey`` (localized per the
 *   active locale); routes, permission filtering, disabled-state behavior
 *   and stable IDs are untouched (WP-UX-UA-01 boundary).
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
      data-testid={`nav-link-${item.id}`}
      className={({ isActive: navActive }) =>
        cn(
          'flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors border-l-2',
          navActive
            ? 'bg-accent text-accent-foreground border-primary'
            : 'text-muted-foreground border-transparent hover:bg-accent/50 hover:text-foreground'
        )
      }
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      <LocalizedLabel item={item} />
    </NavLink>
  )
}

interface DisabledFutureModuleProps {
  item: NavigationItem
}

function DisabledFutureModule({ item }: DisabledFutureModuleProps) {
  const { t } = useTranslation('shell')
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
            <LocalizedLabel item={item} />
            <span className="ml-auto text-xs text-steel-500">
              {t('phaseMarker')}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          <p>{t('phaseAvailable')}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

/**
 * Resolve the display label for a navigation item through the catalog.
 * When no i18n context is available the stable English ``item.label`` is
 * the safe fallback (never a crash).
 */
function LocalizedLabel({ item }: { item: NavigationItem }) {
  const { t, i18n } = useTranslation('shell')
  const translated =
    item.labelKey && i18n.exists(item.labelKey) ? t(item.labelKey) : item.label
  return <span>{translated}</span>
}