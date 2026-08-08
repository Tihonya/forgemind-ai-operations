# ForgeMind AI Operations

Supply Risk Intelligence — a portfolio-grade industrial AI demonstration.

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
- **RAG-powered document intelligence** for evidence retrieval (implementation complete; integration test AT-006 requires live database and was not executed in this review environment)

**Release 1 targets (not yet implemented):**
- **Structured AI recommendations** with human-in-the-loop approval
- **Complete audit traceability** for every workflow step

Release 1 is a **public portfolio MVP** demonstrating one complete vertical scenario: **Production Plan Supply Risk Review**.

## Overview

**Release 1 target scenario (not yet fully implemented):**

A Production Manager logs in, views an active production plan, runs supply risk analysis, receives AI-explained recommendations with document citations, approves a procurement action, and reviews the complete audit trail — all with synthetic data only.

**Currently working:**
- Login and authentication (AT-002)
- Dashboard with synthetic production plan
- Supply risk list and detail views
- Deterministic risk calculation (AT-003, AT-004 verified)
- RAG document retrieval infrastructure (AT-006 test exists but not executed in this review)

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

1. Synthetic production plan → deterministic risk calculation ✅ IMPLEMENTED (AT-003, AT-004 verified)
2. RAG over synthetic engineering documents → cited retrieval ⚠️ IMPLEMENTATION COMPLETE (AT-006 test exists but requires live database; not executed in this review)
3. Structured AI recommendation → human approval ❌ NOT IMPLEMENTED
4. Controlled procurement task creation → complete audit trace ❌ NOT IMPLEMENTED
5. Public HTTPS deployment → demo reset ❌ NOT IMPLEMENTED

**Current implementation status:** Step 1 is verified by passing integration tests. Step 2 has implementation code and an integration test file, but the test requires a live PostgreSQL database and was not executed in this review environment. Steps 3–5 (AI recommendation, approval, procurement, audit, public deployment) are not implemented.

**Canonical Golden Scenario:** The full 13-step Golden Scenario is defined in `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md` §2. The 5 condensed milestones above map to subsets of the canonical steps.

See [docs/next_steps.md](docs/next_steps.md) for the full status and blockers.

## Documentation

- [Source of Truth](forgemind_project_source_of_truth/)
- [Phase 0 Bootstrap Plan](docs/planning/phase_0_bootstrap_plan.md)
- [Requirements Traceability](docs/planning/requirements_traceability_matrix.md)
- [Open Questions](docs/planning/open_questions.md)

## Technology Stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| AI/ML | ARQ + Redis (AI provider adapter: planned for Phase 5, not yet implemented) |
| Frontend | React 18, TypeScript, Vite, Tailwind, shadcn/ui |
| Database | PostgreSQL + pgvector |
| Infra | Docker Compose, Caddy, GitHub Actions |
| Testing | pytest, Vitest, Playwright |

## License

Proprietary — ForgeMind AI Operations
