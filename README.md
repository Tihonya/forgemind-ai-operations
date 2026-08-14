# ForgeMind AI Operations

Controlled AI-assisted Supply Risk Intelligence portfolio MVP demonstrating one complete, auditable, human-approved vertical workflow.

## Live Demo

**Status:** IN DEVELOPMENT — Not yet deployed

**Live Demo:** TBD — not yet deployed. Will be published once Phase 7 (VPS deployment) is complete.

**Source Code:** https://github.com/Tihonya/forgemind-ai-operations

**Current Status:** Development in progress. See [docs/next_steps.md](docs/next_steps.md) for current implementation status and blockers.

## Release 1 Deliverables

Release 1 must provide:
- **Live Demo:** Public HTTPS deployment on Product Owner's VPS
- **Public GitHub repository:** This repository with complete documentation
- **Synthetic data only:** All data and documents are synthetic (invented for the project). No real corporate, military, or confidential systems.
- **Real end-to-end workflows:** No static mockups — workflows exercise the real application stack against synthetic data.
- **Persisted and observable state:** Database, audit logs, state transitions
- **Recruiter-friendly README:** Clear value proposition, architecture, setup instructions
- **Verified technology stack:** All listed technologies actually used in the released application

**Success criteria:** A recruiter can view the Live Demo, understand the value proposition within 3-5 minutes, inspect the GitHub repository, and verify the technology stack matches the implementation.

## What is ForgeMind?

ForgeMind is a web platform for AI-assisted supply chain risk assessment in engineering and manufacturing environments.

**Currently implemented:**
- **Deterministic business logic** (Python/SQL) for risk calculation
- **RAG-powered document intelligence** for evidence retrieval (implementation complete; AT-006 requires formal verification against a live database)
- **AI provider adapter** — OpenAI-compatible ChatProvider (WP-REC-03A, merged)
- **Workflow state machine + engine** — explicit state machine with 7 states and immutable transitions (WP-REC-03B, merged)
- **Controlled AI workflow** (Phase 5) — structured recommendation generation with validation, workflow trace, and user-initiated retry, implemented and formally accepted (AT-008 PASS, AT-013 PASS; accepted evidence run `wp-rec-03h-phase-c-20260813-02`)

**Release 1 targets (not yet implemented):**
- **Human-in-the-loop approval** for AI recommendations (Phase 6)
- **Controlled procurement writes** with approval (Phase 6)
- **Complete audit traceability** for every workflow step (Phase 6)
- **Public HTTPS deployment** with demo reset (Phase 7)

Release 1 is a **public portfolio MVP** demonstrating one complete vertical scenario: **Production Plan Supply Risk Review**.

## Overview

**Release 1 target scenario (not yet fully implemented):**

A Production Manager logs in, views an active production plan, runs supply risk analysis, receives AI-explained recommendations with document citations, approves a procurement action, and reviews the complete audit trail — all with synthetic data only.

**Currently working (demonstrable):**
- Login and authentication
- Dashboard with synthetic production plan
- Supply risk list and detail views
- Deterministic risk calculation (AT-003, AT-004, AT-005 verified)
- RAG document retrieval infrastructure (AT-006 test exists but requires formal verification)
- Structured AI recommendation workflow with validation and user-initiated retry (Phase 5, formally accepted — AT-008 PASS, AT-013 PASS)

**Not yet working (Release 1 targets):**
- Human approval workflow (Phase 6)
- Controlled procurement writes (Phase 6)
- Audit trace (Phase 6)
- Public HTTPS deployment (Phase 7)

The full 13-step Golden Scenario (defined in `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md` §2) is not yet complete. The current demonstrable journey covers steps 1–4 (deterministic core) plus partial step 8 (deterministic risk display).

**Target audience:** Recruiters and technical reviewers evaluating AI-assisted industrial workflow capabilities.

**Reviewer journey:** CV → Live Demo → complete working scenario (3–5 minutes) → inspect results and state transitions → open GitHub → understand architecture, implementation, tests, deployment, and limitations.

**Data policy:** Synthetic data only. No real corporate, military, or confidential systems.

## Quick Start

```bash
# Clone and configure
git clone <repo-url> && cd forgemind-ai-operations
cp .env.example .env
# Edit .env with your settings (or keep defaults for local dev)

# Start all services
docker compose up -d

# Access the application
# Frontend:  http://localhost:5173
# Backend:   http://localhost:8000
# API docs:  http://localhost:8000/docs
# Caddy:     http://localhost
```

## Developer Setup

```bash
# Create root virtual environment (one venv for the whole project)
python3.12 -m venv .venv && source .venv/bin/activate

# Install backend dependencies from the root venv
cd backend && pip install -e ".[dev]" && cd ..

# Frontend
cd frontend && npm install && npm run dev && cd ..

# Run tests (uses root .venv for backend)
make test

# Seed demo data (implemented — generates synthetic golden dataset)
make seed

# Reset demo data (placeholder — reset_service.py not yet implemented; see Phase 7 blockers)
make reset
```

## Configuration

Chat-provider selection is independent of embedding-provider selection. The
chat provider is configured via `CHAT_PROVIDER_MODE`:

| `CHAT_PROVIDER_MODE` | Behaviour |
|---|---|
| `fake` | Deterministic offline provider. Default for development/CI. Requires no key. Rejected outside development. |
| `openai` | OpenAI (requires `OPENAI_API_KEY`). |
| `chain` | Ordered external fallback chain, server-configured via `CHAT_PROVIDER_CHAIN` (default `groq,openrouter`). |

### External fallback chain

The chain advances from Groq (free primary) to OpenRouter (paid fallback)
only after the current provider's bounded retry budget is exhausted with a
**transient** failure (connection failure, timeout, HTTP 429, retryable 5xx).
Permanent errors — including OpenRouter HTTP 402 (external budget/credit
exhaustion), authentication failures, schema-invalid and citation-invalid
responses — never fall back. Total provider calls are bounded by
`provider_count × attempts_per_provider`.

| Variable | Meaning |
|---|---|
| `GROQ_API_KEY` | Groq API key (required when Groq is in use). |
| `GROQ_API_BASE` | Default `https://api.groq.com/openai/v1`. |
| `GROQ_CHAT_MODEL` | Pinned free model, default `openai/gpt-oss-120b`. |
| `OPENROUTER_API_KEY` | OpenRouter API key (required when OpenRouter is in use). |
| `OPENROUTER_API_BASE` | Default `https://openrouter.ai/api/v1`. |
| `OPENROUTER_CHAT_MODEL` | **Required explicit pinned paid model — no default is ever guessed.** |

The ~USD 5 OpenRouter budget is an **external** OpenRouter account/key
control configured separately by the Product Owner. The application does not
enforce it; on exhaustion OpenRouter returns HTTP 402, which the application
treats as a permanent failure (no retry, no fallback).

### Structured output modes

Each provider carries an explicit structured-output capability mode
(`*_STRUCTURED_OUTPUT_MODE`): `json_schema` (strict JSON Schema response
format), `json_object` (provider JSON-object mode), or `prompt_json`
(explicit prompt-only compatibility mode). Server-side Pydantic validation
remains authoritative in every mode. An unsupported mode fails safely at
startup; it is never silently downgraded after a provider error.

API keys are never logged, printed, serialized, or committed.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ Caddy (reverse proxy, HTTPS)                        │
├──────────────┬──────────────────────────────────────┤
│ Frontend     │ Backend (FastAPI)                    │
│ React 18 +   │ ┌─────────┬──────────┬───────────┐  │
│ TypeScript   │ │ REST API│ AI/LLM   │ ARQ Worker│  │
│              │ │         │ Service  │           │  │
│              │ └────┬────┴────┬─────┴─────┬─────┘  │
│              │      │         │           │        │
│              │   ┌──┴─────────┴───────────┴──┐     │
│              │   │ PostgreSQL + pgvector      │     │
│              │   └────────────────────────────┘     │
│              │   ┌──────────┐                       │
│              │   │ Redis    │ (ARQ + cache)         │
│              │   └──────────┘                       │
└──────────────┴──────────────────────────────────────┘
```

## MVP Vertical: Supply Risk Intelligence

Release 1 implements one complete vertical scenario:

**Production Plan Supply Risk Review (5 condensed milestones)**

1. Synthetic production plan → deterministic risk calculation ✅ IMPLEMENTED (AT-003, AT-004, AT-005 verified)
2. RAG over synthetic engineering documents → cited retrieval ⚠️ IMPLEMENTATION COMPLETE (AT-006 test exists; requires formal verification)
3. Structured AI recommendation ✅ IMPLEMENTED & ACCEPTED (Phase 5: WP-REC-03A–03G; AT-008 PASS, AT-013 PASS) → human approval ❌ NOT IMPLEMENTED (Phase 6)
4. Controlled procurement task creation → complete audit trace ❌ NOT IMPLEMENTED (Phase 6)
5. Public HTTPS deployment → demo reset ❌ NOT IMPLEMENTED (Phase 7)

**Current implementation status:** steps 1 and 2 are implemented; step 3's structured AI recommendation is implemented and accepted, while its transition to human approval is not implemented; step 4 (controlled procurement task creation and complete audit trace) and step 5 (public HTTPS deployment and demo reset) are not implemented.

**Canonical Golden Scenario:** The full 13-step Golden Scenario is defined in `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md` §2. The 5 condensed milestones above map to subsets of the canonical steps.

See [docs/next_steps.md](docs/next_steps.md) for the full status and blockers.

## Documentation

- [Source of Truth](forgemind_project_source_of_truth/)
- [Product Strategy (WP-STRAT-01)](docs/planning/wp_strat_01_product_strategy.md)
- [Requirements Traceability](docs/planning/requirements_traceability_matrix.md)
- [Open Questions](docs/planning/open_questions.md)

## Technology Stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| AI/ML | ARQ + Redis, OpenAI-compatible ChatProvider adapter with server-configured Groq → OpenRouter fallback chain (offline-verified; no live provider call) |
| Frontend | React 18, TypeScript, Vite, Tailwind, shadcn/ui |
| Database | PostgreSQL + pgvector |
| Infra | Docker Compose, Caddy, GitHub Actions |
| Testing | pytest, Vitest, Playwright |

## License

Proprietary — ForgeMind AI Operations
