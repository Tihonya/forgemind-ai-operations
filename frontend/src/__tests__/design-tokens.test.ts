/**
 * Design-token invariants (WP-UX-UA-02).
 *
 * These assertions pin the reusable token layer so a future change cannot
 * silently drop a semantic token, a surface level, or a feedback color
 * without a corresponding test failure. They read the two sources of truth:
 *   - tailwind.config.ts (semantic color/radius/shadow/width tokens)
 *   - src/index.css (the HSL custom properties behind those tokens)
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import tailwindConfig from '../../tailwind.config'

type ColorToken = string | { DEFAULT?: string; foreground?: string }

const colors = tailwindConfig.theme?.extend?.colors as
  | Record<string, ColorToken>
  | undefined

const SEMANTIC_COLORS = [
  'border',
  'input',
  'ring',
  'background',
  'foreground',
  'card',
  'popover',
  'secondary',
  'muted',
  'accent',
  'destructive',
  'success',
  'warning',
  'info',
]

describe('design tokens — Tailwind semantic color surface', () => {
  it('defines every semantic color token', () => {
    expect(colors).toBeDefined()
    for (const name of SEMANTIC_COLORS) {
      expect(colors, `missing semantic color "${name}"`).toHaveProperty(name)
    }
  })

  it('defines primary with DEFAULT and foreground (action color)', () => {
    const primary = colors?.primary as { DEFAULT?: string; foreground?: string }
    expect(primary.DEFAULT).toBeDefined()
    expect(primary.foreground).toBeDefined()
  })

  it('defines semantic feedback colors with DEFAULT + foreground', () => {
    for (const name of ['success', 'warning', 'info', 'destructive']) {
      const token = colors?.[name] as { DEFAULT?: string; foreground?: string }
      expect(token.DEFAULT, `${name}.DEFAULT`).toBeDefined()
      expect(token.foreground, `${name}.foreground`).toBeDefined()
    }
  })

  it('defines the radius scale anchored to --radius', () => {
    const radius = tailwindConfig.theme?.extend?.borderRadius as
      | Record<string, string>
      | undefined
    expect(radius).toBeDefined()
    expect(radius?.sm).toBeDefined()
    expect(radius?.md).toBeDefined()
    expect(radius?.lg).toBeDefined()
    expect(radius?.xl).toBeDefined()
  })

  it('defines the surface elevation shadows', () => {
    const shadows = tailwindConfig.theme?.extend?.boxShadow as
      | Record<string, string>
      | undefined
    expect(shadows?.surface).toBeDefined()
    expect(shadows?.['surface-md']).toBeDefined()
    expect(shadows?.drawer).toBeDefined()
  })

  it('defines responsive content widths', () => {
    const maxWidth = tailwindConfig.theme?.extend?.maxWidth as
      | Record<string, string>
      | undefined
    expect(maxWidth?.content).toBeDefined()
    expect(maxWidth?.['content-narrow']).toBeDefined()
  })
})

describe('design tokens — CSS custom properties (index.css)', () => {
  const css = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf-8')

  const REQUIRED_CUSTOM_PROPS = [
    '--background',
    '--foreground',
    '--card',
    '--card-foreground',
    '--popover',
    '--popover-foreground',
    '--primary',
    '--primary-foreground',
    '--secondary',
    '--secondary-foreground',
    '--muted',
    '--muted-foreground',
    '--accent',
    '--accent-foreground',
    '--border',
    '--input',
    '--ring',
    '--destructive',
    '--destructive-foreground',
    '--success',
    '--success-foreground',
    '--warning',
    '--warning-foreground',
    '--info',
    '--info-foreground',
    '--radius',
  ]

  it('declares every required HSL custom property', () => {
    for (const prop of REQUIRED_CUSTOM_PROPS) {
      expect(css, `missing ${prop}`).toContain(prop)
    }
  })

  it('defines a real surface hierarchy (card is elevated above background)', () => {
    // The page canvas and the card surface must not collapse to the same
    // value — otherwise cards lose their visual distinction (the pre-token
    // state where --card equalled --background).
    const background = /--background:\s*([^;]+);/.exec(css)?.[1]
    const card = /--card:\s*([^;]+);/.exec(css)?.[1]
    expect(background).toBeDefined()
    expect(card).toBeDefined()
    expect(card).not.toBe(background)
  })

  it('ships a prefers-reduced-motion rule', () => {
    expect(css).toContain('prefers-reduced-motion')
  })
})
