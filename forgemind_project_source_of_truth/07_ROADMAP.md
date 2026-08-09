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

### Deliverables
- provider adapter;
- versioned prompt;
- structured output;
- workflow trace;
- error handling;
- model outage behavior.

### Exit criteria
- AT-008, AT-013 pass;
- model response validated;
- deterministic numbers preserved.

## Phase 6 — Approval and audit

### Deliverables
- approval center;
- approve/reject;
- procurement task creation;
- immutable-style audit trail.

### Exit criteria
- AT-009…AT-012 pass.

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
