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
