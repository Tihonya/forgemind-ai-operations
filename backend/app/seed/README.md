# Seed Data — Deferred to Phase 1

**Status:** This directory is a placeholder. No seed generators exist in Phase 0.

## Purpose

When implemented in Phase 1, the seed module will provide a synthetic golden dataset for demonstrating the Supply Risk Intelligence workflow:

1. Synthetic production plan
2. Deterministic risk calculation
3. RAG over synthetic engineering documents
4. Structured AI recommendations
5. Human approval workflow
6. Audit trail

## Current State (Phase 0)

- No files in this directory are functional
- `make seed` exits gracefully with a deferred-to-Phase-1 message
- `./scripts/seed.sh` performs the same check

## Planned Structure (Phase 1)

```
seed/
├── generator/
│   ├── main.py              # Entry point
│   ├── production_plans.py  # Synthetic production plans
│   ├── inventory.py         # Inventory and BOM data
│   ├── risks.py             # Risk scenarios
│   ├── documents.py         # Synthetic engineering documents
│   └── users.py             # Demo user accounts
└── README.md
```

## Demo Accounts (Planned)

| Email | Role | Password |
|-------|------|----------|
| manager.demo@forgemind.ai | Production Manager | demo123 |
| procurement.demo@forgemind.ai | Procurement Specialist | demo123 |
| engineer.demo@forgemind.ai | Engineer | demo123 |
| auditor.demo@forgemind.ai | Auditor | demo123 |
| admin.demo@forgemind.ai | AI Administrator | demo123 |

## Important Notes

- All data will be synthetic — no real corporate or confidential information
- Risk calculations will be deterministic and reproducible
- Documents will be generated for RAG demonstration
- The dataset will support the complete Golden Scenario end-to-end
- **Implementation is deferred to Phase 1 — no functionality exists in Phase 0**
