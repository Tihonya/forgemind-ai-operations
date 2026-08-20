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

### 9.1 Start the scheduled backup daemon

```bash
docker compose -f docker-compose.prod.yml --profile backup up -d
```

Daily `pg_dump` with 7-day retention via `scripts/backup-cycle.sh`.
Backups land in `./backups` on the host (bind mount). The operator owns
off-host replication.

### 9.2 Manual backup operations

```bash
# Create a backup:
bash scripts/backup.sh backup ./backups

# Prune old backups (keep 7 days):
bash scripts/backup.sh prune ./backups 7
```

### 9.3 Failure visibility

- Failed `pg_dump` stops the cycle — retention never runs after a failed dump
- `./backups/last_backup_state` records `ok <epoch>` / `failed <epoch>`
- The backup service healthcheck reports unhealthy while the last cycle failed
- After a failure, the cycle retries after 1 hour without touching retention

See `docs/infra-production.md` §6 for full backup guarantees.

---

## 10. Restore and rehearsal

```bash
# Restore from a specific dump:
bash scripts/backup.sh restore ./backups/forgemind-XXXX.dump forgemind

# Rehearse: restore newest dump into a throwaway database, verify, drop:
bash scripts/backup.sh rehearse ./backups forgemind
```

The rehearsal restores the newest dump into a throwaway database, verifies
the restored table count, and drops the scratch database. It never touches
the live database. Restore rehearsal MUST be performed and validated before
production (Phase 7 staging-entry gates).

---

## 11. Rollback and recovery

**Container rollback:**

```bash
# Stop all services:
docker compose -f docker-compose.prod.yml down

# Restart from a previous image (if built):
docker compose -f docker-compose.prod.yml up -d
```

**Database rollback:**

```bash
# Stop the backend and worker first:
docker compose -f docker-compose.prod.yml stop backend worker

# Restore from a backup dump:
bash scripts/backup.sh restore ./backups/forgemind-XXXX.dump forgemind

# Restart services:
docker compose -f docker-compose.prod.yml up -d
```

**Emergency shutdown:**

```bash
docker compose -f docker-compose.prod.yml down
```

**Demo recovery:** The demo is disposable — run `make demo-reset` again.
No partial rollback is attempted.

---

## 12. Shutdown

```bash
# Stop all production services (containers stay, volumes preserved):
docker compose -f docker-compose.prod.yml down

# Stop and remove volumes (DESTRUCTIVE — use with caution):
docker compose -f docker-compose.prod.yml down -v
```

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
