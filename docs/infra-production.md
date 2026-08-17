# ForgeMind — Production Deployment Runbook (WP-P7-02)

Repository-owned Release 1 deployment and security configuration.
This document is operational documentation directly owned by WP-P7-02.

Scope boundary: this runbook describes the repository configuration
and the manual first-deployment procedure. It does NOT perform any
deployment. VPS hardening, DNS, TLS procurement, staging/production
deployment, and live provider calls are separate bounded actions.

## 1. Topology

Host: single VPS (16 GB RAM, 200 GB storage) + Docker Compose.

```
Internet
  │  HTTP/HTTPS only
  ▼
Caddy (automatic HTTPS, {:CADDY_DOMAIN}, TLS contact {:CADDY_EMAIL})
  ├── /health        → backend:8000  (flat status payload, no secrets)
  ├── /api/*         → backend:8000  (auth required; JWT from login)
  └── everything else → nginx (SPA)
                            └── /api → (same origin via Caddy)
Backend (uvicorn, `production` Dockerfile target, non-root appuser)
  ├── PostgreSQL + pgvector   (private `backend` network only)
  ├── Redis                   (private `backend` network only)
  └── ARQ worker              (heartbeat healthcheck in Redis)

Externally reachable: ONLY Caddy (80, 443, 443/udp).
No Docker socket mounts. No secrets inside any image or Compose file.
```

Interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are not
routed on the public origin (Caddy) — they remain reachable only on
the private backend network.

## 2. Production environment workflow

1. Copy `infra/prod.env.example` to the deployment directory as `.env`
   on the VPS. Fill every `REPLACE_*` placeholder with a real value.
   Never commit the filled file.
2. Set restrictive permissions: `chmod 600 .env`.
3. Required FQDN/email are deployment-time Product Owner inputs; no
   FQDN is fabricated by the repository.

## 3. Fail-closed configuration validation (REQUIRED before deploy)

```bash
# inside the backend container (or local venv with the same env vars)
python -m app.ops.validate_config
```

Exit code 0 = every Release 1 rule passes. Any single error → non-zero
and the deployment must not proceed. The report never prints secret
values (set/not-set only).

Enforced rules include:
- ENVIRONMENT=production, strong SECRET_KEY;
- explicit DATABASE_URL / REDIS_URL (no placeholders);
- DISTRIBUTED_RATE_LIMIT_ENABLED=true + RATE_LIMIT_DEGRADED_MODE=fail_closed;
- chat = OpenRouter only (`CHAT_PROVIDER_MODE=openrouter`,
  `OPENROUTER_CHAT_MODEL=qwen/qwen3.7-flash`, json_object, no fallback);
- embeddings = `EMBEDDING_PROVIDER=openai`,
  `OPENAI_API_BASE=https://openrouter.ai/api/v1`,
  `OPENAI_EMBEDDING_MODEL=openai/text-embedding-3-small`,
  `EMBEDDING_DIMENSIONS=1536`, OPENAI_API_KEY = OpenRouter key (PD-3a);
- CADDY_DOMAIN + CADDY_EMAIL explicitly supplied.

## 4. Distributed rate limiting (production-safe)

The Redis-backed limiter (`backend/app/core/rate_limit.py`) shares one
budget across ALL backend/worker processes:

- HTTP request budget: `RATE_LIMIT_PER_MINUTE` per client, enforced by
  the ASGI middleware in staging/production; 429 with correlation ID on
  rejection.
- AI provider budget: `AI_RATE_LIMIT_PER_MINUTE` shared across
  processes at the provider boundary.
- Redis outage → `fail_closed` rejects requests (never silently
  unlimited). `fail_open` exists only as an explicit operator choice.

## 5. Deploy (manual, checklist-driven — PD-9)

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend python -m seed.generator.main
curl -f https://<FQDN>/health   # expect JSON, status healthy/degraded
```

All commands run from the deployment directory with `.env` present.
Caddy obtains the certificate automatically after the first successful
deployment (automatic HTTPS; no manual cert handling).

## 6. Backups (PD-8)

Daily pg_dump with 7-day retention via the compose `backup` profile:

```bash
docker compose -f docker-compose.prod.yml --profile backup up -d
```

Dumps are written to `./backups` on the host (custom format, chmod 600).
Off-host replication is an operator responsibility (documented
integration point: `backups/` directory; no credentials are fabricated).

Manual operations wrapper (`scripts/backup.sh`):

```bash
bash scripts/backup.sh backup   ./backups
bash scripts/backup.sh prune    ./backups 7
bash scripts/backup.sh restore  ./backups/forgemind-XXXX.dump forgemind
bash scripts/backup.sh rehearse ./backups forgemind
```

`rehearse` restores the newest dump into a throwaway database,
verifies the restored table count, and drops the scratch DB. It never
touches the live database. The restore rehearsal MUST be performed and
validated against an authorized local/test environment before
production (Phase 7 staging-entry gates).

## 7. Logs and disk safety (PD-10)

- All services: json-file driver, max-size 10m, max-file 3 (set via the
  YAML anchor in docker-compose.prod.yml).
- Structured JSON logs from backend/worker to stdout/stderr.
- Monitoring remains intentionally bounded: Docker logs, `/health`,
  and the checklist-driven deployment verification.

## 8. Health behavior

- backend → `curl http://localhost:8000/health` (real dependency
  checks; HTTP 200 with a degraded summary even when a dependency is
  down — the payload distinguishes healthy/degraded/unhealthy and never
  exposes secrets or URLs).
- worker → `/usr/local/bin/worker-healthcheck` reads the ARQ heartbeat
  key from Redis (well-formed value = alive; absent/malformed = start
  or stopped; redis failure = unhealthy).
- frontend → nginx static health.
- postgres/redis → native `pg_isready` / `redis-cli ping` probes.

## 9. Embedding smoke — preparation + boundaries

The smoke harness (`backend/app/ops/embedding_smoke.py`) runs offline
by default: it verifies the PD-3a configuration contract and vector
check logic, reports live-only items as `not_run`, and NEVER calls a
provider. A live call requires a separately authorized gate — the
harness itself refuses unless both the `--live` flag AND
`FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM=yes` are present (double
barrier against accidental credit consumption).

The future live gate must additionally verify (contract, PD-3a):
authenticated request, exact model
`openai/text-embedding-3-small`, exactly 1536 numeric finite
dimensions, deterministic repeated input, DB insertion compatibility,
Golden Dataset seeding, runtime retrieval with citations, seed/query
provider consistency, fail-closed invalid-credential behavior, and no
secrets in evidence.

## 10. What is NOT in this runbook

- VPS hardening (separate bounded action; host controls listed in the
  Phase 7 contract section 7 are not claimed operational here).
- DNS mutation, real TLS/Let's Encrypt interaction on a real host.
- Staging/production deployment execution.
- Live OpenRouter/OpenAI/Groq calls.
- Demo reset (WP-P7-03), login demo UX (WP-P7-04), README/license
  reconciliation (WP-P7-05).