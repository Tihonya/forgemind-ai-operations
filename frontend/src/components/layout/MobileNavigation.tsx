/**
 * Accessible mobile navigation drawer (WP-UX-UA-01).
 *
 * At narrow viewports the desktop sidebar is hidden and this surface
 * carries the primary navigation. Uses existing repository primitives
 * (buttons, steel tokens) only — no new component library.
 *
 * Accessibility contract:
 * - opened by an accessible trigger (menu button in the Header);
 * - role=dialog + aria-modal, labelled;
 * - focus moves into the drawer on open;
 * - Tab focus stays inside while open (no inaccessible focus trap);
 * - Escape closes the drawer;
 * - focus returns to the trigger after close;
 * - selecting a navigation item closes the surface;
 * - the underlying shell is inert while open (background content cannot
 *   receive keyboard focus through the overlay).
 */

import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { LogOut, X } from 'lucide-react'

import type { AuthUser } from '@/contexts/auth.context'
import { ROLE_LABEL_KEYS } from './navigation/navigation-config'
import {
  normalizeRoles,
  useNavigationPermissions,
} from './navigation/useNavigationPermissions'
import NavigationEntry from './navigation/NavigationItem'
import { Button } from '@/components/ui/button'

interface MobileNavigationProps {
  open: boolean
  onClose: () => void
  user: AuthUser
  onLogout: () => void
  /** Element to restore focus to when the drawer closes (the menu trigger). */
  returnFocusRef: React.RefObject<HTMLElement | null>
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

export default function MobileNavigation({
  open,
  onClose,
  user,
  onLogout,
  returnFocusRef,
}: MobileNavigationProps) {
  const { t } = useTranslation('shell')
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)

  const displayName = user.display_name ?? user.username
  const normalized = normalizeRoles(user.roles)
  const primaryRole = Array.from(normalized)[0]
  const roleLabel = primaryRole ? t(ROLE_LABEL_KEYS[primaryRole]) : t('roleLabels.unknown')
  const { navigationItems } = useNavigationPermissions(user.roles)

  // Move focus into the drawer on open; restore on close.
  useEffect(() => {
    if (open) {
      closeButtonRef.current?.focus()
    } else {
      returnFocusRef.current?.focus()
    }
  }, [open, returnFocusRef])

  // Escape closes; focus stays cyclical within the drawer.
  useEffect(() => {
    if (!open) return
    const dialog = dialogRef.current
    if (!dialog) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => el.offsetParent !== null || el === document.activeElement)
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey) {
        if (document.activeElement === first || !dialog.contains(document.activeElement)) {
          event.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last || !dialog.contains(document.activeElement)) {
          event.preventDefault()
          first.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 md:hidden"
      role="presentation"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div
        ref={dialogRef}
        id="mobile-navigation-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={t('mobileMenu.ariaLabel')}
        className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-border bg-card shadow-drawer"
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-steel-700 px-4">
          <span className="text-sm font-semibold text-white">ForgeMind</span>
          <Button
            ref={closeButtonRef}
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label={t('mobileMenu.close')}
            data-testid="mobile-menu-close"
            className="min-h-11 min-w-11 text-steel-300 hover:text-white hover:bg-steel-700"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </Button>
        </div>

        {/* Role-aware navigation; selecting an item closes the surface */}
        <nav
          aria-label={t('a11y.primaryNav')}
          className="flex-1 overflow-y-auto px-4 py-6 space-y-1"
          onClickCapture={(e) => {
            const target = e.target as HTMLElement
            if (target.closest('a[href]')) onClose()
          }}
        >
          {navigationItems.map((item) => (
            <NavigationEntry key={item.id} item={item} />
          ))}
        </nav>

        {/* User summary + sign-out stay reachable on mobile */}
        <div className="border-t border-steel-700 px-5 py-4 space-y-4">
          <div className="flex w-full items-center gap-3" data-testid="mobile-user-summary">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-steel-700 text-xs font-semibold text-white">
              {displayName.slice(0, 2).toUpperCase()}
            </div>
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-sm font-medium text-white">
                {displayName}
              </span>
              <span className="truncate text-xs text-steel-400">{roleLabel}</span>
            </div>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={onLogout}
            data-testid="mobile-menu-logout"
            className="flex w-full items-center justify-center gap-2 min-h-11 text-steel-300 hover:text-white hover:bg-steel-700"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            {t('signOut')}
          </Button>
        </div>
      </div>
    </div>
  )
}