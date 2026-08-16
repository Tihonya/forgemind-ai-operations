# WP-REC-04-VFY — Independent Sealed-Evidence Re-Review (Run -03)

**Artifact type:** Independent sealed-evidence re-review (durable record)
**Run ID:** `wp-rec-04-vfy-20260816-03`
**Review date:** 2026-08-16
**Mode:** strictly read-only

This document is the durable record of the independent sealed-evidence re-review of
the formal WP-REC-04-VFY run -03 evidence. It records the independent PASS verdict
that the Product Owner used as the basis for the separate acceptance decision. This
review was supplied by the independent reviewer (a fresh, read-only session) and is
not authored by the execution agent.

The review itself did **not** constitute Product Owner acceptance and did **not**
declare AT-009, AT-010, AT-011, or AT-012 PASS. Those declarations occurred only
through the later, explicit Product Owner acceptance of 2026-08-16, recorded
separately in `docs/reviews/wp_rec_04_phase_6_product_owner_acceptance.md` and in the
Decision Log (DEC-053).

---

## 1. Verdict

```text
INDEPENDENT SEALED-EVIDENCE RE-REVIEW PASSED — RUN wp-rec-04-vfy-20260816-03 IS ACCEPTABLE FOR PRODUCT OWNER DECISION
```

---

## 2. Run and aggregate identity

| Attribute | Value |
|-----------|-------|
| Run ID | `wp-rec-04-vfy-20260816-03` |
| Authoritative execution commit | `b651abdcca0ab634f99f10af1a22ce457bfefa58` (PR #110 merge commit) |
| Repository | `https://github.com/Tihonya/forgemind-ai-operations` |
| Aggregate SHA-256 | `d8c6e666f32fdd6da21b5020a3f7cd703475520d2ac1f0794380cbb579b0b35d` |
| Transport ZIP SHA-256 | `1bf026eb0e12df1767d0af1238320d8bfa56858c3d0121b024d1340edc6aff74` |

The formal verification verdict for this run is:

```text
FORMAL VERIFICATION PASSED — AT-009–AT-012 CANDIDATE EVIDENCE SEALED FOR INDEPENDENT RE-REVIEW
```

---

## 3. Integrity verification

The independent review recomputed package integrity directly from the sealed
artifacts (not from the package's own summary):

- Sealed root `/tmp/wp-rec-04-vfy-20260816-03/` exists exactly once; directory mode
  `0555`; exactly 15 regular files; every file mode `0444`.
- All 12 `checksums.sha256` entries recomputed and matched.
- All 13 `manifest.json` entries verified (path, size, SHA-256) and matched;
  `manifest_complete = true` is accurate.
- Aggregate SHA-256 independently recomputed using the repository convention
  (`'<sha256>  <relpath>'` lines, two spaces, no `./` prefix, sorted by relpath,
  joined with `\n` plus one trailing newline, then SHA-256) and matched
  `d8c6e666f32fdd6da21b5020a3f7cd703475520d2ac1f0794380cbb579b0b35d`.
- Transport ZIP present (41996 bytes); ZIP SHA-256 matched the declared transport
  hash; `unzip -t` reported no structural errors; a read-only extraction compared
  byte-for-byte against the sealed root with no differences.

## 4. Sensitive-material verification

An independent package-wide sensitive-material scan (not relying on
`security-hygiene.json`) was performed across all 15 files:

- Recursive JSON key scan for the normalized name `bindinghash`
  (`binding_hash` / `bindingHash` / `binding-hash` / case variants): 0 occurrences.
- Known binding-hash value (loaded into memory from the immutable -02 package) exact
  byte-match: 0 occurrences.
- Two known reusable demo-password values (loaded into memory from the immutable -02
  drivers): 0 occurrences.
- No password-value literal, no username→password mapping, no default or fallback
  credential; credentials are read from runtime environment variables only with a
  hard stop on absence.
- Absent from every file: JWT-like tokens (`eyJ…`), private-key markers, provider
  API-key values/patterns, bearer/authorization-header values, database
  connection-secret values, `.env` files, copied dotenv-style secret assignments,
  and raw external-provider payload objects.
- Descriptive terms (`binding_hash`, `password`, `Authorization`, `access_token`,
  `DATABASE_URL`, `.env`) appear only as code identifiers, SQL column names,
  env-var names, or narrative descriptions — never as values.
- High-entropy 64-hex occurrences were independently classified as SHA-256
  identities only (driver/package-file hashes, prior-run aggregates, the protected
  audit hash). No 64-hex string is a binding value, token, or secret.

The -03 package contains no prohibited value. The three prior-review defects are
remediated: E-1 (binding-hash fields stripped by `_sanitize()` before serialization),
E-2 (credentials read from runtime env vars only, no literal), and E-3 (endpoint
response hygiene and full-package hygiene computed and reported separately).

---

## 5. AT-009–AT-012 evidence conclusions

### AT-009 — Human approval blocks write (SUCCEEDED)

Scenario-proven: a genuine completed workflow persisted a VALIDATED recommendation
proposing `CREATE_PROCUREMENT_TASK` for RISK-001; a PRODUCTION_MANAGER created a
PENDING approval; zero procurement tasks and zero write events exist before
approval; direct execution before approval fails closed
(`ApprovalNotApprovedError`); self-approval fails closed (`SelfDecisionError`);
pending approval and the approval-request audit event are durably persisted. The
wrong-role denial is test-only (disclosed), not scenario-proven.

### AT-010 — Approval executes controlled action (SUCCEEDED)

Scenario-proven: an authorized PROCUREMENT_SPECIALIST distinct from the requester
approved the request; exactly one local synthetic task was created with complete
linkage (risk, workflow run, recommendation, approval, requester, approver,
correlation); action parameters match the binding; duplicate submission preserves
the same task; no vendor/price/currency/payment/external action exists. Binding
integrity is proven via booleans only (`binding_present_in_database`,
`binding_recomputed_in_memory`, `binding_matches`) — no binding value is recorded.
Concurrency, changed-parameter, and unsupported-action fail-closed assertions are
test-only (disclosed).

### AT-011 — Reject path (SUCCEEDED)

Scenario-proven (no test-only items): a distinct clean run was rejected by an
authorized PROCUREMENT_SPECIALIST; the rejection reason is durably preserved; zero
procurement tasks are created; approve-after-reject and execute-after-reject fail
closed; repeated decision fails closed; the rejection event is persisted in the
append-only audit trail; requester and decider are distinct.

### AT-012 — Audit trace completeness (SUCCEEDED)

The merged read-only endpoint `GET /api/v1/audit-trace/{correlation_id}` (authorized
AUDITOR) returned all nine canonical categories in order for the genuine
approved-path lineage, with `complete = true`, `is_legacy = false`, and
`missing_categories = []`. Every source ID resolves to a captured sanitized row
(`all_source_ids_resolvable = true`), resolving the run -02 provenance limitation.

---

## 6. AT-012 nine-item source-ID matrix

All nine source IDs resolve to captured sanitized underlying rows. Categories 1–6
derive from genuine `workflow_steps`; categories 7–9 from genuine Phase 6
`audit_events`. Correlation ID `f7ca73e2-8078-4f49-b99f-2e054ed3270a`;
workflow run `5eb55932-e003-45cc-a562-ed4dda69c160`.

| # | Category | Source | Source ID | Actor |
|---|----------|--------|-----------|-------|
| 1 | user_action | workflow_step | `4c1f589d-8cd8-45da-a4ab-189a255039aa` | manager.demo |
| 2 | deterministic_calculation | workflow_step | `4e928f9c-c516-4495-8c3f-0a4dc9d311a8` | — |
| 3 | retrieval | workflow_step | `f7be405f-2c3a-4b08-8329-a248c5e50c51` | — |
| 4 | model_call | workflow_step | `afba8d8d-a520-4f56-9add-21d8aff83cdf` | — |
| 5 | structured_validation | workflow_step | `865146ed-03dc-4b6a-bed1-08735731f73e` | — |
| 6 | recommendation | workflow_step | `0c0141ec-8412-4be3-91ae-6469a6d2a8aa` | — |
| 7 | approval_request | audit_event | `985e9cff-7d61-4c11-92e7-43d00af33539` | manager.demo |
| 8 | human_decision | audit_event | `3ddfe8d5-3dc5-4083-82cb-5c7f26852d0f` | procurement.demo |
| 9 | write_action | audit_event | `81ccac71-a39f-48ca-a9be-3665726a1abf` | procurement.demo |

The `deterministic_calculation` item is the persisted point-in-time snapshot
(`PLAN-2026-W31`, risk_count 3, RISK-001 CTRL-X4 CRITICAL shortage 8.00000000). No
fabricated or backfilled item exists; the canonical category names
`model_call`/`structured_validation` map to durable step names
`provider_call`/`validation` via the endpoint's canonical selection (a name
mapping, not a fabrication). Unknown correlation returns 404, unauthorized 403,
unauthenticated 401. Legacy and current-incomplete traces are truthfully
classified.

---

## 7. Test and environment evidence

- 109/109 selected integration tests passed (0 failed, 0 skipped) in 37.45s:
  approval 52 + procurement 23 + audit 15 + trace 19.
- Fresh isolated environment (PostgreSQL `pgvector:pg16` on host port 5435, database
  `forgemind_vfy_03`; Redis `redis:7` on port 6382), distinct from the -02
  environment; single migration head; Golden Dataset V1.0 (seed 42, anchor
  2026-07-31, plan PLAN-2026-W31).
- Zero external calls: `zero_external_calls = true`; in-process fake provider
  (model `vfy-fake`), stub retrieval (empty list, no network), and a
  FakeEmbeddingProvider are deterministic test doubles at the external boundaries
  only. No provider API key set; no vendor/ERP/payment/procurement call.

---

## 8. Non-blocking observations

The following are recorded transparently and are **not** acceptance blockers.

Scanner-methodology observations (H-1 through H-4):

- **H-1** (reference-value loading / potential vacuous zero): the scanner does not
  record the number of binding/password reference values actually loaded.
- **H-2** (dotenv-content scope): the `.env`-content check is filename-only; its
  name overstates the "content" half of its method (the substantive claim was
  independently confirmed true).
- **H-3** (authorization-header scope): JWT-pattern based, sufficient for this
  application's JWT tokens.
- **H-4** (high-entropy classification): counted but not classified per-occurrence;
  the independent review completed the classification (SHA-256 identities only).

Carry-forward limitations (R-3 / R-4), unchanged from run -02:

- **R-3:** no application-level correlation-uniqueness constraint and no adversarial
  same-correlation-different-run test.
- **R-4:** no concurrent-duplicate test for the deterministic-calculation emit-once
  guard (a concurrent-duplicate test for procurement-task creation does exist).

---

## 9. Historical evidence preserved

- Run -01 (`wp-rec-04-vfy-20260816-01`) remains a truthful **formal verification
  failure** (`FORMAL VERIFICATION FAILED — AT-009–AT-012 CANDIDATE EVIDENCE IS NOT
  ACCEPTABLE`). It is not described as accepted.
- Run -02 (`wp-rec-04-vfy-20260816-02`) was a technical PASS whose sealed-evidence
  review **FAILED**. Its review verdict remains verbatim:

```text
INDEPENDENT SEALED-EVIDENCE REVIEW FAILED — RUN wp-rec-04-vfy-20260816-02 IS NOT ACCEPTABLE FOR PRODUCT OWNER DECISION
```

Run -03 is the accepted evidence run.

---

## 10. PASS boundary

This re-review is evidence only. It did **not** constitute Product Owner acceptance
and did **not** declare AT-009–AT-012 PASS. The declaration of `AT-009 PASS`,
`AT-010 PASS`, `AT-011 PASS`, and `AT-012 PASS` occurred only through the explicit
Product Owner acceptance of 2026-08-16, recorded separately in
`docs/reviews/wp_rec_04_phase_6_product_owner_acceptance.md` and in the Decision Log
(DEC-053).
