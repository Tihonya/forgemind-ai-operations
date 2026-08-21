# ForgeMind — Production Deployment Runbook (WP-P7-02)

Repository-owned Release 1 deployment and security configuration.
This document is operational documentation directly owned by WP-P7-02.

Scope boundary: this runbook describes the repository configuration
and the manual first-deployment procedure. It does NOT perform any
deployment. VPS hardening, DNS, TLS procurement, staging/production
deployment, and live provider calls are separate bounded actions.

## 1. Topology

Host: single-purpose ForgeMind VPS, 2 vCPU, 8 GB RAM, 100 GB SSD, no GPU
(DEC-057, 2026-08-21; supersedes the historical 16 GB RAM / 200 GB storage
assumption of PD-1) + Docker Compose. No local LLM or embedding model runs
on the host — OpenRouter inference/embeddings are external (PD-3 / PD-3a),
so there is no local-model memory demand.

```
Internet
  │  HTTP/HTTPS only
  ▼
Caddy (automatic HTTPS, {$CADDY_DOMAIN}, TLS contact {$CADDY_EMAIL})
  ├── /health        → backend:8000  (flat status payload, no secrets)
  ├── /api/*         → backend:8000  (auth required; JWT from login)
  └── everything else → nginx (SPA)
                            └── /api → (same origin via Caddy)
Backend (uvicorn, `production` Dockerfile target, non-root appuser)
  ├── PostgreSQL + pgvector   (private `backend` network only)
  ├── Redis                   (private `backend` network only)
  └── ARQ worker              (heartbeat healthcheck in Redis)
```

Externally reachable: ONLY Caddy (80, 443, 443/udp).
No Docker socket mounts. No secrets inside any image or Compose file.

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

### 2.1 Credential password policy (URL-safe alphabet)

`POSTGRES_PASSWORD` and `REDIS_PASSWORD` are interpolated verbatim
into `DATABASE_URL` / `REDIS_URL`. Release 1 therefore requires the
password alphabet `A-Z a-z 0-9 . _ ~ -` (unreserved URL characters
only). Characters such as `@ : / # %` or spaces silently corrupt the
composed URL and are REJECTED by the production config validator
(exit non-zero). Generate with e.g.:

    openssl rand -base64 24 | tr -d '/+=' | cut -c1-32

The identifier part of the URL host/path must also avoid URL-reserved
characters; the fixed hostnames (`postgres`, `redis`) are safe.

## 3. Fail-closed configuration validation (REQUIRED before deploy)

```bash
# inside the backend container (or local venv with the same env vars)
python -m app.ops.validate_config
```

Exit code 0 = every Release 1 rule passes. Any single error → non-zero
and the deployment must not proceed. The report never prints secret
values (set/not-set only).

The backend container environment includes CADDY_DOMAIN/CADDY_EMAIL,
so the documented in-container invocation in the deploy directory
works as written (no extra host-side variables needed):

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.ops.validate_config
```

The same command runs identically in the production and staging
containers (settings/validator read the same typed environment).

Enforced rules include:
- ENVIRONMENT=production; SECRET_KEY at least 32 chars and NOT the
  development default and NOT any template placeholder;
- explicit DATABASE_URL / REDIS_URL (no placeholders; URL-safe
  credential alphabet per §2.1);
- DISTRIBUTED_RATE_LIMIT_ENABLED=true + RATE_LIMIT_DEGRADED_MODE=fail_closed;
- chat = OpenRouter only (`CHAT_PROVIDER_MODE=openrouter`,
  `OPENROUTER_CHAT_MODEL=qwen/qwen3.7-flash`, json_object, no
  fallback), OPENROUTER_API_KEY explicitly set (no implicit reuse);
- embeddings = `EMBEDDING_PROVIDER=openai`,
  `OPENAI_API_BASE=https://openrouter.ai/api/v1`,
  `OPENAI_EMBEDDING_MODEL=openai/text-embedding-3-small`,
  `EMBEDDING_DIMENSIONS=1536`, OPENAI_API_KEY = OpenRouter key (PD-3a);
- CADDY_DOMAIN + CADDY_EMAIL explicitly supplied through the typed
  settings channel (template placeholders rejected);
- CORS_ORIGINS must not contain template placeholders.

### 3.1 Placeholder rejection (templates and validator share one vocabulary)

The validator rejects any value matching the repository's own template
conventions: `REPLACE_WITH_*`, `replace-with-*`, `REPLACE_*`,
`REPLACE`-family case variants, `changeme`/`change_me`,
`your-*` attribution tokens, `example.com`-class FQDNs, and
`localhost`. Filling only part of the template and running the
validator CANNOT pass: un-filled placeholders produce findings, a
VERDICT: FAIL, and a non-zero exit. Unit tests load the template file
literally, so validator and template cannot drift.

## 4. Distributed rate limiting (production-safe)

The Redis-backed limiter (`backend/app/core/rate_limit.py`) shares one
state across ALL backend/worker processes:

- HTTP request budget: `RATE_LIMIT_PER_MINUTE` **per client address**,
  enforced by the ASGI middleware in staging/production; 429 with
  correlation ID on rejection.

  Client identification: trusted `X-Forwarded-For` from Caddy (sole
  public client; spoofed values dropped), then the transport peer,
  then a shared `client:anonymous` bucket. Every identifier is
  canonicalized into a bounded Redis-safe token (strict IP normalize;
  otherwise a truncated SHA-256 digest). Distinct clients consume
  distinct budgets; the same client shares ONE budget across every
  worker process. There is NO global HTTP ceiling — the per-client
  budget is the whole story.

- AI provider budget: `AI_RATE_LIMIT_PER_MINUTE` shared across
  processes at the provider boundary (scope `ai-provider`) — a
  SEPARATE budget from the HTTP per-client budget.

- Redis outage → `fail_closed` rejects ordinary requests with 429
  (never silently unlimited). `fail_open` exists only as an explicit
  operator choice.

- `/health` exemption: `/health` (exact match) never consumes a
  client budget and stays reachable during limiter Redis outages, so
  monitoring remains observable during exactly the incidents that
  matter. During an outage, /health reports `redis: error: …` in its
  payload (its own dependency check) while ordinary routes return 429.
  The exemption cannot be abused on other routes (exact `/health`
  path only).

Known behavior (fixed window): at a window boundary a client can
consume up to ~2× the configured budget in a single straddling burst.
This is a standard fixed-window property and accepted for Release 1.

## 5. Deploy (manual, checklist-driven — PD-9; Model C — DEC-058)

Primer: the authoritative Release 1 procedure lives in
`docs/operations/release_1_runbook.md` §3/§5. `make deploy` is
INTENTIONALLY DISABLED (fail-closed, WP-P7-CORR-01) and refuses to start
any Compose stack; a one-command production deploy shortcut does not exist.

Release 1 uses the single-VPS MODEL C flow (DEC-058): disposable staging →
verification → staging teardown → promotion of the same SHA and the same
locally built verified application images → independent production
verification. Application images are built exactly ONCE for the candidate
SHA, SERIALIZED (one service at a time; never run backend/worker/frontend
builds concurrently on the 2 vCPU / 8 GB host). No rebuild and no pull may
occur between successful staging verification and production promotion.

The Model C candidate artifact identity is: repository SHA + build-time
input values + verified application image IDs. The Git SHA alone does not
identify a rebuild with changed build args.

**Production promotion start (after staging verification + teardown)** —
the same exact SHA S and the SAME retained verified images; fail-closed
against accidental rebuild or pull:

```bash
docker compose -f docker-compose.prod.yml up -d --no-build --pull never
docker compose -f docker-compose.prod.yml exec backend python -m alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend python -m app.seed.generator.main
curl -f https://<FQDN>/health   # expect JSON, status healthy/degraded
```

`--no-build` and `--pull never` are both supported options of the projected
Docker Compose v2 tooling. Since both Compose files remain built on that
source state with no further `--build`, changes in mutable base tags do not
enter production before `--no-build`/`--pull never` forecloses them.

All commands run from the deployment directory with `.env` present, after
`git rev-parse HEAD` == S has been verified. Caddy obtains the certificate
automatically after the first successful deployment (automatic HTTPS; no
manual cert handling).

The production `CADDY_DOMAIN` / `CADDY_EMAIL` / secret values may differ
from the staging ones — those are GENUINELY RUNTIME inputs, not image
content. BUILD-TIME inputs MUST NOT differ: `VITE_API_BASE_URL` is
compiled into the frontend image (frontend Dockerfile `ARG`/`ENV` → Vite
build; consumed as `import.meta.env.VITE_API_BASE_URL` in
`frontend/src/lib/api.ts`; nginx performs no runtime substitution) and is
recorded in the staging evidence boundary, then re-verified at promotion.
New production runtime data may be created at promotion time.

## 5.1 Host resource discipline (DEC-057 / DEC-058)

- 2 GB host swap is the intended host safety cushion for the transient
  build peaks (DEC-057, 2026-08-21: required/recommended for Release 1
  deployment) and is created during the PRE-STAGING VPS SECURITY HARDENING
  operational action (`vm.swappiness` target approximately 10–30 so
  PostgreSQL/Redis stay in RAM). Swap is an OPERATOR/HARDENING action —
  Docker Compose does NOT create it, and no repository task creates it.
- Evidence of staging verification records the swap presence/size as part
  of the deployment environment (see the RESOURCE PRECHECK in the runbook).
  Host resource values are operational deployment gates, not immutable
  application-artifact identity — the promotion boundary's immutable
  identity is the candidate SHA + build-time inputs + application image
  IDs; host values may be rechecked at promotion where relevant but are
  not required to remain numerically unchanged.
- Builds are SERIALIZED on this host (one application image at a time).
- Backend runs 2 Uvicorn workers (one per 2 vCPU; `infra/docker/backend.dockerfile`
  production stage). The development-stage command is unchanged.
- Redis: bounded `--maxmemory 128mb --maxmemory-policy noeviction`
  (fail-closed: when the bound is hit, writes are refused rather than
  unbounded host-memory growth).
- No general Docker memory-limit architecture is required on the
  single-purpose host.

## 5.2 Build-cache / disk hygiene guidance

100 GB SSD is comfortable for Release 1; the realistic runtime/storage
footprint is far below the disk size. Build cache and old image generations
must not grow forever, so the operator MAY perform bounded, low-frequency
cleanup (e.g. `docker builder prune` or equivalent) — but ONLY after
confirming that no verified image still needed for promotion or rollback
will be deleted (check image IDs against the staging verification evidence
first). This is operator maintenance, not an automatic destructive cron;
no prune command may silently delete the currently verified promotion
images without an identity check.

## 6. Backups (PD-8)

Daily pg_dump with 7-day retention via the compose `backup` profile:

```bash
docker compose -f docker-compose.prod.yml --profile backup up -d
```

The scheduled cycle runs `scripts/backup-cycle.sh` — the ONE
authoritative scheduled-backup implementation. Hard guarantees:

- failed `pg_dump` STOPS the cycle: retention never runs after a
  failed dump (so a string of failure days can never prune the last
  good backups);
- dumps are staged as `*.dump.part` and atomically renamed only on
  success — a partial dump can never be mistaken for a valid backup;
- successful dumps are mode `0600`;
- success is logged only after actual success;
- failures are VISIBLE: `./backups/last_backup_state` records
  `ok <epoch>` / `failed <epoch>`, and the backup service healthcheck
  reports unhealthy while the last cycle failed (no silent 24-hour
  healthy-looking sleep); after a failure the cycle retries after
  RETRY_SLEEP (1 hour) without touching retention.
- Scheduling is INTERNAL to `scripts/backup-cycle.sh`: a successful
  cycle sleeps SLEEP_SECONDS (86400 s) and a failed cycle sleeps
  RETRY_SLEEP (3600 s) inside the same container process. Because the
  process remains running, ordinary daily scheduling does NOT depend
  on the Docker restart policy.
- The committed production service leaves `CYCLE_ONCE` UNSET.
  Docker's `restart: unless-stopped` restarts the container after
  BOTH a zero and a non-zero exit; therefore `CYCLE_ONCE=1` is
  reserved for tests, manual one-shot invocation, and controlled
  external execution ONLY, and MUST NOT be enabled on the Compose
  backup daemon while `restart: unless-stopped` remains configured
  (a bounded cycle that exits cleanly would otherwise restart and
  re-dump in a tight backup-storm loop). The restart policy engages
  only when the daemon process dies unexpectedly (e.g. kill/OOM).
- The state marker contains `ok`/`failed` + an epoch timestamp only —
  non-secret. Its file mode intentionally follows the container umask
  (no 0600 requirement; it carries no secrets).

Backups run as the postgres image user (root inside that container);
dumps land root-owned with mode 0600 on the host `./backups`
directory. If the operator wants non-root ownership, apply the
documented `user:` override inside a locally modified compose file —
never in the committed template. Off-host replication is an operator
responsibility.

Manual operations wrapper (`scripts/backup.sh`), sharing the same
retention primitive (`scripts/backup-prune.sh`):

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
  the backup state marker `/backups/last_backup_state` (ok/failed),
  and the checklist-driven deployment verification.

## 8. Health behavior

- backend → `curl http://localhost:8000/health` (real dependency
  checks; HTTP 200 with a degraded summary even when a dependency is
  down — the payload distinguishes healthy/degraded/unhealthy and never
  exposes secrets or URLs). `/health` is exempt from the per-client
  rate-limit budget (§4), so it stays observable while the limiter's
  Redis is unavailable.
- worker → `/usr/local/bin/worker-healthcheck` reads the ARQ heartbeat
  key from Redis (well-formed value = alive; absent/malformed = start
  or stopped; redis failure = unhealthy). Staleness note: ARQ 0.28.0
  writes the heartbeat at most once per hour (TTL ≈ 3601 s), so a
  worker that dies immediately after a heartbeat write can appear
  healthy for up to ~1 hour. This is inherent ARQ semantics and an
  accepted Release 1 monitoring window; if stricter freshness is
  needed later, lower the ARQ `health_check_interval` in WorkerSettings.
- frontend → nginx static health.
- postgres/redis → native `pg_isready` / `redis-cli ping` probes.
- backup → state-marker healthcheck (§6: unhealthy while the last
  cycle failed).

## 9. Embedding smoke — preparation + boundaries

The smoke harness (`backend/app/ops/embedding_smoke.py`) runs offline
by default: it verifies the PD-3a configuration contract and vector
check logic, reports live-only items as `not_run`, and NEVER calls a
provider. A live call requires a separately authorized gate — the
harness itself refuses unless both the `--live` flag AND
`FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM=yes` are present (double
barrier against accidental credit consumption).

Evidence verdicts (strict gate semantics):
- PASS — every mandatory check executed and passed;
- FAIL — any executed check failed;
- PREPARATION_INCOMPLETE — one or more mandatory checks not executed
  (the normal offline state).

CLI exit codes: 0 = PASS, 1 = FAIL, 2 = PREPARATION_INCOMPLETE,
3 = live authorization refused. Offline runs in their normal state
exit 2 (non-zero), so a strict verification gate can never mistake an
incomplete offline bundle for a passed live gate. The same contract
applies to an authorized `--live` run: WP-P7-02 performs no live
provider execution, so even with both authorization barriers
satisfied the evidence remains PREPARATION_INCOMPLETE and the CLI
exits 2 (never 0) — exit 0 is reachable only from a genuinely
complete PASS, which only the separately authorized live gate can
produce.

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
- Rollback and emergency-access procedures — owed before the staging
  action (WP-P7-06), not part of this configuration WP.
- DNS mutation, real TLS/Let's Encrypt interaction on a real host.
- Staging/production deployment execution.
- Live OpenRouter/OpenAI/Groq calls.
- Demo reset (WP-P7-03), login demo UX (WP-P7-04), README/license
  reconciliation (WP-P7-05).
