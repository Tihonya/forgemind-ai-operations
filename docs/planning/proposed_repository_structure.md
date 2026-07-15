# Proposed Repository Structure

Full directory tree for `forgemind-ai-operations` after Phase 0 bootstrap.

```
forgemind-ai-operations/
│
├── forgemind_project_source_of_truth/          # IMMUTABLE — normative SoT docs
│   ├── MANIFEST.md
│   ├── README.md
│   ├── 00_PROJECT_CHARTER.md
│   ├── 01_PRODUCT_AND_MVP_SCOPE.md
│   ├── 02_SYSTEM_BEHAVIOR_AND_DATA.md
│   ├── 03_DEFINITION_OF_DONE.md
│   ├── 04_ACCEPTANCE_TESTS.md
│   ├── 05_DEPLOYMENT_AND_DEMO.md
│   ├── 06_AI_AGENT_EXECUTION_RULES.md
│   ├── 07_ROADMAP.md
│   ├── 08_DECISION_LOG.md
│   └── 09_MASTER_TASK_FOR_HERMES.md
│
├── backend/                                    # FastAPI application
│   ├── pyproject.toml                          # Python deps, project metadata
│   ├── alembic.ini                             # Alembic config
│   ├── alembic/
│   │   ├── env.py                              # Migration environment
│   │   ├── script.py.mako                      # Migration template
│   │   └── versions/                           # Migration files (auto-generated)
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                             # FastAPI app factory, lifespan
│   │   ├── config.py                           # pydantic-settings (env-driven)
│   │   ├── database.py                         # SQLAlchemy engine, session factory
│   │   ├── dependencies.py                     # DI: auth, db session, current user
│   │   │
│   │   ├── models/                             # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── business.py                     # products, product_versions, components,
│   │   │   │                                   # bom_items, suppliers, purchase_orders,
│   │   │   │                                   # purchase_order_lines, production_plans,
│   │   │   │                                   # production_orders, production_order_requirements,
│   │   │   │                                   # procurement_tasks
│   │   │   ├── inventory.py                    # warehouses, inventory_balances,
│   │   │   │                                   # inventory_reservations
│   │   │   ├── knowledge.py                    # documents, document_versions,
│   │   │   │                                   # document_permissions, knowledge_chunks,
│   │   │   │                                   # component_alternatives
│   │   │   ├── ai.py                           # agent_definitions, agent_versions,
│   │   │   │                                   # workflow_runs, workflow_steps,
│   │   │   │                                   # retrieval_events, model_calls
│   │   │   └── governance.py                   # users, roles, user_roles,
│   │   │                                       # approval_requests, audit_events
│   │   │
│   │   ├── schemas/                            # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                         # Login, token, user profile
│   │   │   ├── risk.py                         # Risk list, risk detail, evidence
│   │   │   ├── approval.py                     # Approval request, approve/reject
│   │   │   ├── audit.py                        # Audit event, audit list
│   │   │   ├── document.py                     # Document list, detail, versions
│   │   │   ├── workflow.py                     # Workflow run, steps, trace
│   │   │   ├── dashboard.py                    # Dashboard KPIs
│   │   │   └── ai_output.py                    # Structured AI output schema v1.0
│   │   │                                       # (versioned, validated by output_validator)
│   │   │
│   │   ├── api/                                # Route modules
│   │   │   ├── __init__.py
│   │   │   ├── router.py                       # Top-level router assembly
│   │   │   ├── health.py                       # GET /health, GET /ready
│   │   │   ├── auth.py                         # POST /auth/login, GET /auth/me
│   │   │   ├── dashboard.py                    # GET /dashboard
│   │   │   ├── risks.py                        # GET /risks, GET /risks/{id},
│   │   │   │                                   # POST /risks/analyze
│   │   │   ├── approvals.py                    # GET /approvals, POST /approvals/{id}/approve,
│   │   │   │                                   # POST /approvals/{id}/reject
│   │   │   ├── documents.py                    # GET /documents, GET /documents/{id}
│   │   │   ├── workflows.py                    # GET /workflows/runs, GET /workflows/runs/{id}
│   │   │   ├── audit.py                        # GET /audit
│   │   │   └── admin.py                        # POST /admin/reset, GET /admin/model-status
│   │   │
│   │   ├── services/                           # Business logic layer
│   │   │   ├── __init__.py
│   │   │   ├── risk_engine.py                  # DETERMINISTIC risk calculation
│   │   │   │                                   # (AT-004: must return exactly 3 risks)
│   │   │   ├── bom_explosion.py                # BOM expansion for production orders
│   │   │   ├── inventory_service.py            # Stock, reservations, incoming supply
│   │   │   ├── approval_service.py             # Approval creation, approve/reject logic
│   │   │   ├── audit_service.py                # Immutable audit event recording
│   │   │   ├── auth_service.py                 # JWT/session, role resolution
│   │   │   └── reset_service.py                # Demo reset: drop + re-seed
│   │   │
│   │   ├── ai/                                 # AI/LLM layer
│   │   │   ├── __init__.py
│   │   │   ├── provider.py                     # OpenAI-compatible adapter
│   │   │   │                                   # (cloud + local through same contract)
│   │   │   ├── output_validator.py             # Pydantic validation of AI output
│   │   │   │                                   # (AT-008: invalid → FAILED_VALIDATION)
│   │   │   ├── prompts/                        # Versioned prompt templates
│   │   │   │   ├── registry.py                 # Prompt version registry
│   │   │   │   └── v1/
│   │   │   │       └── supply_risk.txt         # Supply risk analysis prompt v1
│   │   │   ├── rag/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── indexer.py                  # Document → chunks → embeddings → pgvector
│   │   │   │   ├── retriever.py                # Similarity search + role-based filtering
│   │   │   │   └── citations.py                # Format citations with doc_id, version, chunk_id
│   │   │   └── workflow/
│   │   │       ├── __init__.py
│   │   │       ├── machine.py                  # Explicit state machine (states, transitions)
│   │   │       ├── steps.py                    # Individual workflow steps
│   │   │       └── runner.py                   # Orchestrate a full workflow run
│   │   │
│   │   ├── tasks/                              # Background jobs (ARQ)
│   │   │   ├── __init__.py
│   │   │   ├── indexing.py                     # Document ingestion (async)
│   │   │   └── ai_runs.py                      # Async workflow execution
│   │   │
│   │   └── core/                               # Shared utilities
│   │       ├── __init__.py
│   │       ├── exceptions.py                   # Custom exception hierarchy
│   │       ├── logging.py                      # Structured JSON logging
│   │       └── correlation.py                  # Correlation ID generation (UUID v4)
│   │
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py                         # Fixtures: test DB, test client, seed data
│       ├── unit/
│       │   ├── test_risk_engine.py             # AT-004 — exact 3 risks
│       │   ├── test_bom_explosion.py           # BOM expansion correctness
│       │   ├── test_inventory.py               # Stock/reservation calculations
│       │   ├── test_output_validator.py        # AT-008 — schema validation
│       │   ├── test_approval_service.py        # AT-009, AT-010, AT-011
│       │   └── test_rbac.py                    # FR-02 role enforcement
│       ├── integration/
│       │   ├── test_api_auth.py                # AT-002
│       │   ├── test_api_risks.py               # AT-005 — real data, no mocks
│       │   ├── test_api_approvals.py           # AT-009, AT-010, AT-011
│       │   ├── test_api_dashboard.py           # FR-10
│       │   ├── test_rag_retrieval.py           # AT-006, AT-007
│       │   ├── test_workflow_trace.py          # AT-012
│       │   ├── test_audit_trace.py             # AT-012 — complete chain
│       │   ├── test_reset.py                   # AT-015
│       │   └── test_seed.py                    # AT-003 — dataset integrity
│       └── e2e/
│           └── test_golden_scenario.py         # Full Golden Scenario end-to-end
│
├── frontend/                                   # React + TypeScript + Vite
│   ├── package.json
│   ├── tsconfig.json                           # Strict TypeScript
│   ├── vite.config.ts                          # Dev server + proxy /api → backend:8000
│   ├── tailwind.config.ts                      # Tailwind + shadcn/ui preset
│   ├── postcss.config.js
│   ├── index.html
│   ├── components.json                         # shadcn/ui config
│   ├── public/
│   │   └── favicon.svg
│   │
│   ├── src/
│   │   ├── main.tsx                            # React entry point
│   │   ├── App.tsx                             # Root component + router
│   │   │
│   │   ├── routes/                             # Page components (React Router)
│   │   │   ├── login.tsx                       # Login screen (AT-002)
│   │   │   ├── dashboard.tsx                   # Executive Dashboard (FR-10)
│   │   │   ├── risks.tsx                       # Supply Risk list + filters
│   │   │   ├── risk-detail.tsx                 # Risk detail + evidence panel
│   │   │   ├── approvals.tsx                   # Approval Center
│   │   │   ├── documents.tsx                   # Knowledge Sources
│   │   │   ├── workflow-run.tsx                # Workflow Run Details (step timeline)
│   │   │   ├── audit-log.tsx                   # Audit Log viewer
│   │   │   └── admin.tsx                       # Admin / Model Status
│   │   │
│   │   ├── components/                         # Shared UI components
│   │   │   ├── ui/                             # shadcn/ui primitives
│   │   │   ├── layout/                         # App shell, sidebar, header
│   │   │   ├── risk/                           # Risk card, severity badge
│   │   │   ├── approval/                       # Approval form, status indicator
│   │   │   ├── workflow/                       # Step timeline, tool call display
│   │   │   └── charts/                         # Recharts wrappers
│   │   │
│   │   ├── hooks/                              # Custom React hooks
│   │   │   ├── use-auth.ts                     # Auth state + login/logout
│   │   │   ├── use-risks.ts                    # TanStack Query for risks
│   │   │   ├── use-approvals.ts                # TanStack Query for approvals
│   │   │   └── use-workflow.ts                 # Polling for workflow progress
│   │   │
│   │   ├── lib/                                # Utilities
│   │   │   ├── api-client.ts                   # Fetch wrapper with auth headers
│   │   │   ├── query-client.ts                 # TanStack Query client config
│   │   │   └── utils.ts                        # General helpers
│   │   │
│   │   ├── store/                              # Zustand stores
│   │   │   ├── auth-store.ts                   # Auth state (user, token, role)
│   │   │   └── ui-store.ts                     # Sidebar state, theme
│   │   │
│   │   └── styles/
│   │       └── globals.css                     # Tailwind directives + theme vars
│   │
│   └── tests/
│       ├── dashboard.test.tsx                  # Dashboard renders real data
│       ├── risk-list.test.tsx                  # Risk list + filters
│       ├── approval.test.tsx                   # Approve/reject flow
│       └── login.test.tsx                      # Login form + error states
│
├── seed/                                       # Synthetic dataset
│   ├── README.md                               # Dataset documentation, version, checksum
│   │
│   ├── generator/                              # Python scripts to generate data
│   │   ├── __init__.py
│   │   ├── main.py                             # Seed command entry point
│   │   ├── products.py                         # Synthetic products + versions
│   │   ├── components.py                       # Synthetic components
│   │   ├── bom.py                              # BOM items (must produce golden risks)
│   │   ├── inventory.py                        # Warehouses, balances, reservations
│   │   ├── suppliers.py                        # Suppliers, purchase orders
│   │   ├── production_plans.py                 # PLAN-2026-W31 + work orders
│   │   ├── documents.py                        # Synthetic technical documents
│   │   └── users.py                            # Demo users (5 roles)
│   │
│   ├── fixtures/                               # Versioned golden dataset snapshot
│   │   └── .gitkeep                            # Populated in Phase 2
│   │
│   └── documents/                              # Synthetic technical docs (markdown)
│       └── .gitkeep                            # Populated in Phase 4
│
├── infra/                                      # Deployment infrastructure
│   ├── docker/
│   │   ├── backend.dockerfile                  # Python image, pip install, uvicorn
│   │   ├── frontend.dockerfile                 # Node build → nginx static serve
│   │   └── worker.dockerfile                   # Same as backend, runs ARQ worker
│   │
│   ├── caddy/
│   │   └── Caddyfile                           # Reverse proxy: frontend, backend, /api
│   │
│   └── scripts/
│       ├── deploy.sh                           # VPS deployment script
│       ├── backup.sh                           # PostgreSQL backup
│       └── restore.sh                          # PostgreSQL restore
│
├── scripts/                                    # Dev & utility scripts
│   ├── seed.sh                                 # Run seed generator
│   ├── reset.sh                                # Run demo reset
│   ├── run-tests.sh                            # Run backend + frontend + e2e tests
│   └── check-secrets.sh                        # Detect secrets in tracked files
│
├── release-evidence/                           # Populated at release time (Phase 8)
│   └── .gitkeep
│
├── docs/                                       # Project documentation
│   ├── planning/                               # Phase 0 planning artifacts
│   │   ├── phase_0_bootstrap_plan.md           # Full bootstrap plan
│   │   ├── requirements_traceability_matrix.md # FR → test → AT mapping
│   │   ├── open_questions.md                   # Decisions needed from PO
│   │   └── proposed_repository_structure.md    # This file
│   │
│   ├── architecture.md                         # Architecture diagram + explanation
│   │                                           # (deferred — created after Phase 1)
│   ├── api-reference.md                        # API endpoint documentation
│   │                                           # (deferred — created after Phase 2)
│   ├── deployment-guide.md                     # Deployment instructions
│   │                                           # (deferred — created during Phase 7)
│   │
│   ├── runbooks/                               # Operational procedures
│   │   └── .gitkeep                            # (deferred — created during Phase 7)
│   │
│   └── trade-offs.md                           # Design trade-offs and limitations
│                                               # (populated incrementally)
│
├── .github/
│   ├── workflows/
│   │   ├── ci-backend.yml                      # Install, lint, test backend
│   │   ├── ci-frontend.yml                     # Install, lint, build frontend
│   │   └── ci-e2e.yml                          # Full stack + e2e tests
│   │
│   └── ISSUE_TEMPLATE/
│       ├── task.md                             # Task template (per 06 §3 format)
│       └── bug.md                              # Bug report template
│
├── docker-compose.yml                          # Full stack: backend, frontend, worker,
│                                               # postgres, redis, caddy
├── docker-compose.dev.yml                      # Dev overrides: bind mounts, hot reload,
│                                               # debug ports, test DB
├── .env.example                                # All env vars with placeholder values
├── .gitignore                                  # Python, Node, Docker, env, IDE patterns
├── .dockerignore                               # Exclude node_modules, .git, __pycache__
├── Makefile                                    # Convenience targets
├── README.md                                   # Project-level README (root)
└── LICENSE                                     # MIT
```

---

## Design Principles

1. **Vertical slices**: Each directory maps to a clear responsibility. No cross-cutting utility sprawl.
2. **Separation of concerns**: Models (DB) → Schemas (API) → Services (logic) → API (routes) → AI (LLM).
3. **Deterministic first**: Risk engine has zero LLM dependency. AI layer sits on top.
4. **Test co-location**: Tests mirror the source structure (`unit/`, `integration/`, `e2e/`).
5. **Infrastructure as code**: Docker, Caddy, CI — all versioned, no manual VPS configuration.
6. **Seed as code**: Golden dataset generated by code, not hand-crafted JSON.
7. **Planning artifacts**: `docs/planning/` holds design decisions before implementation.
