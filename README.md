# ForgeMind AI Operations

Supply Risk Intelligence — a portfolio-grade industrial AI demonstration.

## Live Demo

**Status:** IN DEVELOPMENT — Not yet deployed

Release 1 will provide:
- **Live Demo:** https://forgemind.example.com (domain TBD)
- **Source Code:** https://github.com/Tihonya/forgemind-ai-operations

**Current Status:** Development in progress. See [docs/next_steps.md](docs/next_steps.md) for current implementation status and blockers.

## Release 1 Deliverables

Release 1 must provide:
- **Live Demo:** Public HTTPS deployment on Product Owner's VPS
- **Public GitHub repository:** This repository with complete documentation
- **Synthetic data only:** No real corporate, military, or confidential systems
- **Real end-to-end workflows:** No static mockups or fake data
- **Persisted and observable state:** Database, audit logs, state transitions
- **Recruiter-friendly README:** Clear value proposition, architecture, setup instructions
- **Verified technology stack:** All listed technologies actually used in the released application

**Success criteria:** A recruiter can view the Live Demo, understand the value proposition within 3-5 minutes, inspect the GitHub repository, and verify the technology stack matches the implementation.

## What is ForgeMind?

ForgeMind is a web platform for AI-assisted supply chain risk assessment in engineering and manufacturing environments. It combines:

- **Deterministic business logic** (Python/SQL) for risk calculation
- **RAG-powered document intelligence** for evidence retrieval
- **Structured AI recommendations** with human-in-the-loop approval
- **Complete audit traceability** for every workflow step

Release 1 is a **public portfolio MVP** demonstrating one complete vertical scenario: **Production Plan Supply Risk Review**.

## Overview

A Production Manager logs in, views an active production plan, runs supply risk analysis, receives AI-explained recommendations with document citations, approves a procurement action, and reviews the complete audit trail — all with synthetic data only.

**Target audience:** Recruiters and technical reviewers evaluating AI-assisted industrial workflow capabilities.

**Reviewer journey:** CV → Live Demo → complete working scenario (3–5 minutes) → inspect results and state transitions → open GitHub → understand architecture, implementation, tests, deployment, and limitations.

**Data policy:** Synthetic data only. No real corporate, military, or confidential systems.

## Quick Start

```bash
# Clone and configure
git clone <repo-url> && cd AIAutomation
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

# Seed demo data (deferred to Phase 2 — Synthetic ERP core)
make seed

# Reset demo data (deferred to Phase 2 — Synthetic ERP core)
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

**Production Plan Supply Risk Review**

1. Synthetic production plan → deterministic risk calculation ✅ IMPLEMENTED
2. RAG over synthetic engineering documents → cited retrieval ✅ IMPLEMENTED
3. Structured AI recommendation → human approval ❌ NOT IMPLEMENTED
4. Controlled procurement task creation → complete audit trace ❌ NOT IMPLEMENTED
5. Public HTTPS deployment → demo reset ❌ NOT IMPLEMENTED

**Current implementation status:** Steps 1–2 and partial step 8 (evidence display) are working. Steps 3–5 (AI recommendation, approval, procurement, audit, public deployment) are not yet implemented. See [docs/next_steps.md](docs/next_steps.md) for the full status and blockers.

## Documentation

- [Source of Truth](forgemind_project_source_of_truth/)
- [Phase 0 Bootstrap Plan](docs/planning/phase_0_bootstrap_plan.md)
- [Requirements Traceability](docs/planning/requirements_traceability_matrix.md)
- [Open Questions](docs/planning/open_questions.md)

## Technology Stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| AI/ML | ARQ + Redis, OpenAI-compatible API |
| Frontend | React 18, TypeScript, Vite, Tailwind, shadcn/ui |
| Database | PostgreSQL + pgvector |
| Infra | Docker Compose, Caddy, GitHub Actions |
| Testing | pytest, Vitest, Playwright |

## License

Proprietary — ForgeMind AI Operations
