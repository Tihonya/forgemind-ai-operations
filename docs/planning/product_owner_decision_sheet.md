# Product Owner Decision Sheet

Generated from `docs/planning/open_questions.md`.

Each decision includes: ID, title, options, recommendation, rationale,
consequence of postponing, and whether it blocks Phase 0.

---

## MUST DECIDE BEFORE PHASE 0 — APPROVED

All three blocking decisions have been approved by Product Owner (2026-07-15).

---

### DEC-010 — Python Version Pin — APPROVED

**Options:**
- (A) 3.12 — max library compatibility, conservative ✓ APPROVED
- (B) 3.13 — stable, modern
- (C) 3.14 — current environment, newest features

**Decision:** A (Python 3.12)

**Rationale:** Broadest library support, matches SoT minimum requirement.

**Status:** APPROVED — recorded in 08_DECISION_LOG.md

---

### DEC-011 — Background Job Library — APPROVED

**Options:**
- (A) ARQ + Redis — lightweight, async-native, simple ✓ APPROVED
- (B) Dramatiq + Redis — more features, slightly heavier
- (C) Celery + Redis — enterprise-grade, heaviest
- (D) No background jobs — FastAPI BackgroundTasks only, no Redis

**Decision:** A (ARQ + Redis)

**Rationale:** Lightest option with real queue semantics; sufficient for MVP
document indexing and async AI runs.

**Status:** APPROVED — recorded in 08_DECISION_LOG.md

---

### DEC-014 — Reverse Proxy — APPROVED

**Options:**
- (A) Caddy — auto-HTTPS, minimal config ✓ APPROVED
- (B) Nginx — more control, requires certbot

**Decision:** A (Caddy)

**Rationale:** Auto-provisions HTTPS with zero config, ideal for MVP.

**Status:** APPROVED — recorded in 08_DECISION_LOG.md

---

## CAN USE RECOMMENDED DEFAULT

These decisions affect Phase 0 structure but can proceed with recommended
defaults. PO can override later without major rework.

---

### DEC-015 — State Management

**Options:**
- (A) Zustand — minimal, specified in SoT
- (B) Jotai — atomic, minimal
- (C) React Context only — no extra dependency

**Recommendation:** A (Zustand)

**Rationale:** Explicitly named in SoT, minimal footprint, easy to remove if
unused.

**Consequence of postponing:** frontend/package.json missing Zustand dep.
Can add later with one-line change.

**Blocks Phase 0:** NO — can use default A.

---

### DEC-016 — Charts Library

**Options:**
- (A) Recharts — React-native, simpler API
- (B) ECharts — more powerful, larger bundle

**Recommendation:** A (Recharts)

**Rationale:** Sufficient for dashboard KPIs; smaller bundle.

**Consequence of postponing:** frontend/package.json missing chart library.
Can add in Phase 3 when dashboard is built.

**Blocks Phase 0:** NO — can use default A.

---

### DEC-017 — Component Library

**Options:**
- (A) shadcn/ui + Tailwind CSS — copy-paste, full control
- (B) MUI — comprehensive, opinionated
- (C) Ant Design — enterprise-oriented
- (D) Radix UI + custom styling

**Recommendation:** A (shadcn/ui + Tailwind)

**Rationale:** Accessible, no lock-in, pairs naturally with Tailwind.

**Consequence of postponing:** frontend/package.json missing UI deps.
Can add in Phase 3; may require restyling if changed later.

**Blocks Phase 0:** NO — can use default A.

---

### DEC-018 — Redis in MVP

**Options:**
- (A) Yes — required for ARQ queue (if DEC-011 = A)
- (B) No — use BackgroundTasks, no Redis

**Recommendation:** A (Yes, for ARQ)

**Rationale:** Real queue provides retry, persistence, observability.

**Consequence of postponing:** Depends on DEC-011. If ARQ chosen, Redis is
mandatory. Cannot be deferred if DEC-011 = A.

**Blocks Phase 0:** NO — derived from DEC-011.

---

### DEC-019 — Reranker in MVP

**Options:**
- (A) No — pgvector similarity only
- (B) Yes — cross-encoder reranker

**Recommendation:** A (No)

**Rationale:** Keep scope minimal; Post-MVP optimization.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 4 RAG
quality, not structure.

**Blocks Phase 0:** NO — can use default A.

---

### DEC-020 — Object Storage in MVP

**Options:**
- (A) No — store documents in PostgreSQL
- (B) Yes — MinIO or S3

**Recommendation:** A (No)

**Rationale:** Synthetic documents are small; PostgreSQL text/jsonb sufficient.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 4 document
ingestion if changed later (migration required).

**Blocks Phase 0:** NO — can use default A.

---

### DEC-021 — React Flow for Workflow Trace

**Options:**
- (A) No — vertical step/timeline component
- (B) Yes — visual DAG

**Recommendation:** A (No)

**Rationale:** Workflow steps are sequential; timeline is simpler.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 3/5
frontend complexity.

**Blocks Phase 0:** NO — can use default A.

---

### DEC-023 — Rate Limit Values

**Options:**
- (A) 60 req/min API, 10 AI calls/min per user
- (B) 30 req/min API, 5 AI calls/min per user
- (C) Define during Phase 7 deployment

**Recommendation:** A (60/10)

**Rationale:** Reasonable defaults for public demo with synthetic data.

**Consequence of postponing:** No impact on Phase 0. Caddy config can be
updated in Phase 7.

**Blocks Phase 0:** NO — can use default A.

---

### DEC-024 — Correlation ID Format

**Options:**
- (A) UUID v4
- (B) ULID (sortable)
- (C) Sequential integer + prefix

**Recommendation:** A (UUID v4)

**Rationale:** Standard, collision-free, no coordination needed.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 5 workflow
trace schema.

**Blocks Phase 0:** NO — can use default A.

---

### DEC-025 — Risk Engine ↔ AI Output Contract

**Options:**
- (A) Two-phase: engine → deterministic struct; LLM → summary/actions
- (B) Single-phase: engine outputs everything
- (C) Single-phase: LLM outputs everything

**Recommendation:** A (Two-phase)

**Rationale:** Matches architectural principle that LLM doesn't do arithmetic.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 5
schemas/ai_output.py design.

**Blocks Phase 0:** NO — can use default A.

---

### DEC-026 — Document Permission Model

**Options:**
- (A) Role-based (each role has access levels)
- (B) User-based (per-user grants)
- (C) Hybrid (role default + per-user override)

**Recommendation:** A (Role-based)

**Rationale:** Simpler, matches RBAC model; sufficient for MVP.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 4 RAG
retriever filtering.

**Blocks Phase 0:** NO — can use default A.

---

## CAN BE DEFERRED UNTIL LATER PHASES

These decisions do not affect Phase 0 artifacts. Can be decided when the
relevant phase begins.

---

### DEC-009 — Engineer RBAC Role

**Options:**
- (A) 5th distinct role + engineer.demo account
- (B) Engineer views via Production Manager role
- (C) Engineer as sub-role of AI Administrator

**Recommendation:** A (5th distinct role)

**Rationale:** Engineer has distinct behavior (views technical docs).

**Consequence of postponing:** No impact on Phase 0. Affects Phase 1 auth
service and seed data (Phase 2).

**Blocks Phase 0:** NO — defer to Phase 1.

---

### DEC-012 — Real-Time Updates

**Options:**
- (A) Polling (3-5s interval)
- (B) Server-Sent Events (SSE)
- (C) WebSocket

**Recommendation:** A (Polling)

**Rationale:** Simplest; upgrade path to SSE exists if needed.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 3 frontend
architecture when workflow trace UI is built.

**Blocks Phase 0:** NO — defer to Phase 3.

---

### DEC-013 — Workflow Orchestration

**Options:**
- (A) Custom explicit state machine
- (B) LangGraph

**Recommendation:** A (Custom state machine)

**Rationale:** No extra dependency, fully debuggable, matches SoT preference.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 5
backend/ai/workflow/ architecture.

**Blocks Phase 0:** NO — defer to Phase 5.

---

### DEC-022 — Demo Reset Mechanism

**Options:**
- (A) Drop user-generated tables + re-seed from fixture
- (B) Soft-delete user data + restore seed
- (C) Transaction rollback to pre-seed savepoint

**Recommendation:** A (Drop + re-seed)

**Rationale:** Simplest, most reliable; matches seed command pattern.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 6/7
reset_service and operational procedures.

**Blocks Phase 0:** NO — defer to Phase 6.

---

### DEC-027 — Reset Role

**Options:**
- (A) AI Administrator only
- (B) Production Manager + AI Administrator
- (C) Separate superadmin role

**Recommendation:** A (AI Administrator only)

**Rationale:** Matches FR-12; keeps permissions simple.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 6 RBAC
middleware for admin endpoints.

**Blocks Phase 0:** NO — defer to Phase 6.

---

### DEC-028 — Demo Account ↔ Role Mapping

**Options:**
- (A) 5 demo accounts (all roles)
- (B) 3 accounts; Engineer shares Production Manager access
- (C) 3 accounts; Engineer and Admin out of scope for public demo

**Recommendation:** A (5 accounts)

**Rationale:** Full coverage for all roles in public demo.

**Consequence of postponing:** No impact on Phase 0. Affects Phase 2 seed
data generation.

**Blocks Phase 0:** NO — defer to Phase 2.

---

## Summary

**Must decide before Phase 0 — ALL APPROVED (3 decisions):**
- DEC-010: Python version ✓
- DEC-011: Background job library ✓
- DEC-014: Reverse proxy ✓

**Can use recommended default (11 decisions):**
- DEC-015 through DEC-026 (excluding DEC-022, DEC-023, DEC-024, DEC-025, DEC-026)

**Can be deferred until later phases (6 decisions):**
- DEC-009, DEC-012, DEC-013, DEC-022, DEC-027, DEC-028

Total: 20 decisions.

**Phase 0 status:** UNBLOCKED — all blocking decisions approved.

---

## Approval Instructions

Product Owner must:

1. Review all 20 decisions in this sheet.
2. For the 3 "Must decide before Phase 0" items, explicitly approve or reject
   the recommendation.
3. For the 11 "Can use recommended default" items, either:
   - Accept the default (no action required), OR
   - Override with a different option.
4. For the 6 "Can be deferred" items, either:
   - Accept deferral (no action required), OR
   - Decide now to avoid later rework.

Once approved, update `forgemind_project_source_of_truth/08_DECISION_LOG.md`
with DEC-009 through DEC-028 entries, then authorize Phase 0 implementation.
