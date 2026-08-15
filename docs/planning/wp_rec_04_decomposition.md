# WP-REC-04-DEC — Phase 6 Approval, Audit, and Controlled Procurement Decomposition

**Repository:** https://github.com/Tihonya/forgemind-ai-operations
**Authoritative base:** `main` @ `5b7323dec414aba321fc6ca2284ca1de4aa17dd7` (PR #96 merge commit)
**Decision Log entry:** DEC-052 (Accepted, Product Owner 2026-08-15)
**Source reconnaissance:** `/tmp/phase6-reconnaissance-and-planning-report.md` (verdict: `PHASE 6 RECONNAISSANCE INCOMPLETE — CONTRACT OR ARCHITECTURE DECISIONS REQUIRED`, now resolved by DEC-052)
**Type:** Documentation-only decision and planning package. No Phase 6 code, migration, test, frontend implementation, procurement execution, provider call, Phase 7, or deployment.

---

## 1. Purpose

This document converts the completed Phase 6 reconnaissance into an implementation-ready decomposition. It records the accepted Product Owner decisions (G1, G2, G3, M1 — DEC-052), fixes the Phase 6 contract and boundaries, defines the dependency-ordered work packages, states the required technical invariants, and maps the acceptance tests AT-009 through AT-012 to their owning packages.

This document does not authorize implementation. Phase 6 implementation remains NOT STARTED until this package is merged and its post-merge verification passes, and each implementation package below is separately authorized.

---

## 2. Authoritative Product Owner Decisions (DEC-052)

The Product Owner accepted the following decisions on 2026-08-15 (recorded in `forgemind_project_source_of_truth/08_DECISION_LOG.md` DEC-052).

### G1 — Approval authority and separation of duties

- `PRODUCTION_MANAGER` may select a persisted recommendation and create an approval request.
- Only `PROCUREMENT_SPECIALIST` may approve or reject the approval request.
- The deciding user must differ from the requester. Self-approval is forbidden.
- `ENGINEER`, `AI_ADMINISTRATOR`, and `AUDITOR` may not approve or reject procurement actions.
- `AUDITOR` remains read-only.
- Any absent role, wrong role, requester/approver identity match, missing approval, non-pending decision, or parameter mismatch must fail closed.

### G2 — Synthetic procurement boundary

The Release 1 procurement task is a synthetic local application entity containing only the business data required by the acceptance contract: component/item identity, quantity, originating risk, originating workflow run, approval request, requester and approver identities, timestamps, and correlation/audit references. It introduces no vendor or supplier, no price or monetary amount, no currency, no payment, no purchase-order transmission, no external procurement API, and no external financial action. The controlled action is creation of exactly one local `procurement_tasks` row.

### G3 — Approval lifecycle

Single-shot linear lifecycle `PENDING → APPROVED | REJECTED`. A decision is final and auditable. No expiry, revocation, reopening, or multi-approver workflow exists in Release 1. An approved action may create exactly one procurement task; a rejected action can never create a procurement task; duplicate requests or retries must not duplicate the controlled action.

### M1 — Canonical roles

Frontend authorization uses the five canonical backend roles `PRODUCTION_MANAGER`, `PROCUREMENT_SPECIALIST`, `ENGINEER`, `AI_ADMINISTRATOR`, `AUDITOR`. The unsupported `platform_admin` role is removed from the Phase 6 authorization model.

### MVP design principle

This is an intentionally synthetic portfolio MVP, not an implementation of an employer-supplied procurement specification. Creative implementation is permitted for UI presentation, naming, trace visualization, and internal organization, provided it preserves the fixed contracts: deterministic behavior; human approval; separation of duties; exact binding between approval and action parameters; fail-closed authorization; exactly-once procurement-task creation; immutable-style audit history; no real financial or external procurement action; AT-009 through AT-012. No real-world ERP complexity beyond the acceptance contracts may be invented.

---

## 3. Contract and Boundaries

### 3.1 Golden Scenario steps 9–13

From `01_PRODUCT_AND_MVP_SCOPE.md` §2 (steps owned by Phase 6):

1. (9) The user selects one recommendation.
2. (10) The system creates an Approval Request.
3. (11) Before approval, no mutating action is executed.
4. (12) After confirmation, a synthetic procurement task is created.
5. (13) The Audit Log shows the complete trace.

### 3.2 Functional requirements

- **FR-08 — Human Approval:** procurement-task creation requires explicit confirmation.
- **FR-09 — Audit:** critical reads, agent runs, approvals, and write actions are logged.

### 3.3 Acceptance tests AT-009 through AT-012

- **AT-009 — Human approval blocks write:** pending approval → no procurement task.
- **AT-010 — Approval executes controlled action:** an authorized user confirms approval → exactly one procurement task linked to risk, run, and approver.
- **AT-011 — Reject path:** rejected approval → no task; rejection reason preserved in audit log.
- **AT-012 — Audit trace completeness:** for one completed run the audit must contain nine items (user action; deterministic calculation; retrieval; model call; structured validation; recommendation; approval request; human decision; write action or rejection).

AT-009 through AT-012 remain **NOT PASS**. They are not marked PASS by this package; formal verification and a later explicit Product Owner acceptance decision are required (owned by WP-REC-04-VFY).

### 3.4 Deterministic local synthetic-action boundary

Phase 6 is fully deterministic and LLM-free. The LLM participated only upstream in Phase 5 (recommendation generation); Phase 6 never invokes a model. The controlled action is a local, synchronous, reversible-in-demo database write (creation of exactly one `procurement_tasks` row). There is no external adapter, no vendor, no payment rail.

### 3.5 No external or financial integration

- No real vendor or supplier.
- No price, monetary amount, currency, or payment.
- No purchase-order transmission.
- No external procurement API.
- No external financial action.
- Phase 6 makes zero LLM, provider, vendor, payment, or external procurement calls.

### 3.6 Role matrix

| Role | Phase 6 permissions |
|------|---------------------|
| `PRODUCTION_MANAGER` | Select a persisted recommendation; create an approval request; inspect its own approval requests. No approve/reject permission. |
| `PROCUREMENT_SPECIALIST` | Inspect pending requests; approve/reject requests created by another user. Cannot approve/reject its own request. |
| `ENGINEER` | No Phase 6 approval or procurement write authority. |
| `AI_ADMINISTRATOR` | Administrative read access where required. No procurement approval authority. |
| `AUDITOR` | Read-only Audit Log access. No write authority. |

### 3.7 Approval state machine

```
PENDING → APPROVED | REJECTED
```

- Single-shot and linear: a decision is taken once and is final and auditable.
- No expiry, revocation, reopening, or multi-approver workflow in Release 1.
- Only `PENDING` requests may be decided. A non-`PENDING` request cannot be decided again.
- The requester cannot decide its own request (separation of duties).
- `APPROVED` is the only state from which a procurement task may be created.
- `REJECTED` can never create a procurement task.

### 3.8 Action-binding and integrity requirements

- An approval request binds an immutable action snapshot or canonical action hash (never a mutable pointer).
- The binding is re-derived from the persisted recommendation at execution time and any mismatch fails closed (prevents parameter substitution after approval).
- The approval decision and task creation preserve atomic or provably idempotent behavior.
- The procurement task is linked to risk, workflow run, approval, requester, approver, and correlation ID.

### 3.9 Audit-event requirements

- Audit events are append-only: there is no normal update/delete API for audit events.
- Audit events cover at minimum: approval request creation, approval decision (approve/reject), procurement-task creation attempt and result, and rejection.
- The full AT-012 nine-item trace is completed by combining Phase 6 audit events with the existing Phase 5 `workflow_steps` and correlation ID.
- Audit events and logs contain no secrets (no API keys, tokens, prompts, or raw provider payloads).

### 3.10 Idempotency and concurrency requirements

- A database uniqueness guarantee ensures at most one procurement task per approval.
- Concurrent duplicate approval attempts cannot create two tasks.
- Duplicate requests or retries must not duplicate the controlled action.
- Re-approve/execute returns the already-created task rather than a second one.

### 3.11 Non-goals

- No real vendor/supplier or purchase-order transmission.
- No monetary, currency, payment, or financial action.
- No external procurement API or adapter.
- No approval expiry, revocation, reopening, or multi-approver workflow.
- No LLM/provider/vendor call in Phase 6.
- No Phase 7 work, no deployment, no demo reset.

---

## 4. Work Packages

Dependency order (topological):

1. `WP-REC-04B` — audit-event backend foundation.
2. `WP-REC-04A` — approval-request backend service and state machine.
3. `WP-REC-04C` — idempotent synthetic procurement-task service.
4. `WP-REC-04D` — Approval Center UI and canonical-role reconciliation.
5. `WP-REC-04E` — Audit Log UI.
6. `WP-REC-04-VFY` — formal AT-009–AT-012 evidence, independent review, Product Owner acceptance, and Phase 6 closure.

File paths named below are **planning targets**, not final implementation-file assertions; the implementer must verify actual paths against `origin/main` at implementation time (models, migrations, schemas, API routers, and frontend route/component conventions).

---

### WP-REC-04B — Audit-Event Backend Foundation

- **Objective:** Establish the append-only audit-event persistence foundation on which approval (04A), procurement (04C), and the Audit Log UI (04E) build.
- **Dependencies:** WP-REC-04-DEC (this package; supplies the event taxonomy and immutability contract). No implementation predecessor.
- **Exact contract:**
  - `audit_events` entity with: id; correlation ID; actor; event type; entity; before/after summary (or equivalent structured payload); timestamp; linked workflow run / approval / procurement identifiers as applicable.
  - Append-only write path: no update/delete API for audit events.
  - Redaction discipline: no secrets, tokens, prompts, or raw provider payloads in audit rows or logs.
  - Correlation-ID propagation consistent with `backend/app/core/correlation.py`.
- **Expected implementation areas (planning targets):** `backend/app/models/audit.py` (new), `backend/alembic/versions/*_add_audit_events.py` (new migration), `backend/app/services/audit_service.py` (new), `backend/app/schemas/audit.py` (new), `backend/app/api/audit.py` (read-only endpoints, new), plus unit and integration tests.
- **Required tests:** append-only invariant (no update/delete path); redaction; correlation-ID propagation; index/constraint correctness; migration applies cleanly and downgrades.
- **Acceptance evidence:** migration applies cleanly; audit rows immutable via API; unit + integration tests green. No AT is PASS after 04B alone.
- **Security and authorization boundaries:** audit write is internal (service-level, not user-facing); any read endpoint enforces read-only roles (`AUDITOR`, and `AI_ADMINISTRATOR` read where required). No role may mutate audit events.
- **Explicitly excluded work:** approval logic, procurement-task creation, Approval Center UI, Audit Log UI, acceptance-harness formalization.
- **Lifecycle entry:** WP-REC-04-DEC merged and post-merge verified; Product Owner issues explicit implementation authorization for WP-REC-04B.
- **Lifecycle exit:** audit foundation merged with green gates and independent review; no audit event mutation path exists; no AT PASS claimed.

---

### WP-REC-04A — Approval-Request Backend Service and State Machine

- **Objective:** Implement the approval-request record, the single-shot `PENDING → APPROVED | REJECTED` state machine, the binding snapshot/hash, and the create/approve/reject endpoints with fail-closed authorization.
- **Dependencies:** WP-REC-04-DEC (roles + lifecycle, DEC-052); WP-REC-04B (audit-event emission).
- **Exact contract:**
  - `approval_requests` entity carrying an immutable action snapshot or canonical action hash; `requested_by`; `requested_at`; `status ∈ {PENDING, APPROVED, REJECTED}`; `decided_by`; `decided_at`; `comment`; optional rejection reason.
  - Create: `PRODUCTION_MANAGER` only.
  - Approve/reject: `PROCUREMENT_SPECIALIST` only, and only when `decided_by != requested_by`.
  - Fail-closed on: absent role, wrong role, requester/approver identity match, missing approval, non-`PENDING` decision, or parameter/hash mismatch.
  - Approval decisions emit audit events (via 04B).
- **Expected implementation areas (planning targets):** `backend/app/models/approval.py` (new), `backend/alembic/versions/*_add_approval_requests.py` (new migration), `backend/app/services/approval_service.py` (new), `backend/app/schemas/approval.py` (new), `backend/app/api/approval.py` (new), plus unit and integration tests.
- **Required tests:** pending approval blocks creation; wrong-role 403; self-approval forbidden; non-`PENDING` cannot be re-decided; changed-parameters rejection; reject path; audit-event emission; separation-of-duties negative cases.
- **Acceptance evidence:** AT-009 and AT-011 backend paths exercised and green. AT-009/AT-011 remain NOT PASS until WP-REC-04-VFY formal verification.
- **Security and authorization boundaries:** enforce roles via the existing `require_role` dependency (roles reloaded from DB per request). Approver role is fixed and not configurable at request time. Requester/approver identity match fails closed.
- **Explicitly excluded work:** procurement-task creation (04C), Approval Center UI (04D), Audit Log UI (04E).
- **Lifecycle entry:** 04B merged; Product Owner issues explicit implementation authorization for WP-REC-04A.
- **Lifecycle exit:** approval service merged with green gates and independent review; no AT PASS claimed.

---

### WP-REC-04C — Idempotent Synthetic Procurement-Task Service

- **Objective:** Implement the synthetic `procurement_tasks` entity and the idempotent exactly-once creation keyed by approval.
- **Dependencies:** WP-REC-04A (approval service), WP-REC-04B (audit emission).
- **Exact contract:**
  - `procurement_tasks` carries: component/item identity, quantity, originating risk, originating workflow run, approval request, requester, approver, timestamps, and correlation/audit references. No vendor, price, amount, currency, or payment.
  - Creation requires an `APPROVED` request; rejected requests cannot execute.
  - Action-type allow-list: `CREATE_PROCUREMENT_TASK` only; any other action type fails closed.
  - A database uniqueness guarantee enforces at most one task per approval; concurrent duplicate attempts cannot create two tasks; duplicate/retry returns the already-created task.
  - Task creation emits an audit event (via 04B).
- **Expected implementation areas (planning targets):** `backend/app/models/procurement.py` (new), `backend/alembic/versions/*_add_procurement_tasks.py` (new migration), `backend/app/services/procurement_service.py` (new), `backend/app/schemas/procurement.py` (new), `backend/app/api/procurement.py` (new), plus unit and integration tests.
- **Required tests:** exactly one task per approval; duplicate-submission suppression; concurrent duplicate attempts; fail-closed without `APPROVED` approval; rejected requests cannot execute; unsupported action type fails closed; linkage to risk/run/approval/requester/approver/correlation asserted.
- **Acceptance evidence:** AT-010 backend path exercised and green. AT-010 remains NOT PASS until WP-REC-04-VFY formal verification.
- **Security and authorization boundaries:** creation is triggered only by a valid `APPROVED` decision; no direct unauthenticated creation path; no financial or external side effects.
- **Explicitly excluded work:** Approval Center UI (04D), Audit Log UI (04E), any vendor/payment integration.
- **Lifecycle entry:** 04A merged; Product Owner issues explicit implementation authorization for WP-REC-04C.
- **Lifecycle exit:** procurement service merged with green gates and independent review; no AT PASS claimed.

---

### WP-REC-04D — Approval Center UI and Canonical-Role Reconciliation

- **Objective:** Implement the Approval Center route (pending list, structured action preview, approve/reject with comment, audit metadata) and reconcile frontend role codes against the five canonical backend roles.
- **Dependencies:** WP-REC-04A and WP-REC-04C (backend approval + procurement endpoints).
- **Exact contract:**
  - `PRODUCTION_MANAGER`: create and inspect its approval requests; no approve/reject controls.
  - `PROCUREMENT_SPECIALIST`: inspect pending requests and approve/reject requests created by another user.
  - `platform_admin` is removed from the Phase 6 authorization model; the `UserRole` union uses only the five canonical roles (`PRODUCTION_MANAGER`, `PROCUREMENT_SPECIALIST`, `ENGINEER`, `AI_ADMINISTRATOR`, `AUDITOR`).
  - Approve/reject UI requires a comment and shows audit metadata; no monetary or vendor fields.
- **Expected implementation areas (planning targets):** `frontend/src/routes/approval-center.tsx` (new), `frontend/src/components/approval/*` (new), `frontend/src/lib/approval-api.ts` (new), `frontend/src/components/layout/navigation/navigation-config.ts` (role reconciliation), `frontend/src/App.tsx` (manual route registration), plus component/route tests.
- **Required tests:** component tests for pending list, action preview, approve/reject with comment; role-gating tests (production manager no approve button; procurement specialist sees approve/reject; self-request not decidable); E2E approve flow.
- **Acceptance evidence:** UI screenshots + frontend tests; E2E approve → task visible. No AT is PASS by UI alone.
- **Security and authorization boundaries:** UI gating is presentation-layer only and mirrors backend enforcement; backend remains the authority. No client-side fabrication of approval decisions.
- **Explicitly excluded work:** Audit Log UI (04E), backend changes, any financial/vendor UI.
- **Lifecycle entry:** 04A and 04C merged; Product Owner issues explicit implementation authorization for WP-REC-04D.
- **Lifecycle exit:** Approval Center merged with green gates and independent review; `platform_admin` fully removed from Phase 6 UI role model; no AT PASS claimed.

---

### WP-REC-04E — Audit Log UI

- **Objective:** Implement the read-only Audit Log route displaying actor, event, timestamp, entity, before/after summary, and correlation ID.
- **Dependencies:** WP-REC-04B (audit read endpoint).
- **Exact contract:**
  - `AUDITOR` has read-only Audit Log access.
  - `AI_ADMINISTRATOR` has administrative read access where required; no procurement approval authority.
  - No UI path creates, edits, or deletes audit events.
- **Expected implementation areas (planning targets):** `frontend/src/routes/audit-log.tsx` (new), `frontend/src/components/audit/*` (new), `frontend/src/lib/audit-api.ts` (new), `frontend/src/components/layout/navigation/navigation-config.ts` (role gating), `frontend/src/App.tsx` (manual route registration), plus component/route tests.
- **Required tests:** component tests for the nine-item trace rendering; role-gating tests (auditor read-only); E2E audit read.
- **Acceptance evidence:** UI screenshots; AT-012 nine-item trace visible end-to-end. No AT is PASS by UI alone.
- **Security and authorization boundaries:** read-only; no mutation; no secrets displayed; backend remains the authority.
- **Explicitly excluded work:** Approval Center UI, backend changes, any write path.
- **Lifecycle entry:** 04B merged; Product Owner issues explicit implementation authorization for WP-REC-04E.
- **Lifecycle exit:** Audit Log UI merged with green gates and independent review; no AT PASS claimed.

---

### WP-REC-04-VFY — Formal AT-009–AT-012 Evidence, Independent Review, Product Owner Acceptance, and Phase 6 Closure

- **Objective:** Run the Phase 6 acceptance harness in formal-evidence mode for AT-009 through AT-012, capture sealed evidence, perform independent review, obtain explicit Product Owner acceptance, and close Phase 6 with documentation reconciliation.
- **Dependencies:** WP-REC-04A, 04B, 04C, 04D, 04E all merged and green.
- **Exact contract:**
  - Formal execution of every AT-009–AT-012 clause and important negative assertion against a seeded local/CI Postgres with zero external calls.
  - Sealed, read-only evidence packages with per-file hashes and an aggregate identity.
  - Independent read-only review of the evidence.
  - Explicit Product Owner acceptance declaration (new DEC entry).
  - Only after acceptance are AT-009–AT-012 marked PASS and Phase 6 closed.
- **Expected implementation areas (planning targets):** `release-evidence/` (new, or equivalent evidence location per existing convention); acceptance-harness scenario additions under `scripts/`; review and acceptance declarations under `docs/reviews/`; lifecycle-documentation reconciliation.
- **Required tests:** formal AT-009–AT-012 execution with captured evidence (no new product code).
- **Acceptance evidence:** sealed evidence package; independent review; Product Owner acceptance declaration; AT-009–AT-012 → PASS (only upon explicit acceptance).
- **Security and authorization boundaries:** zero external calls; zero secrets in evidence; append-only audit evidence.
- **Explicitly excluded work:** new product code; Phase 7; deployment.
- **Lifecycle entry:** 04A–04E merged; Product Owner authorizes formal verification.
- **Lifecycle exit:** AT-009–AT-012 PASS by explicit Product Owner acceptance; Phase 6 CLOSED / ACCEPTED; documentation reconciled.

---

## 5. Required Technical Invariants

The Phase 6 implementation, taken across 04B/04A/04C, must preserve all of the following:

1. An approval request binds an immutable action snapshot or canonical action hash.
2. Approval decision and task creation preserve atomic or provably idempotent behavior.
3. Database uniqueness guarantees at most one procurement task per approval.
4. Concurrent duplicate approval attempts cannot create two tasks.
5. Non-`PENDING` approvals cannot be decided again.
6. The requester cannot decide its own request.
7. Procurement creation requires an `APPROVED` request.
8. Rejected requests cannot execute.
9. Unsupported action types fail closed.
10. The procurement task is linked to risk, workflow run, approval, requester, approver, and correlation ID.
11. Audit events have no normal update/delete API.
12. Audit and logs contain no secrets.
13. Phase 6 performs zero LLM, provider, vendor, payment, or external procurement calls.

---

## 6. Acceptance Mapping

Ownership of AT-009 through AT-012 and their important negative assertions. No AT is marked PASS here; all remain NOT PASS until WP-REC-04-VFY formal verification and explicit Product Owner acceptance.

| AT / assertion | Owning work package | Final evidence package |
|----------------|---------------------|------------------------|
| AT-009 valid: pending approval → no procurement task | WP-REC-04A (create request), WP-REC-04C (must not create) | WP-REC-04-VFY |
| AT-009 negative: missing approval fails closed | WP-REC-04A | WP-REC-04-VFY |
| AT-009/010 negative: wrong role fails closed | WP-REC-04A (authorization) | WP-REC-04-VFY |
| AT-009/010 negative: self-approval forbidden | WP-REC-04A | WP-REC-04-VFY |
| AT-010 valid: authorized approve → exactly one task linked to risk/run/approver | WP-REC-04A (approve) + WP-REC-04C (create) | WP-REC-04-VFY |
| AT-010 negative: duplicate submission → no duplicate task | WP-REC-04C (uniqueness/idempotency) | WP-REC-04-VFY |
| AT-010 negative: changed parameters invalidate approval | WP-REC-04A (binding hash re-check) | WP-REC-04-VFY |
| AT-010 negative: unsupported action type fails closed | WP-REC-04C (action allow-list) | WP-REC-04-VFY |
| AT-011 valid: reject → no task, rejection reason in audit log | WP-REC-04A (reject) + WP-REC-04B (audit) | WP-REC-04-VFY |
| AT-011 negative: rejected approval cannot later execute | WP-REC-04C (execution guard) | WP-REC-04-VFY |
| AT-012 nine-item completeness | WP-REC-04B (Phase 6 events) + Phase 5 `workflow_steps` (existing) | WP-REC-04-VFY |
| AT-012 negative: no secrets in audit/logs | WP-REC-04B (redaction) | WP-REC-04-VFY |
| Retry → no second task | WP-REC-04C (idempotency) | WP-REC-04-VFY |

Status: AT-009 NOT PASS; AT-010 NOT PASS; AT-011 NOT PASS; AT-012 NOT PASS.

---

## 7. Lifecycle and Authorization Boundaries

- Phase 4: CLOSED / ACCEPTED.
- Phase 5: ACCEPTED.
- Phase 6 reconnaissance: COMPLETE.
- WP-REC-04-DEC: decision and planning package; accepted as documentation after merge.
- Phase 6 implementation: NOT STARTED until this package is merged and its post-merge verification passes.
- AT-009 through AT-012: NOT PASS.
- Phase 7 and deployment: NOT STARTED.
- Release 1: NOT READY / NOT DEPLOYED.
- Next planned implementation package after WP-REC-04-DEC closure: WP-REC-04B — audit-event backend foundation.

This package does not begin implementation, Phase 7, or deployment. Each subsequent package requires its own explicit Product Owner authorization.
