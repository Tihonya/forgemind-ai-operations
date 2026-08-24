# WP-UX-UA-00 — Ukrainian-First, First-Time User Experience, Mobile-First and Traceability Product Direction

**Package:** WP-UX-UA-00 — Product decision application and planning reconciliation (documentation-only)
**Status:** COMPLETE / INCORPORATED through PR #126 (regular merge commit `1b60d293d05fc76f5610d11fcc9100edd3d8dfb4`, 2026-08-24). This document records accepted Product Owner decisions and the updated bounded implementation order. It authorizes NO implementation.
**Decision record:** DEC-059 (see `forgemind_project_source_of_truth/08_DECISION_LOG.md`)
**Date:** 2026-08-24
**Reconciliation base snapshot:** main @ `7e80e0f3ccb98dcf5685509b6847bc9c193fd599` (PR #125 merge commit; snapshot semantics per DEC-051)

**Evidence base:** WP-UX-UA-TRACE-01 reconnaissance report
`/tmp/wp-ux-ua-trace-01-reconnaissance-report.md`
SHA-256 `ff263e28146ea13b9315ede51160bacb01e99ccf54f9c028e9319fc72047c80c` (552 lines), prepared read-only against the reconciliation base snapshot. The reconnaissance findings summarized below are evidence, not implementation.

---

## 1. Purpose

ForgeMind must become understandable and visually coherent for a person opening the demo for the first time. This document applies the Product Owner decisions U1–U6 and the first-time-user, visual, and mobile-first product contracts, and defines the updated bounded work-package order for the UX phase. It supersedes ONLY the English-first ordering recorded in DEC-054; every deployment-security and lifecycle boundary of DEC-054 remains intact.

A user opening the demo must immediately understand:

- what ForgeMind demonstrates;
- which demo role to choose;
- what scenario to follow;
- what has already happened;
- what was produced deterministically;
- what was produced by AI;
- which evidence and documents were used;
- where human approval is required;
- what action should be taken next;
- where the resulting action and audit evidence can be inspected.

Mobile usability is a first-class product requirement, not a final cosmetic hardening phase.

## 2. Accepted Product Owner decisions (recorded in DEC-059)

### U1 — Language priority

- Ukrainian is the default product and demo language.
- English remains available as the secondary locale.
- This supersedes ONLY the English-first ordering established by DEC-054; the remaining deployment-security and lifecycle boundaries of DEC-054 are preserved.
- Stable API enums, database values, event codes and persisted machine identifiers remain English and must never be translated in storage.
- User-facing labels and explanations are localized through the frontend catalog.

### U2 — Workflow transition history

- Authoritative workflow-run state transitions should eventually be emitted as canonical Audit Log events.
- Each authoritative event should support actor, timestamp, reason, correlation identity and exact `from_status → to_status`.
- This requires a separate bounded backend contract and migration package.
- The migration and emitters are NOT implemented by any UX frontend package.
- Until that package is completed, the UI must clearly distinguish derived workflow progress from persisted audit history.

### U3 — Initial document trace strategy

- The first Document Trace implementation is projection-first and read-only.
- It may reconstruct relationships only from existing repository data.
- It must not fabricate ingestion events, missing transitions or source relationships.
- Missing evidence must be shown explicitly as unavailable or not recorded.
- The Audit Log remains the canonical source of truth for persisted transitions.
- A second persistent timeline or competing event history is forbidden.

### U4 — Source identity

- ForgeMind requires structured document-source identity to support credible provenance.
- The eventual contract should be capable of representing source type, source-system identity, external document identity and ingestion identity.
- This is a separate schema-design and migration package.
- Release 1 may initially show only relationships supported by current fields and must not present title or description text as authoritative source identity.

### U5 — Language of provider-generated content

- AI-generated recommendation summaries, business impact and rationale should follow the active user locale.
- Ukrainian is the default requested model-output language; English is requested when the user explicitly selects English.
- Machine-readable schemas, enum values, validation contracts and audit codes remain language-neutral/stable.
- Prompt and model-behavior changes require their own bounded implementation and verification package; no AI prompt is modified by any other package.

### U6 — Graph rendering dependency

- A maintained specialized graph library may be introduced for the desktop/tablet Trace Map after a bounded dependency and security review.
- React Flow is the preferred candidate unless repository-grounded review identifies a material incompatibility.
- The graph is progressive enhancement, never the only representation.
- A semantic linear trace must remain available and keyboard accessible.
- On narrow mobile screens, the linear trace is the default presentation; the interactive graph may be opened as a secondary expanded view.
- The dependency is not added by this or any planning package.

## 3. DEC-054 supersession boundary (exact)

Superseded by U1 (DEC-059):

- DEC-054's ordering "deploy Release 1 initially in English; add Ukrainian localization after deployment stabilization" (Context paragraph 2 of DEC-054);
- the corresponding deferred item "Ukrainian localization" in DEC-054's deferred-items list;
- the deployment-contract statements that Release 1 UI is English-first and that Ukrainian localization is deferred until after deployment stabilization (`docs/planning/phase_7_deployment_contract.md`, scope and deferred-items wording);
- the README limitation bullet stating Release 1 is English-first with Ukrainian localization deferred.

NOT superseded — every other DEC-054 control remains in force, including but not limited to:

- the Phase 7 deployment contract as the authoritative Release 1 deployment contract;
- PD-1 through PD-12 (provider configuration, embedding path, demo roles, deployment model);
- all staging/production/release gates and the Model C promotion model (DEC-058);
- the VPS security-hardening contract and Hostinger/domain input contract;
- the documentation-only/no-implementation authorization boundary of WP-P7-01;
- Release 1 status NOT READY / NOT DEPLOYED;
- the prohibition on provider calls, VPS access, DNS/TLS mutations, container start/stop and GitHub Release publication outside separately authorized packages.

## 4. First-time user experience contract

### 4.1 Login

The login screen must explain the product in plain language and present demo roles as user goals rather than internal authorization concepts. Preferred Ukrainian role framing:

- «Хочу перевірити ризики постачання» — Production Manager;
- «Хочу погодити запропоновану дію» — Procurement Specialist;
- «Хочу перевірити історію та докази» — Auditor.

The screen must clearly disclose that the environment uses synthetic demonstration data.

### 4.2 First entry after login

The first dashboard view must provide:

- a short explanation of the selected role;
- a visible recommended first action;
- a compact Golden Scenario stepper;
- progress derived only from real backend state;
- an option to dismiss or collapse extended guidance without losing access to it permanently.

No competing workflow state for onboarding may be persisted. Onboarding progress is derived from live queries only.

### 4.3 Every primary screen

Every primary screen must make evident:

1. screen purpose;
2. current state in plain language;
3. business meaning;
4. primary next action;
5. links to related entities and evidence;
6. clear separation between deterministic calculation, AI assistance, human decision and demo simulation.

### 4.4 Technical details

Raw UUIDs, checksums, database services, migration revisions and internal enum values must not dominate ordinary business screens. They may be available through:

- a disclosure;
- a copy-ID action;
- a technical details drawer;
- an auditor/admin-specific view.

## 5. Visual experience direction

ForgeMind retains a professional operations and industrial-risk identity, but the UI must become calmer, more consistent and easier to scan. A later bounded visual-system package (WP-UX-UA-02, §7) covers:

- typography hierarchy;
- spacing scale;
- surface/card hierarchy;
- semantic colors;
- status badges;
- icon usage;
- primary and secondary actions;
- empty, loading, success and error states;
- content density;
- consistent drawers, dialogs and tables;
- reduced visual competition between technical and business information.

"Beautiful" must be verified through consistency and comprehension, not only decorative effects.

Avoid:

- excessive gradients;
- decorative animations that delay work;
- dense walls of cards;
- raw codes as primary content;
- multiple competing primary buttons;
- desktop-only hover interactions;
- color as the only status indicator.

## 6. Mobile-first product contract

Mobile requirements apply to every UI package from WP-UX-UA-01 onward.

Reference viewports:

| Viewport | Purpose |
|---|---|
| 360 × 800 | narrow phone |
| 390 × 844 | modern phone |
| 768 × 1024 | tablet portrait |
| 1280 × 800 | laptop/desktop |

Global acceptance requirements (every frontend package):

- no unintended horizontal page scrolling at 360 px;
- all primary actions reachable without hover;
- touch targets at least 44 × 44 CSS pixels where practical;
- visible keyboard focus;
- correct heading and landmark structure;
- Ukrainian text expansion must not truncate critical labels;
- dialogs and drawers become full-screen or near-full-screen on narrow viewports;
- sidebar navigation becomes an accessible mobile menu;
- current role, locale and sign-out remain reachable;
- sticky elements must not obscure content or actions;
- loading, error and empty states must remain understandable on mobile.

Responsive content rules:

- data tables must not simply shrink beyond readability; use responsive cards, priority columns or a controlled horizontal table region with an explicit accessibility strategy;
- dashboard widgets become a single-column task-prioritized layout;
- filter toolbars become stacked controls or a filter drawer;
- the most important action remains visible before secondary metadata;
- long UUIDs and correlation IDs must wrap, truncate safely and provide a copy action;
- the Document Trace linear representation is the default mobile view;
- any graph view must support pan/zoom controls usable by touch and must not trap page scrolling;
- event details open as a mobile-friendly sheet or full-screen surface.

Testing requirement: automated or documented viewport evidence for every materially changed route, in each package that changes it — not only in the final consolidation audit.

## 7. Updated bounded work-package decomposition

All packages are separate PRs. No single PR combines all UX work. Backend migrations are always separated from frontend presentation work. Responsive/mobile acceptance criteria are part of every frontend package, not deferred to the end. None of the packages below is implemented or authorized for implementation by this document; each requires its own authorization.

### WP-UX-UA-01 — Localization foundation, localized login pilot and first-time guidance pilot

- Objective: i18n foundation (`uk` default, `en` secondary), catalog skeleton, typed keys, locale switcher, `<html lang>` sync, missing-translation fallback, Europe/Kyiv-aware date/time helpers; localized login pilot with goal-based role framing and synthetic-data disclosure; first-time dashboard guidance pilot (role explanation, recommended first action, compact Golden Scenario stepper, dismissible, progress derived only from live backend state); mobile login acceptance.
- Dependencies: DEC-059 merged; bounded library-choice spike (react-i18next vs react-intl) resolved inside the package plan.
- Likely file scope: `frontend/package.json` (single dependency addition), new `frontend/src/i18n/**`, `frontend/src/main.tsx`, `frontend/src/routes/login.tsx`, `frontend/src/routes/dashboard.tsx` (guidance pilot only), `frontend/src/components/layout/Header.tsx` (switcher), `frontend/src/lib/format.ts`, `frontend/src/lib/audit-api.ts` (date helpers), CI key-parity job, tests.
- Acceptance: `uk` default boots; switcher persists; login fully localized in both locales; goal-based role framing renders; synthetic-data disclosure visible; Europe/Kyiv dates verified with fixed instants; CI fails on `uk` key gaps; mobile acceptance at the four reference viewports for changed routes; no API/enum/persisted-value change.
- Migration: none. Live verification: not required.

### WP-UX-UA-02 — Visual design-system foundation

- Objective: calmer, consistent visual system applied to pilot surfaces first: typography hierarchy, spacing scale, surface/card hierarchy, semantic colors, status-badge primitives, icon usage rules, primary/secondary action hierarchy, empty/loading/success/error state primitives, content-density rules, consistent drawer/dialog/table patterns, reduced visual competition between technical and business information. Separated from broad translation migration so each stays reviewable.
- Dependencies: WP-UX-UA-01 (pilot surfaces exist in localized form).
- Likely file scope: Tailwind theme/config, `frontend/src/components/ui/**`, layout components, pilot screens, tests.
- Acceptance: consistency verified against §5 avoid-list; comprehension verified (plain-language state labels); mobile acceptance on changed routes; no behavior change.
- Migration: none. Live verification: not required.

### WP-UX-UA-03 — Ukrainian translation catalog (broad migration)

- Objective: migrate all remaining screen copy, menu labels, headings, buttons, empty states, error messages, placeholders, accessibility labels to catalogs; Ukrainian pluralization (ICU rules); uk/en parity; replace hardcoded en-US formatting everywhere; provider-generated text stays untouched (U5 owns model-output language).
- Dependencies: WP-UX-UA-01, WP-UX-UA-02.
- Likely file scope: all non-test `frontend/src/routes/**` and `frontend/src/components/**`, `navigation-config.ts`, `demo-accounts.ts`, `frontend/src/i18n/locales/**`, corresponding tests.
- Acceptance: no hardcoded user-visible English string in non-test TSX (grep gate + review); plural tests for 1/2/5/21 forms; Europe/Kyiv dates everywhere; mobile acceptance on changed routes; no machine-code literal localized.
- Migration: none. Live verification: not required.

### WP-UX-UA-04 — Localized statuses and explanations

- Objective: single status-label registry mapping every machine status to a localized label plus plain-language explanation; eliminate every raw-enum render site (approval status, workflow run/step states on run detail, plan status, severity, PO/order/alternative statuses); machine codes preserved in data attributes and disclosures; distinct visual treatments for distinct state machines.
- Dependencies: WP-UX-UA-01; reconnaissance §7 status inventory frozen as contract.
- Likely file scope: new `frontend/src/lib/status-labels.ts`, badge components, `workflow-state-labels.ts`/`audit-api.ts` label maps as wrappers, risk-detail panels, `status.json` catalogs, tests.
- Acceptance: table-driven tests cover every machine code in both locales; unknown code safe fallback; tooltips/disclosures carry explanations; mobile acceptance.
- Migration: none. Live verification: not required.

### WP-UX-UA-05 — Navigation, onboarding completion and entity cross-links

- Objective: complete NextStepCard and ScenarioStepper (state-derived, non-persistent); close cross-link gaps (recommendation → approval center; approval card → run/risk/audit trace; audit event → referenced entity; run detail → trace dialog); Workflow Runs list route; sidebar becomes an accessible mobile menu; role/locale/sign-out reachable on mobile.
- Dependencies: WP-UX-UA-03.
- Likely file scope: new common guidance components, `RecommendationForRisk.tsx`, `approval-request-card.tsx`, `audit-event-detail.tsx`, `workflow-run-detail.tsx`, new workflow-runs list route, `App.tsx`, navigation config/layout components, tests.
- Acceptance: every primary screen has an evident next action; stepper derives state from live queries only; mobile menu accessible; mobile acceptance on changed routes.
- Migration: none. Live verification: not required.

### WP-UX-UA-06 — Audit/status-transition contract gaps (backend contract package)

- Objective: bounded backend contract and migration package (per U2) for authoritative workflow-run transition events with actor, timestamp, reason, correlation identity and exact `from_status → to_status`; decide document/ingestion entity extension of `audit_events`; until merged, all UI distinguishes derived workflow progress from persisted audit history.
- Dependencies: DEC-059; independent of frontend packages (may run in parallel).
- Likely file scope: `backend/app/models/audit.py` (additive allow-list extension), new Alembic migration, `backend/app/services/audit_service.py`, workflow emitters, schemas, tests. Planning-only variant touches docs only.
- Acceptance: migration up/down clean; existing audit tests green; new events carry the five required fields; AT-012 nine-item surface unchanged; append-only boundary preserved.
- Migration: YES. Live verification: deferred until deployment.

### WP-UX-UA-07 — Trace API (read-only document-scoped projection)

- Objective: projection-first read API per U3: `GET /documents`, `GET /documents/{id}/versions`, `GET /documents/{id}/trace` projecting documents → versions → chunk-derived index state → retrieval citations → runs → recommendations → approvals → tasks → audit events; role-filtered; sanitized (binding-hash/secret rules reused); missing evidence returned explicitly as unavailable.
- Dependencies: WP-UX-UA-06 decision (projection-first requires no audit-schema change).
- Likely file scope: new `backend/app/api/documents.py` (+ router registration), new trace schema, read-only service queries, integration tests including role-filter negatives and golden-lineage assertions.
- Acceptance: seeded Golden Scenario returns the exact expected node/edge set; no fabricated nodes; unauthorized roles filtered per AT-007 semantics; zero write operations.
- Migration: NO (projection-first). Live verification: deferred.

### WP-UX-UA-08 — Trace Map frontend (Document Trace tab)

- Objective: Knowledge Sources document list/detail and Document Trace tab: document passport, localized provenance graph with labeled edges, event-detail drawer (reusing existing audit components), deep links, filters by entity type and `correlation_id`, focused mode, accessible linear fallback as the DEFAULT mobile view; graph as progressive enhancement (desktop/tablet first), opened as a secondary expanded view on mobile.
- Dependencies: WP-UX-UA-07 (API), WP-UX-UA-03/04 (labels), U6 dependency review outcome (React Flow preferred).
- Likely file scope: new knowledge/document routes and trace components, `frontend/src/lib/documents-api.ts`, hooks, navigation config (enable Knowledge Sources), `App.tsx`, tests.
- Acceptance: graph and linear fallback render identical data; honesty rules tested (missing-segment markers, derived index state labeled as derived); keyboard-accessible fallback; touch pan/zoom not trapping page scroll; mobile acceptance at all four viewports.
- Migration: none. Live verification: demo verification (WP-UX-UA-12).

### WP-UX-UA-09 — Provider-output language package (U5)

- Objective: bounded prompt/model-behavior package so recommendation summaries, business impact and rationale follow the active user locale (Ukrainian default; English on explicit selection), while machine-readable schema fields, enums, validation contracts and audit codes remain language-neutral/stable; includes its own verification (schema validation must still pass on Ukrainian-language free text).
- Dependencies: WP-UX-UA-01 (locale concept); separate authorization.
- Likely file scope: `backend/app/ai/workflow/prompts.py`, vertical execution context wiring, schema-validator tests with locale samples, evidence package.
- Acceptance: structured schema validation unchanged; generated free text follows requested locale; evidence captured per established sealed-evidence conventions.
- Migration: none. Live verification: bounded provider verification required (separate evidence package).

### WP-UX-UA-10 — Source identity schema package (U4)

- Objective: bounded schema-design and migration package for structured document-source identity (source type, source-system identity, external document identity, ingestion identity). Until merged, UI shows only relationships supported by current fields and never presents title/description text as authoritative source identity.
- Dependencies: DEC-059; independent backend package.
- Likely file scope: model/migration design document, `backend/app/models/document.py` extension, Alembic migration, seed reconciliation, tests.
- Acceptance: additive migration; existing document/chunk/retrieval contracts unchanged; trace UI may then surface a Source node only from structured fields.
- Migration: YES. Live verification: deferred.

### WP-UX-UA-11 — Accessibility and responsive consolidation audit

- Objective: consolidation gate over all changed surfaces: focus management, ARIA semantics, contrast, heading/landmark structure, viewport evidence consolidation at 360/390/768/1280 widths, Ukrainian expansion audit, touch-target audit. This consolidates mobile behavior; it is NOT the first time mobile behavior is addressed (every prior frontend package already carries mobile acceptance).
- Dependencies: WP-UX-UA-01..08 frontend packages.
- Likely file scope: hardening edits across changed components, evidence documentation.
- Acceptance: keyboard-only completion of login → scenario → trace inspection; no focus traps; documented viewport evidence per route.
- Migration: none. Live verification: demo verification.

### WP-UX-UA-12 — Demo verification

- Objective: bounded verification on the isolated disposable Demo stack (DEC-056): Ukrainian golden scenario walkthrough, first-time-user comprehension check, document trace leg, mobile viewport evidence, sealed evidence capture.
- Dependencies: all prior packages merged; demo environment reset per `scripts/demo-reset.sh`.
- Likely file scope: none in repository (evidence under `/tmp` per convention); docs-only reconciliation afterward if needed.
- Acceptance: PO-reviewed evidence package; SoT 01 §2 scenario steps observable in Ukrainian; trace leg shows seeded lineage; mobile evidence at reference viewports.
- Migration: none. Live verification: YES (this is the demo verification).

## 8. Dependency order and execution sequence

```
Decision gate: DEC-059 merged
│
├─ Frontend track (one PR per package):
│   01 Localization foundation + login/FTUX pilot + mobile login acceptance
│   → 02 Visual design-system foundation
│   → 03 Ukrainian translation catalog (broad migration)
│   → 04 Localized statuses and explanations   (parallel with 05 after 03)
│   → 05 Navigation, onboarding completion, entity cross-links
│   → 08 Trace Map frontend                    (after 07 + 03/04)
│   → 11 Accessibility/responsive consolidation audit
│
├─ Backend track (separate from frontend presentation):
│   06 Audit/transition contract + migration package (U2)
│   → 07 Trace API projection (U3, no migration)
│   10 Source identity schema + migration (U4)     (independent; before any Source-node claim)
│
├─ Model-behavior track:
│   09 Provider-output language package (U5)       (after 01; own verification)
│
└─ 12 Demo verification (last; on isolated disposable Demo stack)
```

Critical path: 01 → 02 → 03 → (04 ∥ 05) → 08 → 11 → 12, with the backend track (06 → 07) feeding 08.

Rules:

- responsive/mobile acceptance criteria are required in EVERY frontend package (01, 02, 03, 04, 05, 08, 11);
- backend migrations (06, 10) are separate packages from frontend presentation;
- Document Trace remains projection-first until U4/U2 packages merge;
- the Audit Log remains the canonical transition source; no second persistent timeline;
- stable machine contracts (API enums, DB values, event codes, persisted identifiers) are never localized;
- each package = one focused PR; no combined UX mega-PR.

## 9. Demo availability versus Release 1 production deployment

These are distinct facts and must never be conflated:

1. **Publicly reachable demonstration environment:** the isolated disposable Demo stack (DEC-056, `docker-compose.demo.yml`, project `forgemind-demo`) is publicly reachable at `https://demo.forgemind-ai.tech/` (observed serving the ForgeMind frontend, HTTP 200, 2026-08-24). Demo availability is an operational fact about the demo stack; the FQDN is operator configuration (`CADDY_DOMAIN`), not a committed repository value.
2. **Formal Release 1 production deployment:** remains NOT STARTED / NOT READY / NOT DEPLOYED under the Phase 7 deployment contract (DEC-054, DEC-058 Model C). Pre-staging VPS hardening, staging deployment/verification (WP-P7-06/07), production promotion (WP-P7-08), post-deployment verification (WP-P7-09/09A), Product Owner acceptance (WP-P7-10), GitHub Release publication (WP-P7-11) and final reconciliation (WP-P7-12) are all still pending.

The publicly reachable demo does NOT make Release 1 deployed, accepted or complete. No deployment-gated acceptance test (AT-001, AT-002, AT-014, AT-015) is marked PASS on demo availability alone.

## 10. Machine-contract stability and audit canonicality

- Stable machine contracts are preserved: API enums, database identifiers, audit event codes, role codes, risk IDs, correlation IDs and all persisted values remain English/machine-readable and are never localized in storage or transport.
- Localization happens only in the frontend display layer via catalogs keyed by stable codes with safe fallback.
- The Audit Log (`audit_events` + `workflow_steps` projections) remains the single canonical source of truth for state-transition history. Document Trace is a read projection of existing tables; a second persistent timeline or competing activity history is forbidden.
- Derived or reconstructed information (e.g. chunk-count-based index state) must be labeled as derived, never presented as a persisted event.

## 11. Non-implementation boundary

This package changes documentation only. It does NOT:

- implement any frontend or backend code;
- add any dependency (including any graph or i18n library);
- modify AI prompts or model behavior;
- create or run any database migration;
- change deployment, infrastructure, CI behavior or evidence packages;
- authorize implementation of any WP-UX-UA package (each remains separately authorized);
- declare Release 1 deployed, accepted or complete.

## 12. Affected documents

- `forgemind_project_source_of_truth/08_DECISION_LOG.md` (DEC-059 added)
- `forgemind_project_source_of_truth/07_ROADMAP.md` (UX product-direction section)
- `docs/planning/wp_ux_ua_00_product_direction.md` (this document)
- `docs/planning/phase_7_deployment_contract.md` (DEC-059 supersession annotation, localization ordering only)
- `docs/ACTIVE_WORK.md` (governance state reconciliation)
- `docs/next_steps.md` (delivery sequence, decision log status, demo-vs-production distinction)
- `docs/demo-environment.md` (public demo availability fact)
- `README.md` (limitations reconciliation)
