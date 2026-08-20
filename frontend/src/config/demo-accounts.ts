/**
 * WP-P7-04 — intentionally public Release 1 Demo accounts (DEC-056 isolated
 * disposable Demo environment).
 *
 * Single source of truth for the three public identities rendered on the
 * login page. Values are byte-identical to the canonical demo identities
 * defined by the backend seed dataset
 * (backend/app/seed/generator/auth_dataset.py — bcrypt hashes only, no
 * plaintext) and the repository-owned demo-credential contract embedded in
 * the backend integration tests and E2E specs.
 *
 * A bounded backend contract test
 * (backend/tests/integration/test_wp_p7_04_demo_credentials.py) proves these
 * credentials authenticate ONLY their intended canonical demo users over the
 * real auth API and that this module stays in sync with that contract.
 *
 * Non-public identities are deliberately absent from this list. Credentials
 * for any identity not listed here must never be added without a separate
 * Product Owner decision.
 */
export interface DemoAccount {
  /** Canonical demo username (backend seed identity). */
  username: string
  /** Visitor-facing role label. */
  roleLabel: string
  /** Canonical backend role code this identity authenticates as. */
  roleCode: string
  /** Repository-owned public demo credential (deterministic seed contract). */
  password: string
  /** Short visitor-facing description of what the role does. */
  description: string
}

export const DEMO_ACCOUNTS: readonly DemoAccount[] = [
  {
    username: 'manager.demo',
    roleLabel: 'Production Manager',
    roleCode: 'PRODUCTION_MANAGER',
    password: 'ManagerPass123!',
    description: 'Start and review supply-risk workflows',
  },
  {
    username: 'procurement.demo',
    roleLabel: 'Procurement Specialist',
    roleCode: 'PROCUREMENT_SPECIALIST',
    password: 'ProcurementPass123!',
    description: 'Review approvals and procurement actions',
  },
  {
    username: 'auditor.demo',
    roleLabel: 'Auditor',
    roleCode: 'AUDITOR',
    password: 'AuditorPass123!',
    description: 'Inspect workflow and audit history',
  },
]