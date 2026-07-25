# WP-3.8 Specification — AT-005 Frontend Data-Fidelity Contract Tests

**Status:** APPROVED FOR IMPLEMENTATION
**Work Package:** WP-3.8
**Phase:** 3 (Core UI)
**Base:** main at 945a53d768fff54746c454dc02a6e131f709ecb8
**Branch:** feature/phase-3-wp-3-8-at005-frontend-test
**Depends on:** WP-3.7 (merged)

---

## 1. Objective

Deliver frontend Vitest + React Testing Library contract test coverage for **AT-005 — No hidden UI mocks**.

**Canonical proof required:**
> When backend-shaped test fixture values change, the frontend renders the changed values without any production-source modification or Golden Scenario-specific fallback logic.

This WP is **pure frontend contract coverage**. It uses mocked API contract responses / hook returns. It does **not** use a live backend, seeded database, or Playwright.

---

## 2. Backend Contract Reference (for test shapes)

Use the exact `RiskRecordWithId` and `RiskSummary` shapes from `frontend/src/lib/risks-api.ts` and supporting detail types from `risk-detail-api.ts`.

All mocked data in tests **must** match the TypeScript contract (string decimals for quantities, valid severities, etc.).

---

## 3. Approved Test Architecture

1. **Prefer extending existing tests** for:
   - Dashboard widgets (`ActivePlanWidget`, `RiskSummaryWidget`)
   - Supply Risk list (`RiskList`)
   - Evidence / Risk summary panels (`EvidencePanel`, `RiskSummary`)
   - Supply Risk Detail flow
   - Navigation permissions / role visibility

2. One small AT-005-focused contract suite or additions inside existing files is permitted to connect the acceptance evidence.

3. **Shared test-only fixture** (`frontend/src/test/fixtures/risk-contract.ts`) allowed **only if reused by at least three test files**. Must be test-only; no production code may import it.

Keep fixtures simple:
- Canonical fixture factory / data matching contract
- Mutated fixture factory or overrides
- Unmistakably non-canonical mutation values (see §6)
- No business-rule assertions on mutated values

---

## 4. Required AT-005 Evidence

### A. Dashboard
- Canonical active-plan fixture renders fixture plan code / period / status.
- Risk-summary counts derive from (or are consistent with) supplied risks data.
- Mutation of plan code or risk severity / count changes rendered output exactly.

### B. Supply Risk List
- Canonical risk records render in expected severity-descending order.
- `risk_id`, `component_*`, `severity`, `shortage`, `available`, `required` come from fixtures.
- A clearly non-canonical mutation (e.g. shortage `37.2500`, `PLAN-TEST-MUTATED`, custom component name) is rendered exactly.
- Filtering and ordering continue to operate correctly on mutated fixture data.

### C. Supply Risk Detail
- Selected risk evidence values (required/available/confirmed_*/shortage/component/wo/plan) come from fixture.
- Mutate required, available, confirmed_early, confirmed_late, shortage, component_name, affected_wo_code, plan_code.
- UI renders the mutated values exactly.
- Frontend **does not recalculate** shortage (displays backend value as-is).
- Any formula label remains purely descriptive.

### D. Role Visibility Regression
- Uppercase backend role codes continue to normalize correctly (`PRODUCTION_MANAGER` → `production_manager` etc.).
- `production_manager` and `procurement_specialist` see Supply Risk Analysis.
- `ai_administrator` and `auditor` do **not** see Supply Risk Analysis.
- No invention of route-level authorization (UX only, per Phase 3 rules).

---

## 5. Explicit Mutation Values (test-only)

Use unmistakably non-canonical values, e.g.:
- `plan_code`: `PLAN-TEST-MUTATED`
- `component_name`: `Mutated Test Component`
- `shortage`: `37.2500`
- `severity`: `LOW`
- Other fields as needed for readability.

These must appear in rendered output in the corresponding tests.

---

## 6. Production Anti-Hardcode Policy

**Scan target:** `frontend/src` production `.ts`/`.tsx` files, **excluding**:
- `*.test.*`
- `**/__tests__/**`
- `**/test/**`

**Forbidden runtime literals (must be zero in scanned files):**
- `PLAN-2026-W31`
- `RISK-001`, `RISK-002`, `RISK-003`
- `CTRL-X4`, `MOTOR-M2`, `SENSOR-L9`
- Canonical work-order IDs (e.g. `WO-2026-0142`)
- Golden Scenario dates used as defaults
- Branches/defaults tied to canonical shortages 8/6/5 (contextual to Golden)

Generic numeric formatting or unrelated numbers are **not** flagged.

Existing non-executable JSDoc examples (e.g. in `risks-api.ts`) are reported separately; do not edit unless required for test clarity.

---

## 7. Critical Semantic Rules

- Tests verify **data fidelity** (UI displays what is supplied), **not** backend formula correctness.
- Do **not** recalculate shortage in tests or production.
- Do **not** assert that mutated values obey business rules.
- Mocked responses / hook returns **must** match actual TS/backend contracts.
- No hidden production mocks or Golden-specific fallbacks.
- Behavior-focused assertions only. No snapshots for business values.

---

## 8. Explicitly Out of Scope

- Playwright / Golden Scenario E2E (WP-3.9)
- Real backend, seeded DB, or live API calls in these tests
- Any production feature, UI, or component changes (unless a genuine defect is discovered — stop and report)
- Backend changes, new endpoints, schema changes
- UI redesign, table ergonomics, widget retry architecture
- `make seed` fixes, global auth hardening
- Generated reports or handoff files
- Broad global mocks or skipped tests

If a test exposes a real production defect:
1. Stop implementation.
2. Report the defect + minimal fix.
3. Obtain explicit approval before any prod source edit.

---

## 9. Files Allowed to Change

```
docs/planning/wp_3_8_at005_frontend_contract_spec.md   (new)
frontend/src/test/fixtures/risk-contract.ts             (new — test only)
frontend/src/components/supply-risk/__tests__/RiskList.test.tsx
frontend/src/components/supply-risk/__tests__/EvidencePanel.test.tsx
frontend/src/components/dashboard/__tests__/RiskSummaryWidget.test.tsx
frontend/src/components/dashboard/__tests__/ActivePlanWidget.test.tsx
frontend/src/routes/__tests__/supply-risk-detail.test.tsx
frontend/src/hooks/useRiskDetail.test.tsx
frontend/src/components/layout/navigation/useNavigationPermissions.test.ts
frontend/src/lib/risks-api.test.ts   (optional for aggregate fidelity)
```

**Files that MUST NOT change:**
- All production `frontend/src/**/*.ts(x)` (except via approved defect fix)
- Any WP-3.9 files
- Backend, seed, infra, docker, Makefile, SoT docs, planning phase handoff, HERMES.md

---

## 10. Test Quality Requirements

- Isolated `QueryClient` per test (or proper wrapper).
- Explicit, readable fixture mutation.
- No `act` warnings, no unhandled promise rejections.
- No snapshots for business data.
- No skipped tests.
- No weakening of existing assertions.
- Behavior assertions only.

---

## 11. Verification Gates (under Node 22.18.0)

```bash
. "$NVM_DIR/nvm.sh" && nvm use 22
npm ci
npm run lint
npm run type-check
npm test
npm run build
npm run test:e2e
make lint
```

All must pass. Report exact counts (passed/failed/skipped).

---

## 12. Pre-Commit Review Checklist (focused)

- Only authorized test + spec + fixture files changed.
- Production source unchanged (or defect reported + approved).
- No WP-3.9 / Playwright Golden work.
- Anti-hardcode scan clean (document result).
- Fixture not imported by production code.
- All new fixtures are under `test/` or `__tests__`.
- Single intentional commit with message:
  `test(frontend): add AT-005 data-fidelity coverage`

---

## 13. Acceptance Criteria

- [ ] AT-005 evidence matrix (A–D) passes with explicit non-canonical mutations.
- [ ] Shared fixture reused in ≥3 test files.
- [ ] All existing tests continue to pass at full strength.
- [ ] No production hardcodes introduced or present.
- [ ] No snapshots for business values.
- [ ] All gates green under Node 22.
- [ ] Single commit, clean tree after.
- [ ] No Docker infrastructure changes.
- [ ] WP-3.9 not started.

---

## 14. Implementation Sequence

1. Create spec (this file).
2. Create shared test fixture.
3. Extend existing tests with required canonical + mutated cases.
4. Add role normalization regression coverage.
5. Run full gate suite (with nvm).
6. Anti-hardcode scan + document.
7. Focused review against checklist.
8. Stage only intended files.
9. Single commit.
10. Stop. Report exact results.

**END OF WP-3.8 SPECIFICATION**