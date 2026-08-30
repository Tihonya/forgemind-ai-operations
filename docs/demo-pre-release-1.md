# Demo Pre-Release 1 — Public Portfolio-Demo Checkpoint

**Last Updated:** 2026-08-29
**Defined by:** WP-DPR1-01
**Reconciliation base snapshot:** main @ `a2ac7d563f678f98a00aaf998ef0d391ff75a781` (PR #139 merge commit; snapshot semantics per DEC-051)
**Status:** DOCUMENTATION BASELINE — described code is incorporated into `main` and has been **deployed to the public Demo and independently verified**: deployment completed through WP-DPR1-02A (candidate `edbbc93894e74689e54c22056ac3e0b56880a72a` at https://demo.forgemind-ai.tech/), independent live verification passed through WP-DPR1-03A (2026-08-29). Post-merge Frontend CI, Backend CI, and End-to-End Tests are complete and successful at this commit. Current state (2026-08-29): the WP-DPR1-05 frontend correction (O2 fix, PR #138, merge commit `7b8af58db8ed9a953fb5e7cbcdcbba7fdb30d8ad`) is deployed to the public Demo and independently verified; O2 is closed; the stable live Compose invocation retains the corrected frontend (WP-DPR1-06). Exact mixed provenance: The public Demo retains the previously verified backend and worker images from candidate edbbc938 and runs the WP-DPR1-05 frontend built from 7b8af58. Durable closure record: [reviews/wp_dpr1_05_06_demo_frontend_closure.md](reviews/wp_dpr1_05_06_demo_frontend_closure.md). Portfolio release `v0.1.0` built on this checkpoint is PUBLISHED: annotated tag `v0.1.0` (tag object `8e91ada34227bb72ce5f46eb0c7e7697fdf0057e`, peeling to release commit `a2ac7d563f678f98a00aaf998ef0d391ff75a781`) and GitHub Release ID `379089527` — [ForgeMind v0.1.0 — Public Portfolio Release](https://github.com/Tihonya/forgemind-ai-operations/releases/tag/v0.1.0) — with independent publication verification PASSED and the one-paragraph Release-notes polish completed (durable closure record: [reviews/wp_dpr1_08_v0_1_0_release_closure.md](reviews/wp_dpr1_08_v0_1_0_release_closure.md)). This remains distinct from formal Release 1: Release 1 stays NOT READY / NOT DEPLOYED, staging and production remain NOT STARTED; the published GitHub Release is the public portfolio release, not a Release 1 production release.

---

## What Demo Pre-Release 1 Is

Demo Pre-Release 1 is the **first public portfolio-demo checkpoint** of ForgeMind: a clearly bounded, verified slice of `main`, shown publicly (CV, technical review, hiring review) through the live public Demo. The public portfolio Demo has been deployed to this code level, candidate `edbbc93894e74689e54c22056ac3e0b56880a72a` has passed independent live verification, and the WP-DPR1-05 frontend correction is deployed and independently verified on top of it; formal Release 1 remains a separate lifecycle state. This checkpoint is the basis for portfolio release `v0.1.0` (DEC-060), which is PUBLISHED: the annotated tag `v0.1.0` and the GitHub Release (ID `379089527`) were created by WP-DPR1-08 at release commit `a2ac7d563f678f98a00aaf998ef0d391ff75a781` (the WP-DPR1-07 reconciliation merge commit), and the publication passed independent verification; the WP-DPR1-07 lifecycle reconciliation is COMPLETE / INCORPORATED through PR #139.

It demonstrates one complete, auditable, human-approved vertical workflow — Production Plan Supply Risk Review — in a Ukrainian-first interface, backed by passing acceptance tests AT-003 through AT-013 and Playwright end-to-end journeys (`golden-scenario.spec.ts`, `approval-trail.spec.ts`).

## What Demo Pre-Release 1 Is Not

| Demo Pre-Release 1 is NOT | Authoritative reason |
|---------------------------|----------------------|
| A formal Release 1 production deployment | Phase 7 deployment contract (DEC-054, DEC-058 Model C): staging/production remain NOT STARTED |
| A formal Release 1 GitHub publication | The one published GitHub Release (ID `379089527`, tag `v0.1.0`) is the public portfolio release — a portfolio release, not formal Release 1 production acceptance; formal Release 1 publication remains WP-P7-11 |
| Final Release 1 acceptance | All Phase 7 gates remain intact; Release 1 remains NOT READY / NOT DEPLOYED |
| Completion of all planned UX work | WP-UX-UA-06 through WP-UX-UA-12 (including the full interactive Document Trace Map) remain NOT STARTED |

Marking the demo updated, publishing a Release, accepting Release 1, or completing the UX roadmap each require their own separate authorization and verification. This revision records the completed public Demo deployment (WP-DPR1-02A), the completed independent live verification (WP-DPR1-03A), the satisfied advertisement boundary, and the incorporated WP-DPR1-07 lifecycle reconciliation (below); it does not declare formal Release 1 acceptance, does not claim production deployment, does not complete the remaining UX roadmap, and performs no credential rotation; the tag `v0.1.0` and the GitHub Release were published by the separately authorized and independently verified WP-DPR1-08 publication package and remain a public portfolio release, not formal Release 1 acceptance.

## Purpose

1. **Demonstrate a controlled AI-assisted decision workflow** — analysis and recommendations are produced by AI, but every consequential procurement action passes an independent human approval gate with persisted, correlated audit events.
2. **Provide a clear portfolio artifact** for technical reviewers and recruiters: source code, tests, acceptance-test evidence, architecture documentation, and a 3–5 minute demonstrable scenario.
3. **Show authorization, traceability, and auditability — not merely an AI chat interface.** Role separation, approval boundaries, and the correlated read-only Decision Trail are themselves part of the demonstrated product.

## Demonstrable User Journey

The incorporated guided journey (WP-UX-UA-05, PR #135; E2E coverage in `frontend/e2e/approval-trail.spec.ts`):

1. A Manager opens a supply risk and reviews its analysis, RAG evidence citations, and structured AI recommendation.
2. The Manager submits the recommendation for approval with **«Передати на погодження»** — without manually entering any UUID; the request is prefilled from the completed recommendation.
3. A Procurement Specialist sees the pending request in the Approval Center and approves or rejects it independently (self-approval is impossible).
4. An approved request remains reachable after the decision — the trail is not lost when the workflow advances.
5. The specialist creates the linked procurement task with **«Створити завдання на закупівлю»** (only from approved requests).
6. The Auditor opens the read-only, linear correlated Decision Trail — **«Ланцюжок рішення»** — connecting risk → analysis → recommendation → approval → task → audit events.
7. The rejection path is terminal and produces no procurement task.

All journey copy is presented in the Ukrainian default locale (English secondary locale available via the locale switcher).

## Included Capabilities

Every capability below is traced to incorporated code or tests on `main`; nothing here is aspirational.

| Capability | Evidence |
|------------|----------|
| Ukrainian application interface (default `uk`, secondary `en`) with responsive application shell | WP-UX-UA-01..03, PRs #128/#130/#132; catalog key-parity test in frontend vitest gate; responsive verification at 360×800 / 390×844 / 768×1024 / 1280×800 |
| Localized statuses and severity explanations with stable machine codes preserved | WP-UX-UA-04, PR #134 (merge commit `b8e548498d7756b7a2280b16a62adde1bb9aaa7b`) |
| Role-separated Manager / Procurement Specialist / Auditor experiences with login role selection | AT-002 implemented (deployment-gated); WP-P7-04, PR #117 |
| Risk, analysis, evidence-citation, and recommendation presentation | AT-004, AT-005, AT-006 PASS |
| Guided approval workflow (submit from completed recommendation, no manual UUID entry) | WP-UX-UA-05, PR #135 (merge commit `feb14a73617c3c13f677e46c199fefae1c6b6111`); `approval-trail.spec.ts` |
| Linked procurement-task creation from approved requests only | AT-010 PASS |
| Correlated read-only Decision Trail («Ланцюжок рішення») reaching audit events | AT-012 PASS; WP-UX-UA-05 |
| Authorization boundaries (RBAC, no self-approve, Auditor read-only) | AT-007, AT-009, AT-011 PASS |
| Golden Scenario end-to-end walkthrough (Playwright) | `frontend/e2e/golden-scenario.spec.ts`; End-to-End Tests successful at the pinned merge commit |

## Known Limitations (Explicit Non-Claims)

Demo Pre-Release 1 does **not** claim:

1. **No complete source-document-to-citation Document Trace Map.** The current «Ланцюжок рішення» is a linear correlated trail (risk → analysis → recommendation → approval → task → audit events), not an interactive map linking every statement back to retrieved source-document fragments. The full Trace Map is deferred to WP-UX-UA-07 (backend projection) + WP-UX-UA-08 (Trace Map frontend), both NOT STARTED.
2. **No final production hardening or SLA.** The formal Release 1 production deployment, deployment-gated acceptance tests (AT-001, AT-002, AT-014, AT-015 from deployment evidence), and operational SLAs remain future work under the Phase 7 contract.
3. **No final visual polish.** The visual design-system foundation is incorporated, but accessibility/responsive consolidation audit (WP-UX-UA-11) and polish iterations are subsequent work.
4. **Not completion of every planned Release 1 work package.** WP-UX-UA-06 through WP-UX-UA-12 and Phase 7 staging/production packages WP-P7-06 onward remain pending.
5. **No real enterprise integrations.** Only synthetic data and synthetic local records exist; no ERP or corporate system is connected. (The hosted OpenAI-compatible provider integration — OpenRouter — is real and verified.)
6. **Provider key/budget configuration is operator-side.** The repository itself carries no provider keys; runtime embedding/chat providers require operator `.env` configuration, including at seeding time.

Recorded during reconnaissance, additionally material: the currently published Demo environment predates WP-UX-UA-04/05 incorporation — until redeployed it may show older behavior, which is precisely why advertisement of the update requires post-deployment verification (below). *(Historical note, resolved 2026-08-29: the Demo has since been redeployed to candidate `edbbc938` through WP-DPR1-02A and independently verified through WP-DPR1-03A; the advertisement boundary below has been satisfied.)*

## Demo Readiness and Deployment Boundary

- The code described by this checkpoint **is incorporated into `main`** at `feb14a73617c3c13f677e46c199fefae1c6b6111` (PR #135 merge commit), with all required post-merge CI workflows complete and successful.
- **Deployment to the public Demo is a separate controlled action**, governed by the isolated disposable Demo stack procedures (`docker-compose.demo.yml`, operator-level reset; see [demo-environment.md](demo-environment.md)).
- **Deployed (2026-08-27, WP-DPR1-02A):** the public Demo at **https://demo.forgemind-ai.tech/** runs the exact candidate `edbbc93894e74689e54c22056ac3e0b56880a72a` (in-place Compose update, one controlled reset, per-service candidate image IDs verified). The deployment report recorded zero repository edits and no lifecycle-reconciliation claims.
- **Independently verified (2026-08-29, WP-DPR1-03A):** live verification **passed** — verified Manager → Procurement Specialist → Auditor journey, rejection path, role boundaries, Ukrainian-first and responsive presentation (desktop 1440×900 and mobile 390×844) and basic keyboard accessibility, against the deployed instance. The concise durable record: [reviews/wp_dpr1_03a_live_demo_verification.md](reviews/wp_dpr1_03a_live_demo_verification.md). The practical public walkthrough: [demo-guide.uk.md](demo-guide.uk.md).
- **Advertisement boundary satisfied:** the public Demo may now be advertised as updated to this checkpoint's code level, based on the passed independent verification.
- **This documentation milestone deploys nothing.** Updating this document does not touch the demo host, containers, DNS, TLS, or secrets.
- **Not formal Release 1:** the verified Demo does not constitute Release 1 deployment, acceptance or completion — Release 1 remains NOT READY / NOT DEPLOYED, staging and production remain NOT STARTED, the one published GitHub Release is the public portfolio release `v0.1.0` rather than a Release 1 production release, and the remaining UX packages (WP-UX-UA-06 through WP-UX-UA-12, including the interactive Document Trace Map) remain NOT STARTED.

## Lifecycle Position

Accepted lifecycle order (each step a separately authorized, bounded action; completed steps marked COMPLETE below):

```
Demo Pre-Release 1 documentation baseline (WP-DPR1-01 — COMPLETE, merged)
→ independent public-demo deployment action (WP-DPR1-02A — COMPLETE, 2026-08-27: demo.forgemind-ai.tech runs candidate edbbc938)
→ independent post-deployment verification (WP-DPR1-03A — COMPLETE, 2026-08-29: PASSED; advertisement boundary satisfied)
→ O2 frontend correction deployed and independently verified (WP-DPR1-05 — COMPLETE, 2026-08-29: PR #138, merge commit 7b8af58; O2 closed on the public Demo)
→ live Compose frontend-pin stabilization (WP-DPR1-06 — COMPLETE, 2026-08-29: the stable live Compose invocation retains the corrected frontend)
→ lifecycle reconciliation and DEC-060 (WP-DPR1-07 — COMPLETE, PR #139: this checkpoint is the basis for portfolio release v0.1.0)
→ portfolio release publication (WP-DPR1-08 — COMPLETE, 2026-08-29: annotated tag v0.1.0 + GitHub Release ID 379089527, independently verified; a portfolio release, not production acceptance)
→ subsequent UX packages (Trace Map backend 07 → Trace Map frontend 08; provider-output language 09;
   consolidation audits; WP-UX-UA-12 demo verification) continue WITHOUT blocking the portfolio publication
```

The steps through portfolio release publication are complete: the Demo is deployed, verified, and publicly presentable at this checkpoint's code level, and portfolio release `v0.1.0` is published and independently verified.

## Related Documents

- [Current lifecycle status](next_steps.md)
- [Active work tracker](ACTIVE_WORK.md)
- [Isolated Demo environment](demo-environment.md)
- [Ukrainian recruiter Demo walkthrough](demo-guide.uk.md)
- [UX product direction and decomposition](planning/wp_ux_ua_00_product_direction.md)
- [Phase 7 deployment contract](planning/phase_7_deployment_contract.md)
- [Product and MVP scope (Source of Truth)](../forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md)
