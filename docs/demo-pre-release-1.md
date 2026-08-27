# Demo Pre-Release 1 — Public Portfolio-Demo Checkpoint

**Last Updated:** 2026-08-27
**Defined by:** WP-DPR1-01
**Reconciliation base snapshot:** main @ `feb14a73617c3c13f677e46c199fefae1c6b6111` (PR #135 merge commit; snapshot semantics per DEC-051)
**Status:** DOCUMENTATION BASELINE ONLY — all described code is incorporated into `main`; nothing has been deployed by this milestone definition. Post-merge Frontend CI, Backend CI, and End-to-End Tests are complete and successful at this commit.

---

## What Demo Pre-Release 1 Is

Demo Pre-Release 1 is the **first public portfolio-demo checkpoint** of ForgeMind: a clearly bounded, verified slice of `main`, intended to be shown publicly (CV, technical review, hiring review) once an independently authorized deployment action brings the running isolated Demo environment to this code level.

It demonstrates one complete, auditable, human-approved vertical workflow — Production Plan Supply Risk Review — in a Ukrainian-first interface, backed by passing acceptance tests AT-003 through AT-013 and Playwright end-to-end journeys (`golden-scenario.spec.ts`, `approval-trail.spec.ts`).

## What Demo Pre-Release 1 Is Not

| Demo Pre-Release 1 is NOT | Authoritative reason |
|---------------------------|----------------------|
| A formal Release 1 production deployment | Phase 7 deployment contract (DEC-054, DEC-058 Model C): staging/production remain NOT STARTED |
| A GitHub Release | No tag or GitHub Release is created for this checkpoint (GitHub Release publication is a separate Phase 7 package, WP-P7-11) |
| Final Release 1 acceptance | All Phase 7 gates remain intact; Release 1 remains NOT READY / NOT DEPLOYED |
| Completion of all planned UX work | WP-UX-UA-06 through WP-UX-UA-12 (including the full interactive Document Trace Map) remain NOT STARTED |

Marking the demo updated, publishing a Release, accepting Release 1, or completing the UX roadmap each require their own separate authorization and verification. This document does none of them.

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

Recorded during reconnaissance, additionally material: the currently published Demo environment predates WP-UX-UA-04/05 incorporation — until redeployed it may show older behavior, which is precisely why advertisement of the update requires post-deployment verification (below).

## Demo Readiness and Deployment Boundary

- The code described by this checkpoint **is incorporated into `main`** at `feb14a73617c3c13f677e46c199fefae1c6b6111` (PR #135 merge commit), with all required post-merge CI workflows complete and successful.
- **Deployment to the public demo is a separate controlled action**, governed by the isolated disposable Demo stack procedures (`docker-compose.demo.yml`, operator-level reset; see [demo-environment.md](demo-environment.md)).
- **This documentation milestone deploys nothing.** Defining Demo Pre-Release 1 does not touch the demo host, containers, DNS, TLS, or secrets.
- **The public demo must not be advertised as updated until an independent post-deployment check passes** against the deployed instance (observing the UA-04/UA-05 behavior described here).

## Lifecycle Position

Accepted order for the coming steps (each a separately authorized, bounded action):

```
Demo Pre-Release 1 documentation baseline (WP-DPR1-01 — THIS milestone, awaiting review/merge)
→ independent public-demo deployment action (brings demo.forgemind-ai.tech to this code level)
→ independent post-deployment verification (then, and only then, advertise/update resume references)
→ subsequent UX packages (Trace Map backend 07 → Trace Map frontend 08; provider-output language 09;
   consolidation audits; WP-UX-UA-12 demo verification) continue WITHOUT blocking the portfolio publication
```

The full Document Trace Map and further visual polish are subsequent roadmap work, not prerequisites for the first portfolio-demo publication. Release 1 completion continues through the unchanged Phase 7 gates.

## Related Documents

- [Current lifecycle status](next_steps.md)
- [Active work tracker](ACTIVE_WORK.md)
- [Isolated Demo environment](demo-environment.md)
- [UX product direction and decomposition](planning/wp_ux_ua_00_product_direction.md)
- [Phase 7 deployment contract](planning/phase_7_deployment_contract.md)
- [Product and MVP scope (Source of Truth)](../forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md)
