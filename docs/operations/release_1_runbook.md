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

- Single-purpose ForgeMind VPS: 2 vCPU, 8 GB RAM, 100 GB SSD, no GPU
  (DEC-057, 2026-08-21; supersedes the historical 16 GB RAM / 200 GB
  storage assumption of PD-1). No local LLM or embedding model runs on
  the host — OpenRouter inference/embeddings are external (PD-3 / PD-3a).
- 2 GB host swap created during the PRE-STAGING VPS SECURITY HARDENING
  operational action (`vm.swappiness` approximately 10–30). Swap is an
  operator/hardening action — Docker Compose does not create it, and no
  repository task creates it.
- Docker and Docker Compose installed on the deployment host
- Production FQDN and TLS contact email (Product Owner deployment-time input)
- OpenRouter account with API key (used for both chat and embeddings)
- OpenRouter provider-side hard budget/cap expected by PD-4 confirmed
  administratively BEFORE staging entry (external USD 5 account/billing
  control; the application does not enforce the monetary cap). If the cap
  cannot be confirmed later, staging entry remains blocked.
- All secrets prepared via `infra/prod.env.example` — see §2 below
- VPS security hardening completed and independently verified (separate
  bounded action; see Phase 7 contract §7)

### 1.1 Resource precheck (REQUIRED before any deployment action here)

On the deployment host, confirm before starting (all are deployment-time
verifications; this repository task executes NONE of them):

```bash
# 1. Free RAM
free -h

# 2. Swap presence and size (evidence records that swap exists)
swapon --show
grep -i swap /proc/meminfo

# 3. Free disk
df -h /

# 4. Exact repository SHA — must equal the candidate Release SHA S
git rev-parse HEAD

# 5. Docker / Compose available
docker --version
docker compose version
```

Also confirm `vm.swappiness` is within the ~10–30 target for evidence:

```bash
cat /proc/sys/vm/swappiness
```

Staging evidence records the confirmed values as deployment-environment
evidence. Host resource values (free RAM, swap presence/size, free disk,
swappiness) are operational deployment gates, NOT immutable application
artifact identity — the promotion pre-flight in §3.4 binds correctness to
the artifact identity (repository SHA S + build-time input values +
application image IDs). Relevant host values may be rechecked at promotion
where relevant, but they are not required to remain numerically unchanged.

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

## 3. Release 1 deployment model (Model C — DEC-058)

> This section documents the procedure. It must NOT be executed from
> this repository task. VPS deployment is a separate bounded action
> (WP-P7-06) and begins only after pre-staging VPS hardening, PO
> authorization, and the RESOURCE PRECHECK (§1.1) have passed.
> Direct `make deploy` is intentionally disabled (WP-P7-CORR-01).

Release 1 uses Model C on the single VPS (DEC-058, 2026-08-21): ONE
public ForgeMind stack exists on the host at a time; staging and
production cannot coexist on the current port topology (80/443/443-udp).
Application images are built ONCE for the candidate Release SHA S, staging
is verified against exactly S, staging is then torn down, and production
is started from the same SHA S with the SAME locally retained verified
images — never by rebuilding and never by pulling replacement images.

There is no GHCR/container-registry promotion step for Release 1
(PD-9 manual-first delivery stays in force).

### 3.1 STAGING BUILD (WP-P7-06)

```bash
# From the deployment directory on the VPS (with .env present):
git fetch origin
git checkout --detach S                # exact candidate Release SHA S
git rev-parse HEAD                     # record: MUST equal S

# Build ONCE, SERIALIZED (one service at a time). Never run these
# builds concurrently on the 2 vCPU / 8 GB host.
docker compose -f docker-compose.prod.yml build backend
docker compose -f docker-compose.prod.yml build worker
docker compose -f docker-compose.prod.yml build frontend

# Start the disposable staging stack:
docker compose -f docker-compose.prod.yml up -d

# Migrate + seed:
docker compose -f docker-compose.prod.yml exec backend python -m alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend python -m app.seed.generator.main

# Record the artifact identity into the staging evidence:
git rev-parse HEAD                    # candidate SHA S (record: MUST equal S)

# Build-time input used to build the frontend image (non-secret; the
# Release 1 expected/default value is /api/v1). The value is compiled
# into the frontend image — it is part of the artifact identity boundary.
# If the .env line is absent, the Compose build default
# ${VITE_API_BASE_URL:-/api/v1} applies — record `/api/v1` in that case.
grep '^VITE_API_BASE_URL=' .env      # record the exact build value

# Application image identities. docker-compose.prod.yml declares
# `name: forgemind`, so Docker Compose v2 resolves the three build-derived
# application image tags deterministically as:
docker image inspect --format '{{.Id}}' forgemind-backend    # backend image ID
docker image inspect --format '{{.Id}}' forgemind-worker     # worker image ID
docker image inspect --format '{{.Id}}' forgemind-frontend   # frontend image ID

# Full Compose-resolved image inventory (ADDITIONAL cheap evidence;
# pure non-mutating render):
docker compose -f docker-compose.prod.yml config --images
```

The application image references above are exact for this repository: the
prod Compose file has the explicit top-level `name: forgemind`, so there is
no filename-derived default and no operator guessing — the same three
references apply on any host.

### 3.2 STAGING VERIFICATION (WP-P7-07)

Read-only. Runs AT-001, AT-002, AT-014, the Golden Scenario walkthrough,
health verification, and the reboot test against staging, bound to the
exact SHA S. NEVER repair staging defects during this verification — a
defect means solving separately and re-verifying against a new candidate
SHA S. The evidence records/validates the exact SHA S, the build-time
input values (VITE_API_BASE_URL), and the image identities recorded in §3.1.

### 3.3 STAGING TEARDOWN (only after WP-P7-07 PASS)

```bash
# Destroy the staging runtime/state (disposable model). Verified
# application images are RETAINED.
docker compose -f docker-compose.prod.yml down --volumes
```

- Do NOT rebuild. Do NOT pull new images. Do NOT prune the retained
  verified images.
- Staging teardown is NOT a rollback of staging verification evidence:
  the evidence stays valid because the promoted production artifact is
  the same SHA with the same verified image identities.

### 3.4 PRODUCTION PROMOTION (WP-P7-08)

```bash
# From the deployment directory on the VPS (with the final .env present):
git fetch origin
git checkout --detach S                # the SAME SHA S
git rev-parse HEAD                     # FAIL CLOSED if this != S

# Build-time input check — the intended production VITE_API_BASE_URL must
# equal the staging-recorded build value (FAIL CLOSED on any difference;
# it is compiled into the frontend image):
grep '^VITE_API_BASE_URL=' .env      # compare to staging evidence

# Resolve the Compose image inventory (pure non-mutating render):
docker compose -f docker-compose.prod.yml config --images

# Verify required application image IDs equal the staging evidence (FAIL
# CLOSED on any mismatch, absence, or accidental rebuild after staging
# verification). The references are exact for this repository:
docker image inspect --format '{{.Id}}' forgemind-backend
docker image inspect --format '{{.Id}}' forgemind-worker
docker image inspect --format '{{.Id}}' forgemind-frontend

# Start production with NO rebuild and NO pull:
docker compose -f docker-compose.prod.yml up -d --no-build --pull never

# Migrate + seed (new production runtime data may be created):
docker compose -f docker-compose.prod.yml exec backend python -m alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend python -m app.seed.generator.main

# Health:
curl -f https://<FQDN>/health
```

Production RUNTIME configuration, the final FQDN (`CADDY_DOMAIN`), and
production secrets MAY differ from staging — the FQDN/TLS contact,
database/Redis credentials, and other container environment values that
are NOT compiled into an application image. BUILD-TIME inputs MUST NOT
differ: `VITE_API_BASE_URL` is compiled into the frontend image during
`npm run build` (frontend Dockerfile `ARG`/`ENV` → Vite statically
substitutes `import.meta.env.VITE_API_BASE_URL`; nginx performs NO runtime
substitution). Changing a build-time input after staging verification
REQUIRES a rebuild, and the rebuilt application image set is a NEW
candidate artifact set that must repeat the staging deployment and
verification cycle before production promotion.

Caddy obtains the TLS certificate automatically after the first
successful start (automatic HTTPS; no manual cert handling).

**FAIL-CLOSED conditions** — if ANY of the following occur, DO NOT deploy
production from the changed artifact; return to staging verification with
a new candidate evidence boundary:

- SHA differs from the staging-verified S;
- a build-time input value differs from the staging evidence (currently:
  VITE_API_BASE_URL);
- an application image ID differs from the staging evidence;
- a verified image is missing;
- an operator accidentally rebuilt after staging verification.

The Model C candidate artifact identity is: repository SHA + build-time
input values + verified application image IDs. The Git SHA alone does not
identify a rebuild with changed build args — the SHA may stay the same
while the image IDs change.

**WP-P7-09 remains mandatory after production deployment** — production is
not verified merely because staging passed.

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
# Compose network. The postgres service container sets
# POSTGRES_USER, POSTGRES_DB, and POSTGRES_PASSWORD — but NOT
# PGPASSWORD. PGPASSWORD is set inline from POSTGRES_PASSWORD for
# the individual pg_dump process so the client authenticates
# explicitly (no reliance on implicit local-trust auth). The dump
# is written to stdout and redirected to the host file.
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
  --format=custom' \
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
#    database environment and network are available. PGPASSWORD is
#    set inline from POSTGRES_PASSWORD for explicit authentication:
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
  --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
  --no-owner --no-privileges --clean' \
  < "./backups/forgemind-XXXX.dump"

# 3. Restart services:
docker compose -f docker-compose.prod.yml up -d
```

> **Warning:** Restore is destructive — `--clean` drops existing
> database objects before recreating them from the dump. Verify the
> target database name and the dump file before proceeding.

**Rehearsal (throwaway database — never touches live DB):**

The rehearsal restores a production dump into a throwaway scratch
database, verifies the contents, then drops the scratch database. It
is a host-shell procedure: `SCRATCH_DB` is a host-shell variable that
must be explicitly passed into the postgres container via
`docker compose exec -e`. The same `SCRATCH_DB` value is used for
createdb, pg_restore, psql verification, and dropdb — one identity,
established once.

```bash
# ── Rehearsal procedure (run on the deployment host) ──────────────
set -euo pipefail

# 1. Identify the newest backup dump using a Bash-native loop (no ls
#    pipeline) so that zero matching files reach the explicit guard
#    instead of triggering set -e via pipefail. Fail immediately if
#    none exists — do NOT proceed with an empty NEWEST variable.
NEWEST=""
for candidate in ./backups/forgemind-*.dump; do
  [[ -f "${candidate}" ]] || continue
  if [[ -z "${NEWEST}" || "${candidate}" -nt "${NEWEST}" ]]; then
    NEWEST="${candidate}"
  fi
done
if [[ -z "${NEWEST}" ]]; then
  echo "ERROR: no backup dump found in ./backups/ — cannot rehearse." >&2
  exit 1
fi
echo "Rehearsing with dump: ${NEWEST}"

# 2. Establish one unique scratch database identity on the HOST.
#    The rehearsal-only prefix prevents accidental production targeting.
SCRATCH_DB="forgemind_rehearsal_$(date -u +%Y%m%d_%H%M%S)"

# 3. Validate the scratch identity by construction — refuse anything
#    that does not carry the rehearsal-only prefix or is empty.
case "${SCRATCH_DB}" in
  forgemind_rehearsal_*) ;;
  *) echo "ERROR: SCRATCH_DB has unexpected form: '${SCRATCH_DB}'" >&2; exit 1 ;;
esac

# 4. Define a fail-safe cleanup function. Only a rehearsal-prefixed
#    database is ever dropped. --if-exists tolerates the case where
#    the scratch DB was never created (e.g. createdb failed).
cleanup_rehearsal() {
  echo "Cleaning up scratch database: ${SCRATCH_DB}"
  docker compose -f docker-compose.prod.yml exec -T \
    -e SCRATCH_DB="${SCRATCH_DB}" \
    postgres sh -lc \
    'PGPASSWORD="$POSTGRES_PASSWORD" dropdb --if-exists \
     --username="${POSTGRES_USER}" "${SCRATCH_DB}"' \
    || echo "WARNING: cleanup failed for ${SCRATCH_DB}" >&2
}

# 5. Arm the cleanup trap — if anything fails below, the scratch DB
#    is still removed.
trap cleanup_rehearsal EXIT

# 6. Create the scratch database. SCRATCH_DB is passed into the
#    container via -e so the inner shell sees it.
docker compose -f docker-compose.prod.yml exec -T \
  -e SCRATCH_DB="${SCRATCH_DB}" \
  postgres sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" createdb \
   --username="${POSTGRES_USER}" "${SCRATCH_DB}"'

# 7. Restore the dump into EXACTLY the scratch database. The dump
#    file is fed from the host via stdin redirect.
docker compose -f docker-compose.prod.yml exec -T \
  -e SCRATCH_DB="${SCRATCH_DB}" \
  postgres sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
   --username="${POSTGRES_USER}" --dbname="${SCRATCH_DB}" \
   --no-owner --no-privileges' \
  < "${NEWEST}"

# 8. Verify the restored table count. The SQL string is quoted so
#    that pg_catalog and information_schema are excluded.
docker compose -f docker-compose.prod.yml exec -T \
  -e SCRATCH_DB="${SCRATCH_DB}" \
  postgres sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql \
   --username="${POSTGRES_USER}" --dbname="${SCRATCH_DB}" -tAc \
   "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('"'"'pg_catalog'"'"','"'"'information_schema'"'"');"'

# 9. Drop the scratch database — same identity, explicit cleanup.
docker compose -f docker-compose.prod.yml exec -T \
  -e SCRATCH_DB="${SCRATCH_DB}" \
  postgres sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" dropdb --if-exists \
   --username="${POSTGRES_USER}" "${SCRATCH_DB}"'

# 10. Disarm the trap — cleanup is done, no further action needed.
trap - EXIT
echo "Rehearsal complete: ${SCRATCH_DB} created, restored, verified, and dropped."
# ── End rehearsal procedure ───────────────────────────────────────
```

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

> **Promotion-boundary note (DEC-058, 2026-08-21):** the no-rebuild /
> no-pull promotion rule in §3.4 governs ONLY the staging-verified →
> production-promotion boundary. A rollback below is an emergency
> recovery action to a KNOWN-GOOD commit/artifact (per the rollback
> procedure), and is performed only when the running production artifact
> is defective. A rollback does NOT authorize skipping §3.4 for a normal
> promotion, and what a rollback rebuilds must itself be a previously
> verified known-good state.

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
- Off-host backup: no destination has been selected yet. Before production
  closure, the operator/Product Owner must either configure at least one
  off-host backup copy or record an explicitly accepted temporary Release
  1 limitation (hardening contract). This remains a pre-production
  operator decision/gate — this runbook does not select a destination and
  adds no S3/rclone/scp automation.
- Live provider calls require separately authorized gates
- The embedding smoke harness (`make smoke-prepare`) runs offline by
  default; a live call requires `--live` flag AND
  `FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM=yes` (double barrier)
- `make deploy` is intentionally disabled (fails with a pointer to this
  runbook); staging/production deployment is checklist-controlled (Model C,
  §3) — there is no one-command deploy shortcut
- If a deployment defect is found, create a separate bounded remediation
  package — do NOT repair defects inside a read-only verification action
- Escalate to the Product Owner for: FQDN changes, provider key rotation,
  security incidents, backup failure beyond retry window

---

## 14. Operator maintenance notes (build cache / disk)

The host has 100 GB SSD — comfortable for Release 1; the realistic
runtime/storage footprint is far below the disk size. Build cache and old
image generations must not grow forever. The operator MAY perform bounded,
low-frequency cleanup (e.g. `docker builder prune` or equivalent) —
quarterly or occasional, NOT an aggressive automatic cron — and only after
confirming (against the staging verification evidence) that no verified
image still needed for promotion or rollback will be deleted. No prune
command may silently delete the currently verified promotion images
without an identity check.

## 15. Reference: Makefile commands

| Command | Purpose |
|---------|---------|
| `make dev` | Start all services in development mode |
| `make test` | Run all test suites |
| `make lint` | Run all linters |
| `make seed` | Seed the database with the golden dataset |
| `make demo-reset` | Reset the isolated disposable Demo environment |
| `make deploy` | REFUSES direct deployment (disabled) — follow this runbook §3 |
| `make compose-validate` | Validate production Compose with template env |
| `make caddy-validate` | Validate production Caddyfile |
| `make config-validate` | Fail-closed production configuration validation |
| `make backup-smoke` | Run repo-owned backup/healthcheck test suites |
| `make smoke-prepare` | Offline embedding smoke preparation |
