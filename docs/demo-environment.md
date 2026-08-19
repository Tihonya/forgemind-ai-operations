# Isolated Demo Environment (WP-P7-03, DEC-056)

"Real ForgeMind in an unreal world." The Release 1 Demo runs the REAL
ForgeMind application stack — Caddy → nginx frontend → FastAPI backend →
ARQ worker → PostgreSQL (pgvector) / Redis — with production-grade security
and provider behavior (`ENVIRONMENT=production`) against SYNTHETIC demo data.

There is no "demo mode" inside the application: the demo is distinguished by
its Compose file and project identity, never by weakening the app.

## Isolation model

| Dimension | Production | Demo |
|-----------|-----------|------|
| Compose file | `docker-compose.prod.yml` | `docker-compose.demo.yml` |
| Compose project | `forgemind` | `forgemind-demo` |
| PostgreSQL database | `forgemind` (configurable) | `forgemind_demo` (hard-coded) |
| PostgreSQL volume | `postgres_data` | `demo_postgres_data` |
| Redis volume | `redis_data` | `demo_redis_data` |
| Caddy volumes | `caddy_data`/`caddy_config` | `demo_caddy_data`/`demo_caddy_config` |
| Host-published PG/Redis ports | none | none |
| Docker socket mount | none | none |
| Secrets | `infra/prod.env.example` → operator `.env` | `infra/demo.env.example` → operator `infra/demo.env` |

Demo and production never share a database, Redis state, Compose project, or
secrets. A future production stack can coexist with the demo without overlap.

## Configuration

1. Copy `infra/demo.env.example` to `infra/demo.env` (never committed).
2. Replace every `REPLACE_*` placeholder with real values (provider keys,
   DB/Redis passwords, a 32+-char `SECRET_KEY`, a demo FQDN + TLS email).
3. The demo database name is hard-coded to `forgemind_demo` in the Compose
   file — it is NOT set in the env file and cannot be redirected by config.

## Starting the demo

```bash
docker compose --env-file infra/demo.env -f docker-compose.demo.yml up -d
```

The empty demo database is migrated (`alembic upgrade head`) and seeded with
the canonical Golden Dataset via `scripts/demo-reset.sh` (see below), or
manually:

```bash
docker compose --env-file infra/demo.env -f docker-compose.demo.yml \
  exec backend python -m alembic upgrade head
docker compose --env-file infra/demo.env -f docker-compose.demo.yml \
  exec backend python -m app.seed.generator.main
```

At deployed demo runtime, Golden RAG seeding performs real embedding calls
(OpenRouter → `openai/text-embedding-3-small`, 1536 dims), and chat uses the
real OpenRouter provider. No real external BUSINESS side effect exists: the
repository contains no ERP/supplier/payment/email/webhook adapter, and the
procurement action is a synthetic local `procurement_tasks` row only.

## Reset (operator-level, disposable)

```bash
make demo-reset
# or
./scripts/demo-reset.sh
```

`scripts/demo-reset.sh` performs a full disposable reset:

1. validates the demo identity (compose file, project `forgemind-demo`,
   database `forgemind_demo`, no host ports, no Docker socket, demo env);
2. acquires a `flock` reset lock (a concurrent reset fails fast);
3. `docker compose … down -v` — destroys ONLY the demo containers/volumes;
4. starts PostgreSQL + Redis and waits healthy;
5. starts the backend and runs `python -m alembic upgrade head` (empty DB);
6. runs the canonical Golden seed (`python -m app.seed.generator.main`);
7. starts the worker/frontend/caddy and waits healthy;
8. verifies backend `/health`.

Old demo workflow/audit/session history is INTENTIONALLY discarded across a
reset (DEC-056). Audit history is meaningful and immutable only within one
demo generation; a reset starts a new clean generation.

### Fail-closed guards

The reset refuses to run unless every identity guard passes. It has NO
authority over the production stack: it pins `-f docker-compose.demo.yml`,
`-p forgemind-demo`, and the demo env file, and never accepts a database or
project name from the operator. There is no `docker compose down -v` against
an unqualified/default project.

### Failure and recovery

If a reset fails after old demo state was removed, it does NOT claim success
and exits non-zero. The demo is disposable: the documented recovery is to run
the deterministic reset again. No partial rollback into the previous demo
session is attempted.

## No reset API / no Docker-host control

There is NO browser/backend reset endpoint and NO `reset_service.py`. The
application backend cannot receive Docker-host or database-drop privileges,
and no Docker socket is mounted into any container.

## Per-browser sandbox (future)

Per-browser/per-user ephemeral sandboxes (open demo → ephemeral demo_session
→ isolated cloned baseline → destroy on reset/expiry) are a future evolution
and are NOT implemented in Release 1. Release 1 uses ONE isolated shared Demo
environment.
