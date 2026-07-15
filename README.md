# ForgeMind AI Operations

Supply Risk Intelligence — a portfolio-grade industrial AI demonstration.

## Overview

ForgeMind demonstrates a complete enterprise-grade AI workflow for supply chain risk assessment. It combines deterministic business logic, RAG-powered document intelligence, and structured AI recommendations with full audit traceability and human-in-the-loop approval.

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

# Seed demo data (deferred to Phase 1)
make seed

# Reset demo data (deferred to Phase 1)
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

1. Synthetic production plan → deterministic risk calculation
2. RAG over synthetic engineering documents → cited retrieval
3. Structured AI recommendation → human approval
4. Controlled procurement task creation → complete audit trace
5. Public HTTPS deployment → demo reset

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
