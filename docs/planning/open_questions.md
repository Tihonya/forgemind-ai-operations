# Open Questions — Pending Product Owner Approval

All items below require explicit Product Owner decision before implementation begins. Each is numbered for Decision Log entry (DEC-009 onwards).

---

## Resolved Questions (Approved)

### Q-2 — Python Version Pin (DEC-010) — RESOLVED ✓

**Decision:** Option A — Pin to Python 3.12.
**Status:** APPROVED by Product Owner (2026-07-15)
**Recorded in:** 08_DECISION_LOG.md DEC-010
**Validated:** Phase 1 implementation uses Python 3.12 successfully (239 tests passing).

---

### Q-3 — Background Job Library (DEC-011) — RESOLVED ✓

**Decision:** Option A — ARQ + Redis.
**Status:** APPROVED by Product Owner (2026-07-15)
**Recorded in:** 08_DECISION_LOG.md DEC-011
**Validated:** Phase 1 diagnostic-job pipeline uses ARQ + Redis end-to-end (live smoke verified).

---

### Q-6 — Reverse Proxy (DEC-014) — DEFERRED ✓

**Decision:** Option A — Caddy.
**Status:** APPROVED by Product Owner (2026-07-15)
**Recorded in:** 08_DECISION_LOG.md DEC-014
**Implementation Status:** Deferred to Phase 2 (frontend scope deferred from Phase 1). Decision remains valid; Caddy configuration will be added when Phase 2 front-end work begins.

---

## Unresolved Questions

### Q-1 — Engineer RBAC Role (DEC-009)

**Context:** `01_PRODUCT_AND_MVP_SCOPE.md` §5 lists five target users (Production Manager, Procurement Specialist, Engineer, AI Administrator, Auditor), but FR-01 lists only four demo roles (no Engineer). Gate D says "at least four roles".

**Options:**
- (A) Engineer is a 5th distinct RBAC role with `engineer.demo` account.
- (B) Engineer views are accessible via Production Manager role (no separate role).
- (C) Engineer is a sub-role of AI Administrator.

**Recommendation:** Option A — Engineer has distinct behavior (views technical docs and alternatives) and warrants a separate role.

**Blocks Phase 0:** NO — defer to Phase 1.

---

### Q-4 — Real-Time Updates (DEC-012)

**Context:** `02` §2 says "WebSocket або polling — обрати найпростішу надійну реалізацію".

**Options:**
- (A) Polling (3-5s interval) — simplest.
- (B) Server-Sent Events (SSE) — one-directional, moderate complexity.
- (C) WebSocket — bidirectional, most complex.

**Recommendation:** Option A — polling is explicitly suggested as acceptable by the SoT. Upgrade path to SSE exists if needed later.

**Blocks Phase 0:** NO — defer to Phase 3.

---

### Q-5 — Workflow Orchestration (DEC-013)

**Context:** `02` §2 says "LangGraph або власна explicit state machine".

**Options:**
- (A) Custom explicit state machine — no extra dependency, fully debuggable.
- (B) LangGraph — framework-backed, more abstraction.

**Recommendation:** Option A — matches SoT preference for "явну" state machine. No external framework dependency.

**Blocks Phase 0:** NO — defer to Phase 5.

---

### Q-7 — State Management (DEC-015)

**Context:** `02` §2 says "Zustand або мінімальний state layer".

**Options:**
- (A) Zustand — minimal, specified in SoT.
- (B) Jotai — atomic, minimal.
- (C) React Context only — no extra dependency.

**Recommendation:** Option A — Zustand is explicitly named in SoT and is minimal.

---

### Q-8 — Charts Library (DEC-016)

**Context:** `02` §2 says "ECharts або Recharts".

**Options:**
- (A) Recharts — React-native, simpler API.
- (B) ECharts — more powerful, larger bundle.

**Recommendation:** Option A — Recharts is sufficient for dashboard KPIs and risk severity distribution.

---

### Q-9 — Component Library (DEC-017)

**Context:** `02` §2 says "component library із послідовною design system" but names no specific library.

**Options:**
- (A) shadcn/ui + Tailwind CSS — copy-paste components, full control.
- (B) MUI (Material UI) — comprehensive, opinionated.
- (C) Ant Design — enterprise-oriented.
- (D) Radix UI primitives + custom styling.

**Recommendation:** Option A — shadcn/ui provides accessible components without lock-in, pairs naturally with Tailwind.

---

### Q-10 — Redis in MVP (DEC-018)

**Context:** `02` §2 says "Redis лише за наявності реальної потреби".

**Dependency:** If ARQ (Q-3) is chosen, Redis is required for the job queue.

**Options:**
- (A) Yes — Redis required for ARQ queue.
- (B) No — use FastAPI BackgroundTasks, no Redis needed.

**Recommendation:** Option A — real queue provides retry, persistence, and observability that BackgroundTasks lacks.

---

### Q-11 — Reranker in MVP (DEC-019)

**Context:** `02` §2 says "optional reranker".

**Options:**
- (A) No reranker — pgvector similarity only.
- (B) Yes — add cross-encoder reranker for better retrieval quality.

**Recommendation:** Option A — keep scope minimal. Reranker is a Post-MVP optimization.

---

### Q-12 — Object Storage in MVP (DEC-020)

**Context:** `02` §2 says "object storage опціонально".

**Options:**
- (A) No — store document text and chunks in PostgreSQL.
- (B) Yes — MinIO or S3 for document files.

**Recommendation:** Option A — synthetic documents are small; PostgreSQL text/jsonb is sufficient.

---

### Q-13 — React Flow for Workflow Trace (DEC-021)

**Context:** `02` §2 says "React Flow лише для workflow trace, якщо виправдано".

**Options:**
- (A) No React Flow — use a vertical step/timeline component.
- (B) Yes React Flow — visual DAG of workflow steps.

**Recommendation:** Option A — workflow steps are sequential, not a complex DAG. Timeline is simpler and sufficient.

---

### Q-14 — Demo Reset Mechanism (DEC-022)

**Context:** FR-12 says admin can reset. AT-015 says "created demo actions cleared, seed dataset restored, audit reset event recorded."

**Options:**
- (A) Drop all user-generated tables + re-seed from fixture.
- (B) Soft-delete user data + restore seed.
- (C) Transaction rollback to pre-seed savepoint.

**Recommendation:** Option A — simplest, most reliable. Matches "seed command creates Golden Dataset" pattern.

---

### Q-15 — Reset Role (DEC-023)

**Context:** FR-12 says "Адміністратор". `05` §5 says "Адміністративний reset не повинен бути доступним анонімному користувачеві."

**Options:**
- (A) AI Administrator only.
- (B) Production Manager + AI Administrator.
- (C) Separate superadmin role (outside MVP RBAC).

**Recommendation:** Option A — matches FR-12 and keeps permissions simple.

---

### Q-16 — Demo Account ↔ Role Mapping (DEC-024)

**Context:** `05` §5 lists three demo accounts (manager.demo, procurement.demo, auditor.demo) but the SoT defines 5 roles.

**Options:**
- (A) Create 5 demo accounts (add engineer.demo, admin.demo).
- (B) Keep 3 accounts; Engineer shares Production Manager access; AI Administrator uses a different login flow.
- (C) Keep 3 accounts; Engineer and Admin are out of scope for public demo.

**Recommendation:** Option A — full coverage for all roles in public demo.

---

### Q-17 — Rate Limit Values

**Context:** Gate D and `05` §6 mention rate limiting but specify no numbers.

**Options:**
- (A) 60 req/min per user for API, 10 AI calls/min per user.
- (B) 30 req/min per user for API, 5 AI calls/min per user.
- (C) Define during Phase 7 deployment configuration.

**Recommendation:** Option A — reasonable defaults for a public demo with synthetic data.

---

### Q-18 — Correlation ID Format

**Context:** FR-07 / AT-012 require correlation IDs.

**Options:**
- (A) UUID v4.
- (B) ULID (sortable).
- (C) Sequential integer + prefix.

**Recommendation:** Option A — UUID v4 is standard, collision-free, no coordination needed.

---

### Q-19 — Risk Engine ↔ AI Output Contract

**Context:** `02` §6 shows a combined JSON schema. `02` §1 says "LLM не є джерелом істини для арифметики." Need a precise split.

**Options:**
- (A) Two-phase: Engine outputs deterministic risk struct (quantities, severity, affected orders). LLM enriches with summary, business_impact, recommended_actions on top.
- (B) Single-phase: Engine outputs everything including text explanations.
- (C) Single-phase: LLM outputs everything including numbers.

**Recommendation:** Option A — matches the architectural principle that LLM doesn't do arithmetic. Deterministic numbers come from engine; LLM adds human-readable context.

---

### Q-20 — Document Permission Model

**Context:** `02` §3 lists `document_permissions` entity but semantics are undefined.

**Options:**
- (A) Role-based: each role has access to certain document access levels (public, internal, restricted).
- (B) User-based: per-user access grants.
- (C) Hybrid: role default + per-user override.

**Recommendation:** Option A — simpler, matches RBAC model. Sufficient for MVP synthetic data.

---

## Summary: Decisions Needed

| # | Decision | Recommendation | Impact |
|---|----------|---------------|--------|
| DEC-009 | Engineer RBAC role | 5th distinct role | Affects auth, RBAC middleware, demo accounts |
| DEC-010 | Python version | 3.12 | Affects Dockerfile, CI, dependencies |
| DEC-011 | Background jobs | ARQ + Redis | Affects docker-compose, backend deps, worker |
| DEC-012 | Real-time | Polling | Affects frontend architecture |
| DEC-013 | Workflow engine | Custom state machine | Affects backend/ai/workflow/ |
| DEC-014 | Reverse proxy | Caddy | Affects infra/caddy/, docker-compose |
| DEC-015 | State management | Zustand | Affects frontend/src/store/ |
| DEC-016 | Charts | Recharts | Affects frontend deps |
| DEC-017 | Component library | shadcn/ui + Tailwind | Affects frontend styling approach |
| DEC-018 | Redis in MVP | Yes (for ARQ) | Affects docker-compose services |
| DEC-019 | Reranker in MVP | No | Reduces Phase 4 scope |
| DEC-020 | Object storage | No | Documents in PostgreSQL |
| DEC-021 | React Flow | No (use timeline) | Reduces frontend complexity |
| DEC-022 | Demo reset mechanism | Drop + re-seed | Affects reset_service design |
| DEC-023 | Reset role | AI Administrator only | Affects RBAC |
| DEC-024 | Demo accounts | 5 accounts (all roles) | Affects seed data, auth |
| — | Rate limit values | 60 API / 10 AI per min | Affects Caddy/backend config |
| — | Correlation ID | UUID v4 | Affects core/correlation.py |
| — | Engine↔AI contract | Two-phase output | Affects schemas/ai_output.py |
| — | Document permissions | Role-based | Affects RAG retriever filter |

All 20 items above require Product Owner approval before Phase 0 implementation begins.
