# WP-P7-02 — Live Embedding — Product Owner Acceptance

**Acceptance date:** 2026-08-18
**Accepted by:** Product Owner
**Recorded by:** Documentation-only reconciliation package `docs/wp-p7-02-live-embedding-acceptance`
**Pinned main:** `c30a06194beda6dc7f36b441e27afd7534b8a947` (PR #114 merge commit)
**Authoritative contract:** `docs/planning/phase_7_deployment_contract.md`
**Authoritative decision:** DEC-055 (`forgemind_project_source_of_truth/08_DECISION_LOG.md`)

---

## 1. Accepted evidence identities

| Item | Identity |
|---|---|
| Sealed evidence package | `wp-p7-02-live-embedding-smoke-20260818-03` |
| Aggregate identity SHA-256 | `a755d37077fa77bd6f688c3551c3dec03c76b00ede3fec46fb7de63acbc5f0ba` |
| SHA256SUMS SHA-256 | `d11bbfe9ec9393731b27bb47c19b8b3b31a25753527636f18ecc6f4aea3f7236` |
| Pinned main | `c30a06194beda6dc7f36b441e27afd7534b8a947` |

## 2. Accepted independent-review verdict

```
INDEPENDENT LIVE EVIDENCE REVIEW PASSED — WP-P7-02 LIVE EMBEDDING GATE
EVIDENCE IS ACCEPTABLE FOR PRODUCT OWNER ACCEPTANCE
```

The independent evidence review is preserved at
`docs/reviews/wp_p7_02_live_embedding_smoke_03_independent_evidence_review.md`.

## 3. Live-gate acceptance (L1-L11)

The Product Owner accepts the authoritative live embedding gates as satisfied:

| Gate | Label | Verdict |
|---|---|---|
| L1 | authenticated_openrouter_request | PASS |
| L2 | exact_model | PASS |
| L3 | 1536_numeric_finite | PASS |
| L4 | determinism | PASS |
| L5 | db_insertion_compatibility | PASS |
| L6 | golden_dataset_seeding | PASS |
| L7 | runtime_retrieval_with_citations | PASS |
| L8 | seed_query_provider_consistency | PASS |
| L9 | invalid_credentials_fail_closed | PASS |
| L10 | provider_failure_fail_closed | PASS |
| L11 | no_secrets_in_evidence | PASS |

Verified live facts: OpenRouter endpoint `https://openrouter.ai/api/v1`; embedding
model `openai/text-embedding-3-small`; dimensions 1536; Golden corpus 3 documents /
3 APPROVED versions / 7 permissions / 9 chunks; ingestion 3 attempted / 3 succeeded /
0 failed; runtime retrieval/citations PASS; unauthorized-role denial PASS; business
checksum `sha256:840c235cb9a431b2906471270b2d1b8c7e487b9912c64d72a5fff773039172dc`;
10 outbound HTTP attempts (8 real successes, 1 real transient rate-limit, 1
intentionally-invalid credential request, 0 SDK retries); 14 embedded input items.
Request count and embedded-item count are distinct.

## 4. Credential-rotation disposition

The old OpenRouter credential was inadvertently echoed in an interactive terminal
OUTSIDE the sealed evidence package. The sealed package and report contain zero
secret (independent scan: 0 key-value / `sk-or-` / `sk-` / `Bearer` / `Authorization`
hits). The Product Owner rotated the old credential after the smoke; this is the
correct post-exposure mitigation. The independent evidence review classified the
disclosure as a MEDIUM, NON-BLOCKING security-process finding. No live-smoke rerun
is required solely because of the credential rotation. The new credential was not
inspected, read, or used in this reconciliation.

## 5. Rate-limit finding disposition (F-3)

The smoke observed a single transient OpenRouter embedding rate-limit, and the
repository embedding path has no embedding-specific pacing/retry code. This is an
OPERATIONAL INFO observation, NOT an unsatisfied Phase 7 §6 requirement.

The Phase 7 §6 rate-limiting contract (Redis-backed distributed rate limiting OR an
explicitly justified single-worker deployment) is SATISFIED by WP-P7-02 via the
Redis-backed distributed solution already on main:

- `backend/app/core/rate_limit.py` — `RedisRateLimiter`, documented as the Phase 7 §6
  production-safe primitive;
- `backend/app/api/middleware/rate_limit.py` — distributed per-client HTTP limiter
  shared through Redis;
- `backend/app/ai/provider/factory.py` — Redis-backed shared `ai-provider` limiter for
  staging/production;
- `backend/app/config.py` — `distributed_rate_limit_enabled=true` default,
  `rate_limit_degraded_mode=fail_closed`, `ai_rate_limit_per_minute=10`;
- `docker-compose.prod.yml` — Redis service plus
  `DISTRIBUTED_RATE_LIMIT_ENABLED` / `AI_RATE_LIMIT_PER_MINUTE` /
  `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_WINDOW_SECONDS` / `RATE_LIMIT_DEGRADED_MODE`
  environment wiring.

The application does NOT currently implement embedding-specific retry/pacing; this
reconciliation does not claim it does. Transient embedding-provider throttling is
carried forward as a staging operational observation: if it materially blocks
staging, a separate bounded remediation package should be opened.

## 6. Work-package and lifecycle state

- WP-P7-01 = COMPLETE (contract incorporated via PR #111 under DEC-054).
- WP-P7-02 implementation = COMPLETE and incorporated (PR #113 deployment/security
  configuration; PR #114 Golden RAG / production seed remediation; both merged and
  independently post-merge verified).
- WP-P7-02 live embedding gate = ACCEPTED (this acceptance).
- WP-P7-02 = COMPLETE / ACCEPTED.
- Phase 7 = OPEN / IN PROGRESS (NOT closed).
- WP-P7-03 (demo reset) = NEXT implementation package, NOT IMPLEMENTED.
- WP-P7-04 = NOT STARTED.
- WP-P7-05 = NOT STARTED.
- Deployment / staging / production = NOT STARTED.
- Release 1 = NOT READY / NOT DEPLOYED.
- No deployment-gated acceptance test (AT-001, AT-002, AT-014, AT-015) is changed to
  PASS by this acceptance.

## 7. Boundary statement

This artifact records an already-made Product Owner decision. It performs NO
deployment and authorizes NO VPS/staging/production action, NO provider call, NO
credential read, and NO Phase 7 closure. WP-P7-03 through WP-P7-12 remain separately
authorized bounded packages.
