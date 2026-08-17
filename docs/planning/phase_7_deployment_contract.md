# Phase 7 — Release 1 Deployment Contract and Controlled Decomposition

**Work package:** WP-P7-01
**Type:** Documentation-only contract (no application, deployment, infrastructure, or localization changes)
**Status:** PROPOSED — AWAITING INDEPENDENT DOCUMENTATION REVIEW
**Baseline:** origin/main @ `8e018b2080917c50b5641abbdbd7be0407493677` (PR #111 merge commit)
**Date:** 2026-08-17
**Decision:** DEC-054 (Product Owner, 2026-08-17)

**Authoritative design inputs:**

1. `/tmp/release-1-phase-7-readiness-reconnaissance-and-deployment-plan.md` — readiness reconnaissance and deployment plan.
2. `/tmp/release-1-phase-7-readiness-design-independent-review.md` — independent readiness-design review. Verdict: INDEPENDENT PHASE 7 READINESS DESIGN REVIEW PASSED WITH REQUIRED CORRECTIONS — WP-P7-01 MUST INCORPORATE THE CORRECTED DECISIONS AND LIFECYCLE DECOMPOSITION.
3. `/tmp/release-1-phase-7-pd3a-embedding-path-technical-spike.md` — PD-3A embedding-path technical spike. Declared verdict: PD-3A EMBEDDING PATH DECISION READY — PRODUCTION EMBEDDING ARCHITECTURE MAY BE RECORDED IN WP-P7-01.
4. `/tmp/release-1-phase-7-pd3a-embedding-path-independent-review.md` (SHA-256 `d437f79c0a5661557db78d826b666a6402db6c114e9932d6b61bfdb4c6ee4aae`) — independent PD-3A review. Verdict: INDEPENDENT PD-3A REVIEW PASSED — FINAL EMBEDDING DECISION MAY BE RECORDED IN WP-P7-01.

The spike contains two known non-authoritative defects that this contract does NOT reproduce as fact:
- IR-1: the spike's executive section incorrectly described the OpenRouter model-name convention as an "undocumented assumption about model-name forwarding." OpenRouter's `dimensions` parameter and `openai/text-embedding-3-small` model name are officially documented. The OpenRouter path is fully documented.
- IR-2: the spike incorrectly claimed the protected audit file did not exist anywhere. The file exists as an untracked artifact in a separate worktree with the exact expected identity.

---

## 1. Purpose and Scope

This document is the authoritative Release 1 / Phase 7 deployment contract. It records the accepted Product Owner deployment decisions (PD-1 through PD-11), incorporates all required corrections from the independent readiness-design review, records the independently accepted PD-3a embedding architecture, defines explicit Release 1 scope and non-scope, defines the deployment architecture and safety boundaries, decomposes all remaining work into lifecycle-safe bounded packages, and prevents implementation, review, remediation, merge, deployment, evidence review, Product Owner acceptance, GitHub Release publication, and lifecycle closure from being combined improperly.

This contract keeps Release 1 NOT READY / NOT DEPLOYED until all required gates pass.

### 1.1 Release 1 scope

- Public HTTPS deployment of the existing ForgeMind AI Operations MVP on a single Hostinger VPS.
- One complete vertical scenario: Production Plan Supply Risk Review (Golden Scenario).
- English-first UI and operational README.
- Authentication required; bounded demo credentials displayed on the login page.
- Live RAG with grounded citations.
- Live chat (OpenRouter) and live embedding (OpenRouter routing to OpenAI) providers.
- Demo reset capability.
- Daily PostgreSQL backup with 7-day retention.
- Manual first deployment, checklist-driven.
- Docker logs + backend `/health` + bounded deployment verification for monitoring.

### 1.2 Release 1 non-scope

- Ukrainian localization (deferred until after deployment stabilization; future target is an EN / UA language switch).
- CI/CD deployment automation (deferred until after first stable deployment).
- Full observability platform (logs, metrics, tracing suite).
- General enterprise AI platform expansion.
- Agent-loop runtime (not a Release 1 dependency or blocker).
- SP-0B runtime migration manifest (not authorized).
- Bilingual CV/portfolio presentation (Phase 8 or post-stabilization unless separately authorized).
- Local embedding service (Option B from the spike — not the primary or fallback path).
- Degraded mode without live RAG (Option D — rejected for violating AT-006 and the Golden Scenario).

---

## 2. Authoritative Baseline Lifecycle State

| Item | State |
|------|-------|
| Phase 6 | CLOSED / ACCEPTED (DEC-053, 2026-08-16) |
| AT-003 through AT-013 | PASS |
| AT-001, AT-002, AT-014 | REQUIRES DEPLOYMENT/ENVIRONMENT VERIFICATION |
| AT-015 | NOT IMPLEMENTED |
| DEC-053 | Accepted (latest accepted decision at baseline) |
| Phase 7 implementation | NOT STARTED |
| Deployment | NOT STARTED |
| Release 1 | NOT READY / NOT DEPLOYED |

No later Phase 7 branch, PR, merge, tag, release, or lifecycle transition exists at the baseline.

### 2.1 Intended post-merge state (prospective)

If and only if this PR is merged and post-merge verified:

- Phase 7: IN PROGRESS — PLANNING/IMPLEMENTATION AUTHORIZED
- Deployment execution: NOT STARTED
- Staging: NOT STARTED
- Production: NOT STARTED
- Release 1: NOT READY / NOT DEPLOYED

Until this PR is merged and post-merge verified, GitHub main remains authoritative with Phase 7 NOT STARTED.

No deployment-gated acceptance test is marked PASS. Phase 7 is not closed. No GitHub Release or tag is created.

---

## 3. Product Owner Deployment Decisions

The Product Owner has authorized proceeding toward Release 1 and has selected the following direction. Each decision is recorded as ACCEPTED.

### PD-1 — Deployment topology: ACCEPTED

Single Hostinger VPS using Docker Compose.

Planned service topology:

- Caddy reverse proxy with automatic HTTPS;
- frontend served through nginx;
- FastAPI backend;
- ARQ worker;
- PostgreSQL with pgvector;
- Redis.

The VPS target has 16 GB RAM and 200 GB storage.

The stack has NOT already been deployed. Deployment has not begun.

### PD-2 — Domain and TLS: ACCEPTED WITH DEPLOYMENT-TIME INPUT

- Caddy automatic HTTPS is selected.
- Exact domain/FQDN remains a required deployment-time Product Owner input.
- A suitable domain is NOT claimed to already exist.
- DNS mutation is NOT authorized by WP-P7-01.

### PD-3 — Chat provider: ACCEPTED

Initial Release 1 chat configuration:

- provider: OpenRouter only;
- model: `qwen/qwen3.7-flash`;
- response mode: `json_object`;
- automatic provider fallback: disabled.

This reflects the accepted DEC-049 evidence: `no_fallback=true`, `no_groq_request=true`. A Groq-first chain is NOT recorded as the initial production configuration. The Groq-first path was never live-verified; automatic fallback is deferred until Groq is separately live-verified and accepted.

### PD-3a — Embedding provider: ACCEPTED AFTER TECHNICAL SPIKE AND INDEPENDENT REVIEW

Primary Release 1 path (Option C from the independent review):

- provider endpoint: OpenRouter embeddings;
- client implementation: existing `OpenAIEmbeddingProvider`;
- `EMBEDDING_PROVIDER=openai`;
- `OPENAI_API_BASE=https://openrouter.ai/api/v1`;
- `OPENAI_EMBEDDING_MODEL=openai/text-embedding-3-small`;
- `EMBEDDING_DIMENSIONS=1536`;
- `OPENAI_API_KEY` contains an OpenRouter key supplied through the production secret workflow.

Important wording:

- the config field is named `OPENAI_API_KEY`, but for the primary path its value comes from the existing OpenRouter account;
- the value is never included or requested in this contract;
- seed-time and runtime query embeddings must use the same endpoint, model, and dimension;
- the existing 1536-dimensional database contract remains unchanged;
- no migration or re-index is planned for this path;
- fake embeddings remain forbidden in staging/production;
- live RAG remains required.

Fallback (Option A — direct OpenAI):

Direct OpenAI `text-embedding-3-small`, 1536 dimensions, using the default OpenAI base URL and a real OpenAI key. The fallback is configuration-only but requires a separate provider account/key. It may be used only if the OpenRouter live embedding gate fails or the Product Owner explicitly changes the operational decision.

Explicitly rejected:

- "Pre-seed embeddings and remove the key" (the original PD-3a recommendation) is technically invalid. Query embeddings are generated live at workflow runtime (`vertical.py` line 410). Removing the key breaks every workflow run at `FAILED_RETRIEVAL`.
- Option D (degraded mode without live RAG) is rejected for violating AT-006 and the Golden Scenario.
- Option B (local embedding service) is not the primary or fallback path; it is a future optimization requiring a separate work package.

Mandatory future gate:

Before staging, WP-P7-02 must perform an explicitly authorized bounded live embedding smoke that verifies:

- authenticated OpenRouter embedding request;
- exact model identifier;
- exactly 1536 numeric dimensions;
- non-empty finite vector;
- deterministic repeated input;
- database insertion compatibility;
- Golden Dataset seeding;
- runtime retrieval with citations;
- seed/query provider consistency;
- fail-closed behavior for invalid credentials and provider failure;
- no secrets in logs or evidence.

This smoke is NOT executed in WP-P7-01.

### PD-4 — External provider budget: ACCEPTED

- USD 5 OpenRouter budget cap for initial Release 1 operation.
- This is an external account/billing control.
- The application does NOT enforce the monetary cap.

### PD-5 — Public access: ACCEPTED

- authentication remains required;
- the public portfolio deployment may display bounded demo credentials on the login page;
- no anonymous application access.

### PD-6 — Displayed demo roles: ACCEPTED WITH CORRECTION

Display exactly these demo accounts:

- `manager.demo`;
- `procurement.demo`;
- `auditor.demo`.

Do NOT display `admin.demo`.

Plaintext passwords are NOT placed in this planning contract or Decision Log.

The future login UX implementation (WP-P7-04) may obtain repository-owned demo credentials from the established seed/test contract, but must independently review their public-demo suitability before rendering them.

Why all three roles are needed:

- `manager.demo` (PRODUCTION_MANAGER) initiates the workflow and creates the approval request;
- `procurement.demo` (PROCUREMENT_SPECIALIST) performs the independent approval;
- `auditor.demo` (AUDITOR) inspects the audit trail;
- the auditor cannot approve;
- self-decision is forbidden (the approver must be a different identity from the requester; `manager.demo` cannot approve its own request).

### PD-7 — Demo reset: ACCEPTED

- manually triggered administrative reset for Release 1;
- synchronous and observable;
- preserve protected/audit history according to the approved reset contract;
- emit a reset audit record;
- never schedule an uncontrolled destructive reset;
- exact implementation belongs to WP-P7-03.

### PD-8 — Backup: ACCEPTED

- daily PostgreSQL `pg_dump`;
- 7-day retention;
- backup and restore must be documented and validated before production;
- no backup operation occurs in WP-P7-01.

### PD-9 — Delivery automation: ACCEPTED

- first deployment is manual and checklist-driven;
- CI/CD automation is deferred until after first stable deployment;
- existing CI gates remain applicable to repository changes.

### PD-10 — Initial monitoring: ACCEPTED

- Docker/container logs;
- backend `/health`;
- bounded deployment verification;
- no claim of a full observability platform.

### PD-11 — Language: ACCEPTED

- Release 1 UI and operational README are English-first;
- Ukrainian localization is explicitly deferred until after deployment stabilization;
- future target is an EN / UA language switch;
- localization must not block initial Release 1 deployment;
- bilingual CV/portfolio presentation belongs to post-stabilization or Phase 8 work unless separately authorized.

---

## 4. License and Documentation

Known WP-P7-05 correction (NOT performed in WP-P7-01 unless strictly required to link this contract):

- root `LICENSE` is Apache-2.0;
- stale README wording that says "Proprietary" must be corrected;
- Phase 6 feature descriptions in README must be reconciled (README currently lists Phase 6 features as "NOT IMPLEMENTED" despite Phase 6 being CLOSED/ACCEPTED);
- final documentation should be clear, visually pleasant, portfolio-ready, and honest;
- these edits are not performed in WP-P7-01.

---

## 5. Known Implementation Gaps

This contract truthfully lists the following known implementation gaps. Demo reset is NOT the only missing code artifact; rate limiting and login UX are additional required code changes.

1. Demo reset service/command is not implemented (`reset_service.py` does not exist; `scripts/reset.sh` and the Makefile guard for its absence).
2. General application rate limiting is not enforced (no rate-limiting middleware exists in the FastAPI app; `rate_limit_per_minute` is never read by any application code).
3. Existing AI rate limiting is not distributed across multiple workers (the per-instance sliding-window limiter in `OpenAIChatProvider` is process-local; in a 4-worker deployment each worker has its own independent limiter window).
4. Login page does not display the selected demo accounts (the login page says "Authorized use only. Contact your administrator for credentials.").
5. Production Compose/targets and Caddy configuration require implementation (`docker-compose.prod.yml` does not exist; production Dockerfile targets must be set).
6. Production secret/config workflow requires implementation.
7. Backup/restore and log-rotation procedures require implementation.
8. README/license/status reconciliation remains required.
9. Live OpenRouter embedding compatibility remains documentation-supported but not yet live-verified (the bounded live smoke is a WP-P7-02 gate).
10. Exact domain/FQDN remains undecided deployment-time input.

---

## 6. Rate-Limiting Contract

WP-P7-02 must choose and validate one production-safe solution:

- Redis-backed distributed rate limiting; or
- an explicitly justified single-backend-worker configuration for Release 1.

The current in-memory/per-instance limiter does NOT protect a multi-worker deployment. This contract does not claim it does.

---

## 7. Security-Hardening Contract

No public deployment may begin before a separate bounded VPS security-hardening action and independent verification.

The required baseline must include:

- Hostinger account protected by MFA;
- supported Ubuntu LTS with security updates installed;
- a dedicated non-root deployment user with narrowly scoped sudo;
- SSH public-key authentication;
- root SSH login disabled;
- SSH password authentication disabled only after key-based access is independently verified;
- host firewall default-deny for inbound traffic;
- only HTTP/HTTPS publicly exposed;
- SSH restricted to the Product Owner's trusted source IP or a separately approved secure access path where practical;
- PostgreSQL and Redis never exposed on public interfaces;
- backend reachable externally only through Caddy;
- Docker daemon socket not exposed to application containers;
- application containers run with the least practical privileges;
- production secrets stored outside Git with restrictive filesystem permissions;
- no secret values in Compose files, logs, reports, or evidence;
- Redis-backed distributed application rate limiting, unless a separately reviewed single-worker Release 1 topology is selected;
- Fail2ban or an equivalent SSH brute-force control;
- unattended operating-system security updates;
- Docker log rotation and disk-usage limits;
- daily PostgreSQL `pg_dump` with seven-day retention;
- at least one off-host backup copy or an explicitly accepted temporary Release 1 limitation;
- backup restore rehearsal before production;
- no public display of `admin.demo`;
- separate pre-production security verification;
- documented rollback and emergency access procedures.

WP-P7-02 may implement repository-owned configuration and hardening automation, but must not access the VPS.

Actual VPS hardening and access configuration must be a separate bounded action before staging deployment.

---

## 8. Hostinger and Domain Input Contract

Timing:

- No Hostinger credentials, VPS IP, SSH credentials, DNS mutation, or domain purchase is required for WP-P7-01.
- WP-P7-02 may use placeholders for the production FQDN, TLS contact email, VPS address, and secret locations.
- Before staging deployment, the Product Owner must provide or confirm:
  - exact production or staging FQDN;
  - VPS public IP;
  - operating-system version;
  - public SSH key installation;
  - dedicated deployment username;
  - DNS-management availability;
  - TLS contact email;
  - approved SSH exposure policy.
- Passwords, private SSH keys, Hostinger account credentials, MFA codes, and secret values must never be placed in repository files, PR bodies, prompts, reports, or chat messages.
- DNS and VPS mutations require separate explicit authorization.

Preferred naming model:

- one portfolio/project domain;
- application deployed on `demo.<domain>` or `forgemind.<domain>`;
- backend exposed through the same public origin under `/api`;
- PostgreSQL, Redis, worker, and internal backend ports remain private.

The exact FQDN remains a Product Owner deployment-time input and must not be fabricated.

---

## 9. Controlled Work-Package Decomposition

Dependency-ordered decomposition respecting the established lifecycle:

implementation → independent review → bounded remediation if required → independent re-review → Ready transition → independent pre-merge verification → regular merge commit → post-merge verification.

These gates are never combined implicitly.

### WP-P7-01 — Phase 7 deployment contract and controlled decomposition

This current documentation-only package. Records PO decisions PD-1 through PD-11, incorporates all required corrections, records PD-3a, defines scope/non-scope, defines deployment architecture, decomposes remaining work, defines gates, records security-hardening and Hostinger/domain input contracts. No code, no deployment, no provider calls.

Lifecycle: documentation PR → independent review → regular merge → post-merge verification.

### WP-P7-02 — Deployment and security configuration implementation

Production Compose/targets, Caddy configuration, secret/config validation, rate limiting, backup/logging foundations, health behavior, and the separately authorized live embedding smoke.

Lifecycle: implementation → independent review → bounded remediation if required → independent re-review → Ready transition → independent pre-merge verification → regular merge commit → post-merge verification.

Must NOT access the VPS. May use placeholders for FQDN, TLS email, VPS address, and secret locations.

### WP-P7-03 — Demo reset implementation

`reset_service.py`, reset API endpoint, audit reset event, tests. Synchronous admin-triggered reset; preserve protected/audit history; emit reset audit record; never schedule uncontrolled destructive reset.

Lifecycle: implementation → independent review → bounded remediation if required → independent re-review → Ready transition → independent pre-merge verification → regular merge commit → post-merge verification.

### WP-P7-04 — Login-page demo account UX implementation

Display `manager.demo` + `procurement.demo` + `auditor.demo` on the login page. Do NOT display `admin.demo`. Must independently review public-demo suitability of repository-owned demo credentials before rendering them.

Lifecycle: implementation → independent review → bounded remediation if required → independent re-review → Ready transition → independent pre-merge verification → regular merge commit → post-merge verification.

### WP-P7-05 — Release documentation and portfolio presentation

README reconciliation, Apache-2.0 wording, architecture/runbook material, screenshots or visuals where justified, polished English-first presentation. Reconcile stale Phase 6 feature descriptions. Correct "Proprietary" to "Apache License 2.0".

Lifecycle: documentation PR → independent review → regular merge → post-merge verification.

Dependencies: WP-P7-02, WP-P7-03, WP-P7-04 (features implemented so docs are accurate).

### Post-merge verification gate

After WP-P7-02 through WP-P7-05 are merged and post-merge verified:

### WP-P7-06 — Staging deployment action

SSH to VPS, clone repo, create `.env`, `docker compose up -d --build`, run migrations, seed, verify health.

Dependencies: WP-P7-05 merged and post-merge verified; PO approval for VPS access; domain/DNS configured; VPS security hardening completed and independently verified.

Lifecycle: deployment action → verification.

### WP-P7-07 — Independent staging smoke and acceptance verification

AT-001, AT-002, AT-014 on staging; Golden Scenario walkthrough; health verification; reboot test.

Dependencies: WP-P7-06 (staging deployed).

Lifecycle: read-only verification → evidence pack.

If staging defects exist: create a separate bounded remediation implementation package; independently re-review and reverify it; do NOT repair defects inside the read-only staging verification action.

### WP-P7-08 — Production deployment action

Deploy to production domain with final `.env`.

Dependencies: WP-P7-07 (staging verification passed); explicit PO production-deployment authorization.

Lifecycle: deployment action.

### WP-P7-09 — Independent post-deployment verification and sealed evidence collection

AT-015 on production (demo reset); AT-001/002/014 on production; 24-hour stability; release evidence pack.

Dependencies: WP-P7-08 (production deployed).

Lifecycle: read-only verification → sealed evidence pack.

### WP-P7-09A — Independent sealed-evidence review

Independent review of the release evidence pack.

Dependencies: WP-P7-09.

Lifecycle: read-only review → review report.

### WP-P7-10 — Product Owner Release 1 acceptance decision

PO reviews independent evidence review; declares Release 1 READY.

Dependencies: WP-P7-09A.

Lifecycle: PO decision.

### WP-P7-11 — GitHub Release/tag publication

Create GitHub Release/tag `v1.0.0` with release notes, evidence pack link, screenshots. Only after PO acceptance.

Dependencies: WP-P7-10.

Lifecycle: release creation.

### WP-P7-12 — Final lifecycle and documentation reconciliation

Mark deployment/release facts truthfully; close Phase 7 if justified; prepare transition to post-release stabilization.

Dependencies: WP-P7-11.

Lifecycle: documentation PR → independent review → regular merge → post-merge verification.

### Separation guarantee

The following remain separate bounded actions:

- implementation;
- review;
- remediation;
- evidence creation;
- evidence review;
- Product Owner acceptance;
- GitHub Release publication;
- lifecycle reconciliation.

---

## 10. Release 1 Entry and Exit Gates

### 10.1 Staging entry gates

- WP-P7-02 through WP-P7-05 merged and post-merge verified;
- exact-main CI green or honestly non-applicable;
- production configuration validated without exposing secrets;
- live OpenRouter chat evidence gate satisfied;
- live OpenRouter embedding evidence gate satisfied;
- demo reset verified;
- rate limiting verified;
- backup and restore rehearsal passed;
- login role workflow verified;
- no unresolved blocking findings;
- VPS security hardening completed and independently verified;
- exact domain/FQDN supplied by Product Owner.

### 10.2 Production-deployment gates

- staging deployment successful;
- staging verification passed;
- security and secret scans passed;
- rollback procedure verified;
- exact domain/FQDN supplied;
- explicit Product Owner production-deployment authorization.

### 10.3 Release 1 acceptance gates

- production post-deployment verification passed;
- sealed evidence independently accepted;
- AT-001, AT-002, AT-014, and AT-015 evaluated from deployment evidence;
- no false PASS marking before evidence exists;
- explicit Product Owner acceptance.

### 10.4 Release 1 closure gates

- Product Owner acceptance recorded;
- GitHub Release/tag published separately;
- lifecycle reconciliation merged and post-merge verified;
- only then may Release 1 become READY / DEPLOYED and Phase 7 become CLOSED.

---

## 11. Validation Boundary

This contract is documentation-only. No application, test, migration, schema, dependency, CI, infrastructure, or evidence-package file is changed by WP-P7-01.

No provider call occurred. No `.env` was accessed. No VPS was accessed. No containers were started or stopped. No DNS or TLS was configured. No GitHub Release or tag was published. No Ukrainian localization was begun.

Phase 6 and DEC-053 remain intact. Release 1 remains NOT READY / NOT DEPLOYED. No plaintext demo password was added.

---

## 12. Explicit Next Action

Independent documentation review only.
