# 07. Delivery Roadmap

Roadmap побудовано вертикально: кожна фаза завершується перевірюваним результатом.

## Phase 0 — Repository and governance

### Deliverables
- repository structure;
- Source of Truth documents;
- branch strategy;
- CI skeleton;
- issue/task template;
- Decision Log.

### Exit criteria
- документи затверджені;
- Definition of Done незмінно зафіксований;
- CI запускається хоча б із placeholder checks.

## Phase 1 — Running skeleton

### Deliverables
- React frontend;
- FastAPI backend;
- PostgreSQL;
- migrations;
- health checks;
- Docker Compose;
- basic login page.

### Exit criteria
- clean deployment;
- frontend → backend connection;
- backend → database connection;
- automated smoke test.

## Phase 2 — Synthetic ERP core

### Deliverables
- business schema;
- seed generator;
- Golden Dataset;
- CRUD/read APIs;
- deterministic risk engine.

### Exit criteria
- AT-003, AT-004, AT-005 pass;
- жодної LLM-залежності.

## Phase 3 — Core UI

### Deliverables
- Dashboard;
- risk list;
- risk details;
- evidence calculation view;
- responsive desktop layout.

### Exit criteria
- UI працює з real backend data;
- no hardcoded result;
- frontend tests pass.

## Phase 4 — Knowledge and RAG

**Status:** PARTIALLY COMPLETE — substantial RAG and role-filtering implementation exists (document ingestion, pgvector index, retrieval with citations, role-filtered retrieval, DocumentPermission model, server-side role derivation, unauthorized-role test); formal AT-006/AT-007 PASS evidence is incomplete. This is a documentation/status and acceptance-evidence contradiction, not a false technical foundation.

### Deliverables
- document ingestion;
- document versions/status;
- pgvector index;
- retrieval;
- access filtering;
- citations.

### Exit criteria
- AT-006, AT-007 pass;
- evaluation fixtures створені.

> Phase 4 remains PARTIALLY COMPLETE until AT-006 and AT-007 have accepted PASS evidence. The exit criteria are not weakened. Formal verification requires a bounded verification package (SD-2), separate from WP-ARCH-01. WP-REC-05 (Phase 4 completion) is positioned after WP-REC-03C–03G and before Phase 6 (SD-4).

## Phase 5 — Controlled AI workflow

**Status:** COMPLETE / ACCEPTED — Phase 5 implementation packages WP-REC-03A through WP-REC-03G are all merged (PRs #63, #65, #72, #73, #74, #78, #80); formal Phase 5 acceptance declared by the Product Owner on 2026-08-14 (DEC-043). AT-008 and AT-013 are PASS, evidenced by accepted formal run `wp-rec-03h-phase-c-20260813-02` (see `docs/reviews/wp_rec_03h_phase_d_product_owner_acceptance_declaration.md`).

### Deliverables
- provider adapter;
- versioned prompt;
- structured output;
- workflow trace;
- error handling;
- model outage behavior.

### Exit criteria
- AT-008, AT-013 pass ✅ — AT-008 PASS, AT-013 PASS (accepted evidence run `wp-rec-03h-phase-c-20260813-02`, Product Owner acceptance date 2026-08-14);
- model response validated;
- deterministic numbers preserved.

## Phase 6 — Approval and audit

**Status:** CLOSED / ACCEPTED — Phase 6 implementation packages WP-REC-04B, WP-REC-04A, WP-REC-04C, WP-REC-04D, and WP-REC-04E are all incorporated into main (PRs #99, #102, #104, #106, #108); formal Phase 6 acceptance declared by the Product Owner on 2026-08-16 (DEC-053). AT-009, AT-010, AT-011, and AT-012 are PASS, evidenced by accepted formal run `wp-rec-04-vfy-20260816-03` (see `docs/reviews/wp_rec_04_phase_6_product_owner_acceptance.md`).

### Deliverables
- approval center;
- approve/reject;
- procurement task creation;
- immutable-style audit trail.

### Exit criteria
- AT-009…AT-012 pass ✅ — AT-009 PASS, AT-010 PASS, AT-011 PASS, AT-012 PASS (accepted evidence run `wp-rec-04-vfy-20260816-03`, Product Owner acceptance date 2026-08-16);

## Phase 7 — Public deployment

### Status
OPEN / IN PROGRESS — WP-P7-01 (deployment contract, DEC-054) is COMPLETE (incorporated via PR #111); WP-P7-02 (deployment/security configuration + Golden RAG / production seed remediation + live embedding gate) is COMPLETE / ACCEPTED (PR #113 + PR #114 merged and post-merge verified; live embedding smoke -03 PASSED; independent evidence review PASSED; Product Owner acceptance 2026-08-18, DEC-055); WP-P7-03 (demo reset) is the next implementation package (NOT IMPLEMENTED). Deployment execution, staging, and production remain NOT STARTED. Release 1 remains NOT READY / NOT DEPLOYED.

### Deliverables
- VPS deployment;
- domain/subdomain;
- HTTPS;
- backups;
- log rotation;
- rate limiting;
- demo reset;
- operational runbooks.

### Exit criteria
- AT-001, AT-002, AT-014, AT-015 pass on public environment.

### Authoritative contract
The Release 1 / Phase 7 deployment contract and controlled decomposition are defined in `docs/planning/phase_7_deployment_contract.md` (WP-P7-01, DEC-054). The contract records Product Owner deployment decisions PD-1 through PD-12, a dependency-ordered work-package decomposition (WP-P7-01 through WP-P7-12), staging/production/release gates, a VPS security-hardening contract, and a Hostinger and domain input contract. No deployment-gated acceptance test is marked PASS until deployment evidence exists.

## Phase 8 — Portfolio release

### Deliverables
- final README;
- architecture diagram;
- screenshots;
- 3–5 minute video;
- CV description;
- external user smoke test;
- release evidence pack.

### Exit criteria
- усі gates у Definition of Done виконано;
- 24 години без P1/P2;
- project status changed to `PORTFOLIO_READY`.

## UX product direction — Ukrainian-first, first-time experience, mobile-first, traceability (DEC-059)

**Status:** DIRECTION ACCEPTED — WP-UX-UA-01 (localization foundation, authenticated application shell, responsive/mobile shell, active-locale date formatting) is COMPLETE / INCORPORATED through PR #128 (regular merge commit `0f819a879d51e5f9f7d3c233a821d1fdb55a51be`, 2026-08-25), independently re-verified before merge; WP-UX-UA-02 (visual design system) is COMPLETE / INCORPORATED through PR #130 (regular merge commit `1a4ec61c05076101b7e6db64b65acaad5bcc831c`, 2026-08-25), independently re-verified before merge; WP-UX-UA-03 (broad Ukrainian migration of the complete user-facing application interface; Ukrainian default locale, English secondary) is COMPLETE / INCORPORATED through PR #132 (regular merge commit `ce6b388ef66feaf0105a0a38ebabe3bb7788b267`, 2026-08-25), independently re-verified before merge; localized catalogs, formatters, backend-error mapping and the hardcoded-visible-English gate delivered; stable machine codes and values unchanged; E2E login behavior aligned with the Ukrainian default; WP-UX-UA-04 (unified localized status and severity registry) is IMPLEMENTED ON BRANCH `feat/wp-ux-ua-04-localized-status-registry` / PENDING REVIEW / NOT MERGED; WP-UX-UA-05 (guided approval flow and end-to-end decision trail) is IMPLEMENTED ON BRANCH `feat/wp-ux-ua-05-guided-approval-trail` / PENDING REVIEW / NOT MERGED; the remaining WP-UX-UA packages are NOT STARTED. The Product Owner accepted the Ukrainian-first, first-time user experience, mobile-first and traceability direction on 2026-08-24 (DEC-059). It supersedes ONLY the English-first ordering of DEC-054; all Phase 7 deployment-security and lifecycle gates remain intact. Release 1 remains NOT READY / NOT DEPLOYED.

**Authoritative planning documents:** `docs/planning/wp_ux_ua_00_product_direction.md` (decisions U1–U6, first-time user experience contract, visual direction, mobile-first contract, bounded decomposition WP-UX-UA-01 through WP-UX-UA-12) and DEC-059 in `forgemind_project_source_of_truth/08_DECISION_LOG.md`.

**Evidence base:** WP-UX-UA-TRACE-01 reconnaissance report `/tmp/wp-ux-ua-trace-01-reconnaissance-report.md` (SHA-256 `ff263e28146ea13b9315ede51160bacb01e99ccf54f9c028e9319fc72047c80c`, read-only against main @ `7e80e0f3ccb98dcf5685509b6847bc9c193fd599`).

**Bounded work-package order (each separately authorized; no combined UX mega-PR):**

1. WP-UX-UA-01 — localization foundation + small authenticated application-shell and first-time guidance pilot + responsive shell evidence;
2. WP-UX-UA-02 — visual design-system foundation (separate from broad translation migration);
3. WP-UX-UA-03 — broad Ukrainian migration of the complete user-facing application interface (translation catalog);
4. WP-UX-UA-04 — localized statuses and explanations (parallel with 05 after 03);
5. WP-UX-UA-05 — navigation, onboarding completion, entity cross-links;
6. WP-UX-UA-06 — audit/status-transition backend contract + migration (U2; backend track);
7. WP-UX-UA-07 — Trace API read-only projection (U3; no migration; backend track);
8. WP-UX-UA-08 — Trace Map frontend (after 07 + 03/04; linear trace default on mobile);
9. WP-UX-UA-09 — provider-output language package (U5; own verification);
10. WP-UX-UA-10 — source identity schema + migration (U4; backend track);
11. WP-UX-UA-11 — accessibility/responsive consolidation audit (gate, not first mobile work);
12. WP-UX-UA-12 — demo verification on the isolated disposable Demo stack.

**Cross-cutting rules:** responsive/mobile acceptance criteria are required in EVERY frontend package; backend migrations are separated from frontend presentation; Document Trace stays projection-first until U2/U4 packages merge; the Audit Log remains the canonical transition source (no second persistent timeline); stable machine contracts (API enums, DB values, event codes, persisted identifiers) are never localized.

**Exit criteria**
- Every WP-UX-UA package separately planned, authorized, implemented, verified and merged before being marked complete.
- First-time-user comprehension verified on the demo (WP-UX-UA-12 evidence).
- Mobile acceptance evidence exists for every materially changed route.
- No localization change alters any API enum, DB value, event code, or persisted identifier.

## Post-MVP

Лише після Portfolio Ready:

1. Requirements Analyst;
2. Incident Triage;
3. Process Mapping;
4. Evaluation Lab;
5. n8n integration;
6. local GPU showcase;
7. additional workflows.

## Основний принцип

Не переходити до наступної фази, якщо exit criteria попередньої не мають evidence.
