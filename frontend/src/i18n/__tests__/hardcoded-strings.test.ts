/**
 * Hardcoded-visible-English gate (WP-UX-UA-03 §10).
 *
 * Scans non-test `.tsx`/`.jsx` source for *likely user-visible* hardcoded
 * English strings and fails when a new one appears. It is deliberately not a
 * raw grep:
 *
 * - it only inspects JSX text nodes and the user-facing attributes
 *   `aria-label`, `title`, `placeholder`, `alt` (never `data-testid`,
 *   `className`, `id`, `src`, `href`, API paths, or imports);
 * - it only flags *multi-word Latin phrases* (two or more alphabetic words),
 *   which are the strong signal of visible copy — single tokens such as
 *   machine codes (`PENDING`, `CRITICAL`), component codes, CSS classes, and
 *   TypeScript types (`Promise`, `Record`, …) are intentionally ignored;
 * - every remaining legitimate phrase is listed in `ALLOWLIST` below with a
 *   mandatory reason, so an unexplained English sentence cannot slip through
 *   review without an audit trail.
 *
 * The gate does not claim completeness — it is a regression tripwire for the
 * most common class of missed migration (a literal English sentence or label
 * left in JSX). Manual review of the allowlist is required on every change.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Allowlist of remaining hardcoded phrases, each with the reason it is not
 * interface copy (machine/status content, a brand/product name, or a
 * developer-only string). Review every entry before changing it.
 */
const ALLOWLIST: Record<string, string> = {
  // Product name — rendered as the application brand mark, not localizable copy.
  'Supply Risk Intelligence':
    'ForgeMind product subtitle (brand name), intentionally not translated',
  // Dataset status is a raw machine value; its localized registry is WP-UX-UA-04.
  'Not Loaded': 'Raw dataset status label owned by the WP-UX-UA-04 status registry',
}

/** User-facing attributes whose literal string values are visible copy. */
const VISIBLE_ATTRS = ['aria-label', 'title', 'placeholder', 'alt'] as const

/** Matches a multi-word Latin phrase (two or more alphabetic words). */
const ENGLISH_PHRASE = /\b[A-Za-z]{2,}\b(?:[ '’-][A-Za-z]{2,}\b)+/

/** Matches JSX text nodes: content between `>` and `<`, excluding `{}`/nested tags. */
const JSX_TEXT = />([^<>{}]{2,120})</g

interface Finding {
  file: string
  line: number
  source: 'text' | 'aria-label' | 'title' | 'placeholder' | 'alt'
  text: string
}

function isSourceFile(name: string): boolean {
  return (
    (name.endsWith('.tsx') || name.endsWith('.jsx')) &&
    !name.endsWith('.test.tsx') &&
    !name.endsWith('.spec.tsx')
  )
}

function collectSourceFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules') continue
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      out.push(...collectSourceFiles(full))
    } else if (isSourceFile(entry.name)) {
      out.push(full)
    }
  }
  return out
}

function stripComments(src: string): string {
  // Block comments and line comments, preserving line positions with blanks.
  return src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/\/\/[^\n]*/g, (m) => m.replace(/[^\n]/g, ' '))
}

function scanFile(file: string): Finding[] {
  const src = stripComments(readFileSync(file, 'utf8'))
  const lines = src.split('\n')
  const rel = relative(process.cwd(), file)
  const findings: Finding[] = []

  const check = (lineNo: number, text: string, source: Finding['source']) => {
    const trimmed = text.trim()
    if (trimmed.length < 3) return
    if (ENGLISH_PHRASE.test(trimmed)) {
      findings.push({ file: rel, line: lineNo, source, text: trimmed })
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    // JSX text nodes.
    JSX_TEXT.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = JSX_TEXT.exec(line)) !== null) {
      check(i + 1, m[1], 'text')
    }
    // Visible attributes.
    for (const attr of VISIBLE_ATTRS) {
      const attrRe = new RegExp(`${attr}=\\{?"([^"]{2,120})"`, 'g')
      let am: RegExpExecArray | null
      while ((am = attrRe.exec(line)) !== null) {
        check(i + 1, am[1], attr)
      }
    }
  }
  return findings
}

describe('hardcoded-visible-English gate (WP-UX-UA-03 §10)', () => {
  it('finds no unexplained multi-word English phrase in non-test TSX/JSX', () => {
    const srcDir = join(process.cwd(), 'src')
    const files = collectSourceFiles(srcDir)
    expect(files.length).toBeGreaterThan(0)

    const violations: Finding[] = []
    for (const file of files) {
      for (const finding of scanFile(file)) {
        if (ALLOWLIST[finding.text] === undefined) {
          violations.push(finding)
        }
      }
    }

    expect(
      violations,
      violations
        .map(
          (v) =>
            `${v.file}:${v.line} [${v.source}] ${JSON.stringify(v.text)}`,
        )
        .join('\n'),
    ).toEqual([])
  })

  it('every allowlist entry carries a non-empty reason', () => {
    for (const [phrase, reason] of Object.entries(ALLOWLIST)) {
      expect(phrase, phrase).toMatch(ENGLISH_PHRASE)
      expect(reason, phrase).toBeTruthy()
    }
  })
})
