# ForgeMind — Release 1 Operator Runbook

This is the canonical Release 1 operator runbook. It documents the full
operational lifecycle using actual repository commands and scripts.

For the detailed production deployment configuration (topology, security
contracts, credential policy, rate limiting, embedding smoke), see
[docs/infra-production.md](../infra-production.md). This runbook
complements that document with an operator-facing procedure index.

**Boundary:** This runbook documents procedures. It does NOT execute
any deployment. No VPS access, DNS mutation, TLS procurement, or live
provider call is authorized by this document.

---

## 1. Prerequisites

- Single VPS (16 GB RAM, 200 GB storage) per Phase 7 contract PD-1
- Docker and Docker Compose installed on the deployment host
- Production FQDN and TLS contact email (Product Owner deployment-time input)
- OpenRouter account with API key (used for both chat and embeddings)
- All secrets prepared via `infra/prod.env.example` — see §2 below
- VPS security hardening completed and independently verified (separate
  bounded action; see Phase 7 contract §7)

---

## 2. Production configuration preparation

### 2.1 Secret handling

```bash
# On the VPS, in the deployment directory:
cp infra/prod.env.example .env
chmod 600 .env
# Edit .env — replace EVERY REPLACE_* placeholder with a real value
```

Secret variables (by NAME only — never commit real values):

| Variable | Purpose |
|----------|---------|
| `CADDY_DOMAIN` | Production FQDN |
| `CADDY_EMAIL` | TLS contact email (Let's Encrypt) |
| `SECRET_KEY` | JWT signing secret (≥32 random characters) |
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password (URL-safe alphabet only: A-Z a-z 0-9 . _ ~ -) |
| `REDIS_PASSWORD` | Redis password (same URL-safe alphabet) |
| `OPENAI_API_KEY` | OpenRouter key for the embedding path |
| `OPENROUTER_API_KEY` | OpenRouter key for the chat path |

**Password policy:** `POSTGRES_PASSWORD` and `REDIS_PASSWORD` are
interpolated verbatim into `DATABASE_URL` / `REDIS_URL`. Only URL-safe
characters (`A-Z a-z 0-9 . _ ~ -`) are accepted. The production config
validator rejects others. See `docs/infra-production.md` §2.1.

### 2.2 Compose validation

```bash
make compose-validate
```

Validates `docker-compose.prod.yml` resolves with the template env file.
Uses `infra/prod.env.example` — no real secrets needed.

### 2.3 Caddyfile validation

```bash
make caddy-validate
```

Validates the production Caddyfile with safe placeholder env
(`CADDY_DOMAIN=example.com`).

### 2.4 Production config validation (fail-closed)

```bash
# Local venv (development):
make config-validate

# On the deployment host (inside the backend container):
docker compose -f docker-compose.prod.yml exec backend python -m app.ops.validate_config
```

Exit code 0 = every Release 1 rule passes. Any error → non-zero exit
and the deployment must NOT proceed. The report never prints secret
values (set/not-set only).

Enforced rules include: `ENVIRONMENT=production`, strong `SECRET_KEY`,
explicit `DATABASE_URL`/`REDIS_URL`, URL-safe credential alphabet,
`DISTRIBUTED_RATE_LIMIT_ENABLED=true` + `fail_closed`, OpenRouter-only
chat (`qwen/qwen3.7-flash`, `json_object`, no fallback), OpenRouter
embedding (`openai/text-embedding-3-small`, 1536 dims), real FQDN/email,
no template placeholders. See `docs/infra-production.md` §3 for the full
list.

---

## 3. Build and start (future deployment procedure)

> This section documents the procedure. It must NOT be executed from
> this repository task. VPS deployment is a separate bounded action
> (WP-P7-06).

```bash
# From the deployment directory on the VPS (with .env present):
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --build
```

Caddy obtains the TLS certificate automatically after the first
successful start (automatic HTTPS; no manual cert handling).

---

## 4. Migrations

```bash
docker compose -f docker-compose.prod.yml exec backend python -m alembic upgrade head
```

Run database migrations after the backend container is healthy and before
seeding.

---

## 5. Canonical Golden seed

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.seed.generator.main
```

Generates the synthetic golden dataset: production plans, BOMs, inventory,
suppliers, engineering documents, demo user accounts (with bcrypt-hashed
passwords), and role assignments. Also triggers embedding generation for
RAG documents via the configured embedding provider.

For local development: `make seed`

---

## 6. Health verification

```bash
# Backend health (JSON payload, no secrets):
curl -f https://<FQDN>/health

# Expected: HTTP 200, status "healthy" or "degraded"
# Degraded means a dependency check failed — inspect the payload
```

The `/health` endpoint reports backend, PostgreSQL, and Redis dependency
status. It is exempt from the per-client rate-limit budget so it stays
reachable during limiter Redis outages. See `docs/infra-production.md` §8.

Worker health: the ARQ worker has a Redis-heartbeat healthcheck
(`/usr/local/bin/worker-healthcheck`). See `docs/infra-production.md` §8.

---

## 7. Logs

```bash
# All services (json-file driver, 10m max-size, 3 files per service):
docker compose -f docker-compose.prod.yml logs -f

# Specific service:
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f worker

# Backup state marker (non-secret):
cat ./backups/last_backup_state
# "ok <epoch>" = last backup succeeded
# "failed <epoch>" = last backup failed
```

Log rotation is configured in `docker-compose.prod.yml` via the
`logging` YAML anchor (`max-size: 10m`, `max-file: 3`).

---

## 8. Operator-level Demo reset

The Release 1 Demo uses an isolated disposable environment
(`docker-compose.demo.yml`, Compose project `forgemind-demo`).

```bash
# Reset the demo environment (full disposable reset):
make demo-reset
# or:
./scripts/demo-reset.sh
```

The reset script:
1. Validates demo identity (compose file, project, database, no host ports)
2. Acquires a `flock` reset lock (concurrent reset fails fast)
3. Destroys demo containers and demo PostgreSQL + Redis volumes only
4. Starts PostgreSQL + Redis, waits healthy
5. Runs `alembic upgrade head` on the empty database
6. Runs the canonical Golden seed
7. Starts worker, frontend, Caddy, waits healthy
8. Verifies backend `/health`

Caddy TLS/ACME volumes are preserved across resets. Old demo history is
intentionally discarded (DEC-056). See [docs/demo-environment.md](../demo-environment.md).

---

## 9. Backup

### 9.1 Start the scheduled backup daemon (canonical production mechanism)

```bash
docker compose -f docker-compose.prod.yml --profile backup up -d
```

Daily `pg_dump` with 7-day retention via `scripts/backup-cycle.sh`.
The backup service runs inside the Compose topology on the private
`backend` Docker network — it reaches PostgreSQL via the `postgres`
hostname on that network. No host PostgreSQL port is published or
required. Backups land in `./backups` on the host (bind mount). The
operator owns off-host replication.

The backup container (`postgres:16-alpine`) sets `PGPASSWORD` from
`${POSTGRES_PASSWORD}` and `PGHOST` defaults to `postgres` (inside
the cycle script). The host-side `.env` file is NOT automatically
equivalent to `PGHOST`/`PGUSER`/`PGPASSWORD` — those are Docker
Compose interpolation variables, not shell-exported PG client vars.

### 9.2 Manual backup operations

Production PostgreSQL intentionally has NO host port publication. It
is reachable only inside the private Docker network. Manual backup and
restore operations MUST be executed through the existing PostgreSQL
service/container where the real database environment and network are
already available — NOT via host-side `bash scripts/backup.sh` (which
requires separately configured `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`
and network access that the current production topology does not
provide).

**Manual backup (via the PostgreSQL container):**

```bash
# Ensure the host backup directory exists:
mkdir -p ./backups

# Create a manual backup via the postgres container on the private
# Compose network. pg_dump uses the container's environment
# (POSTGRES_USER, POSTGRES_DB, PGPASSWORD are already set).
# The dump is written to stdout and redirected to the host file.
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -lc 'pg_dump --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" --format=custom' \
  > "./backups/forgemind-$(date -u +%Y%m%d_%H%M%S).dump"

# Restrict permissions on the backup file:
chmod 600 ./backups/forgemind-*.dump
```

> **Note:** `scripts/backup.sh` is a repository utility for environments
> where `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD` and network access are
> intentionally provided. It is NOT the default production-host command
> and CANNOT be executed correctly in the current production topology
> without separately configuring PostgreSQL-client network access.

### 9.3 Failure visibility

- Failed `pg_dump` stops the cycle — retention never runs after a failed dump
- `./backups/last_backup_state` records `ok <epoch>` / `failed <epoch>`
- The backup service healthcheck reports unhealthy while the last cycle failed
- After a failure, the cycle retries after 1 hour without touching retention

See `docs/infra-production.md` §6 for full backup guarantees.

---

## 10. Restore and rehearsal

**Restore from a specific dump (via the PostgreSQL container):**

```bash
# 1. Stop backend and worker to prevent concurrent writes:
docker compose -f docker-compose.prod.yml stop backend worker

# 2. Restore from a specific dump file. The dump file is already on
#    the host in ./backups. Use the postgres container where the
#    database environment and network are available:
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -lc 'pg_restore --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" --no-owner --no-privileges --clean' \
  < "./backups/forgemind-XXXX.dump"

# 3. Restart services:
docker compose -f docker-compose.prod.yml up -d
```

> **Warning:** Restore is destructive — `--clean` drops existing
> database objects before recreating them from the dump. Verify the
> target database name and the dump file before proceeding.

**Rehearsal (throwaway database — never touches live DB):**

```bash
# 1. Create a throwaway database inside the postgres container:
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -lc 'createdb --username="${POSTGRES_USER}" \
  "forgemind_rehearsal_$(date +%s)"'

# 2. Restore the newest dump into the throwaway database:
NEWEST=$(ls -1t ./backups/forgemind-*.dump 2>/dev/null | head -1)
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -lc 'pg_restore --username="${POSTGRES_USER}" \
  --dbname="forgemind_rehearsal_SCRATCH" --no-owner --no-privileges' \
  < "${NEWEST}"

# 3. Verify the restored table count:
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -lc 'psql --username="${POSTGRES_USER}" \
  --dbname="forgemind_rehearsal_SCRATCH" -tAc \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('"'"'pg_catalog'"'"','"'"'information_schema'"'"');"'"

# 4. Drop the throwaway database:
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -lc 'dropdb --username="${POSTGRES_USER}" \
  "forgemind_rehearsal_SCRATCH"'
```

> **Rehearsal rules:**
> - Use a throwaway database — create, restore, verify, drop.
> - NEVER touch the live production database during rehearsal.
> - The rehearsal database name must not match the production database name.
> - Replace `forgemind_rehearsal_SCRATCH` with a unique scratch name per run.
> - Restore rehearsal MUST be performed and validated before production
>   (Phase 7 staging-entry gates).

> **Security boundary:** PostgreSQL remains private — no host port is
> published. All manual operations above use `docker compose exec` against
> the `postgres` service on the private Compose network. The host-side
> `.env` file provides Docker Compose interpolation variables
> (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) but these are NOT
> automatically equivalent to shell-exported `PGHOST`/`PGUSER`/`PGPASSWORD`
> for direct host-side PostgreSQL client tools.

---

## 11. Rollback and recovery

### 11.1 Application rollback (known-good git commit)

The Compose topology builds application images from source at deploy time
(see `docker-compose.prod.yml` — `backend`, `worker`, and `frontend` use
`build:` context, not pinned `image:` tags). There is no versioned-image
registry or pre-built image cache to select from. A rollback therefore
requires restoring the repository to a known-good commit and rebuilding.

**Prerequisites:**

- A known-good deployment commit SHA must have been previously verified
  (record it at deployment time).
- Database schema compatibility must be verified: if the known-good
  commit's Alembic migrations are not compatible with the current database
  state, a database backup restore may be required (see §11.2 and §10).
- The operator must have access to the deployment directory with `.env`.

**Procedure:**

```bash
# 1. Identify and record the known-good verified deployment commit SHA.
#    (This SHA must be recorded at the original deployment time.)
KNOWN_GOOD_SHA="<known-good-commit-sha>"

# 2. Record the current deployment SHA for audit purposes.
git rev-parse HEAD

# 3. Stop backend and worker (or the full stack) to prevent writes:
docker compose -f docker-compose.prod.yml stop backend worker

# 4. Fetch the latest repository state:
git fetch origin

# 5. Check out the exact known-good commit in detached-HEAD state:
git checkout --detach "${KNOWN_GOOD_SHA}"

# 6. Rebuild application images from the known-good revision:
docker compose -f docker-compose.prod.yml up -d --build

# 7. Run health verification:
curl -f https://<FQDN>/health
# Expected: HTTP 200, status "healthy" or "degraded"
```

**Warnings:**

- `docker compose up -d --build` rebuilds from the current working tree.
  Without checking out the known-good commit, the rebuild deploys the
  current code — NOT a previous version.
- If the database schema has migrated forward incompatibly since the
  known-good commit, code-only rollback is NOT sufficient. Restore the
  matching database backup (see §11.2) from before the problematic
  migration.
- This procedure does NOT implement image tagging or pinning. The
  Compose file uses `build:` context; each `up --build` produces images
  from the current source tree.

### 11.2 Database rollback (restore from backup)

**Prerequisites:**

- A verified backup dump must exist in `./backups`.
- Backend and worker MUST be stopped before restoring a live target
  database to prevent concurrent writes.
- Restore is destructive — it overwrites the target database.

```bash
# 1. Stop backend and worker:
docker compose -f docker-compose.prod.yml stop backend worker

# 2. Restore from a specific dump (via the PostgreSQL container on the
#    private Compose network — no host PostgreSQL port required):
#    See §10 for the canonical manual backup/restore procedure.

# 3. Restart services:
docker compose -f docker-compose.prod.yml up -d
```

### 11.3 Emergency shutdown

```bash
# Stop and remove containers (named volumes preserved):
docker compose -f docker-compose.prod.yml down
```

### 11.4 Demo recovery

The demo is disposable — run `make demo-reset` again.
No partial rollback is attempted.

---

## 12. Shutdown

**Stop services (retain containers):**

```bash
# Stop containers without removing them — containers can be restarted
# with `docker compose ... start`. Named volumes and networks preserved.
docker compose -f docker-compose.prod.yml stop
```

**Stop and remove containers (preserve named volumes):**

```bash
# Stops and REMOVES service containers and Compose networks.
# Named volumes are preserved (databases/Redis data retained).
docker compose -f docker-compose.prod.yml down
```

**Stop and remove everything including volumes (DESTRUCTIVE):**

```bash
# WARNING: removes containers, networks, AND named volumes.
# This destroys persisted PostgreSQL and Redis state.
docker compose -f docker-compose.prod.yml down -v
```

> **`stop` vs `down` semantics:** `docker compose stop` halts containers
> without removing them — they can be restarted with `docker compose start`.
> `docker compose down` stops and REMOVES containers and networks while
> preserving named volumes (unless `-v` is supplied). `docker compose down -v`
> additionally removes named volumes and is destructive to persisted
> database/Redis state.

---

## 13. Boundaries and escalation notes

- This runbook does NOT cover VPS hardening — that is a separate bounded
  action (Phase 7 contract §7)
- DNS mutation and TLS procurement are deployment-time actions, not
  repository tasks
- Live provider calls require separately authorized gates
- The embedding smoke harness (`make smoke-prepare`) runs offline by
  default; a live call requires `--live` flag AND
  `FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM=yes` (double barrier)
- If a deployment defect is found, create a separate bounded remediation
  package — do NOT repair defects inside a read-only verification action
- Escalate to the Product Owner for: FQDN changes, provider key rotation,
  security incidents, backup failure beyond retry window

---

## 14. Reference: Makefile commands

| Command | Purpose |
|---------|---------|
| `make dev` | Start all services in development mode |
| `make test` | Run all test suites |
| `make lint` | Run all linters |
| `make seed` | Seed the database with the golden dataset |
| `make demo-reset` | Reset the isolated disposable Demo environment |
| `make compose-validate` | Validate production Compose with template env |
| `make caddy-validate` | Validate production Caddyfile |
| `make config-validate` | Fail-closed production configuration validation |
| `make backup-smoke` | Run repo-owned backup/healthcheck test suites |
| `make smoke-prepare` | Offline embedding smoke preparation |
