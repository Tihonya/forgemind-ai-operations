# WP-DPR1-05 / WP-DPR1-06 — Demo Frontend Closure Record (O2)

**Date:** 2026-08-29
**Scope:** Durable record of the public-Demo O2 closure (Audit Log trace-action i18n defect), the WP-DPR1-05 frontend-only deployment, its independent verification, and the WP-DPR1-06 live Compose frontend-pin reconciliation.
**Repository:** https://github.com/Tihonya/forgemind-ai-operations — `main` @ `7b8af58db8ed9a953fb5e7cbcdcbba7fdb30d8ad`.

## 1. PR #138 merge identity

- PR #138 (`fix/wp-dpr1-05-audit-trace-i18n`): merged 2026-08-29T14:26:54Z; merge commit `7b8af58db8ed9a953fb5e7cbcdcbba7fdb30d8ad`; parents in order `3c260807d751974618713dbc44d1afdf2ad0902d` (prior main tip) and `a09a2a4b191574cce7474b4a24b8ed9e7c0dcf11` (reviewed head).
- Incorporated delta: exactly 5 frontend files (`uk/audit.json`, `en/audit.json`, `routes/audit-log.tsx`, `i18n/__tests__/i18n-core.test.ts`, `routes/__tests__/audit-log.test.tsx`), +105/−3; all merge-commit blobs byte-identical to the reviewed head.
- Post-merge Frontend CI and End-to-End Tests completed successfully at `7b8af58`.

## 2. Root cause of O2

O2 was the public-Demo Audit Log defect in which the row action for the audit trace rendered the i18next diagnostic `key 'trace (uk)' returned an object instead of string.` (and `[object Object]`) instead of a localized label: a duplicate string-valued `trace` key in the `uk`/`en` audit catalogs collided with (and shadowed) the nested `trace` object namespace used by the read-only trace dialog.

## 3. Fix summary (application source fix deployed to the public Demo frontend)

- The row-action key was renamed to `viewTrace` — `Слід` (`uk`) / `Trace` (`en`) — leaving exactly one nested `trace` object per audit catalog; the read-only dialog (`AuditTraceDialog`) continues its `trace.*` namespace with title `Слід аудиту`.
- Collision-specific regression tests were added (raw-source catalog guard plus Audit Log label/object-diagnostic cases).
- Fix commits: `c3ab943` (fix), `a09a2a4` (test).

## 4. Exact deployed application images (as independently verified)

| Component | Image ID |
|-----------|----------|
| backend | `sha256:7e1b21c263b710beecc13028f357adf030d2605568266f4873a5c29f6056ef51` |
| worker | `sha256:58d156b611c9b478fd3a59d41c1a5714dc002363ea3f19b700004bef4796c730` |
| frontend | `sha256:ecae3e2f60f81c31487a3764c05303a0af29adc4dbb966612166f5f7e064b19d` |
| Alembic revision | `d00f71c78f67` |

Mixed-provenance statement: `The public Demo retains the previously verified backend and worker images from candidate edbbc938 and runs the WP-DPR1-05 frontend built from 7b8af58.` The full running stack was NOT rebuilt from `7b8af58`; database state was unchanged.

## 5. Health, migration and independent UI results

- HTTPS and `/health`: HTTP 200 on `/`, `/login` and `/health`; health checks report backend/postgresql/redis/worker ok; `alembic_revision: d00f71c7` (equals pinned `d00f71c78f67`); TLS valid for the Demo domain.
- Independent UI verification (fresh browser context, Ukrainian default, Auditor demo role via the public login quick-fill; read-only): 16/16 PASS — Audit Log rows display row actions `Слід` (×7); the i18next object diagnostic, `[object Object]` and any raw `trace` key are absent before and after reload; clicking `Слід` opens the read-only dialog titled `Слід аудиту` with a coherent trace and no mutation controls; the English switch shows `Trace`. No forms submitted, no records created.

## 6. WP-DPR1-06 override-reconciliation disposition

The independent verification identified a release-gating observation (F1): the live Compose override still resolved the frontend to the pre-WP-DPR1-05 `:edbbc938` image, so the next Compose operation affecting the frontend would have reverted the fix. WP-DPR1-06 reconciled this with a one-line override change (frontend image pin → the WP-DPR1-05 candidate tag `forgemind-frontend:wp-dpr1-05-7b8af58`, which resolves to `sha256:ecae3e2f60f8…`), then recreated only the frontend container with the identical image. Post-reconciliation Compose resolution selects the WP-DPR1-05 frontend image; backend/worker pins remain intentionally `:edbbc938`; the rollback tag remains preserved and unused.

## 7. No database or persistent-service mutation

No application data, volume, or persistent service was changed by WP-DPR1-05 or WP-DPR1-06: no seed/reset/data mutation; backend, worker, PostgreSQL, Redis, reverse proxy and backup services retained identical container identities, images and zero restart counts across both actions; no Compose-wide up/down; no rollback. Only the frontend container was switched (WP-DPR1-05) and recreated with the same image (WP-DPR1-06).

## 8. Source-report identities and verdicts

| Report | SHA-256 | Lines | Bytes | Verdict |
|--------|---------|-------|-------|---------|
| `/tmp/wp-dpr1-05-pr138-independent-post-merge-verification-report.md` | `c23b245e3426e0e39eb94c9071891fdcb990deeea09e652b932484fd09813517` | 56 | 5661 | `POST-MERGE VERIFICATION PASSED — PR #138 INCORPORATED AND WP-DPR1-05 READY FOR DEMO DEPLOYMENT` |
| `/tmp/wp-dpr1-05-frontend-only-demo-deployment-report.md` | `67dd924c59aca8bc9e9ad0ca177c54aaa8494432ff091c9142b7e832898217c1` | 76 | 6294 | `FRONTEND-ONLY DEMO DEPLOYMENT PASSED — O2 NO LONGER REPRODUCES ON THE PUBLIC DEMO` |
| `/tmp/wp-dpr1-05-independent-frontend-deployment-verification-report.md` | `ebb59a40daaf7847bc7d400d6c9c38060781404538c09b86c4ae9704099779ec` | 57 | 6179 | `INDEPENDENT FRONTEND DEPLOYMENT VERIFICATION PASSED — WP-DPR1-05 DEPLOYED AND O2 CLOSED ON PUBLIC DEMO` |
| `/tmp/wp-dpr1-06-live-compose-override-reconciliation-report.md` | `038d2506f460e2e3a0a8525b1429959102b95e46495f104dde826135b04345e7` | 56 | 6906 | `LIVE COMPOSE OVERRIDE RECONCILED — FRONTEND PIN STABLE FOR RELEASE PREPARATION` |

## 9. Chronology note (non-blocking)

The independent verification report's stated window (14:50–15:20 UTC) overlaps the deployment report's stated window (14:44–15:05 UTC) on 2026-08-29. Neither report was altered; the overlap is not used as evidence about which document existed first. The independently observed post-switch running image, health and UI state stand as the verified current truth.

## 10. Boundary statement

Neither WP-DPR1-05 nor WP-DPR1-06 declared production acceptance, and neither created a Git tag or GitHub Release. This closure concerns the public portfolio Demo only; formal Release 1 production deployment remains NOT STARTED, and no deployment-gated acceptance test is marked PASS on Demo evidence alone. See [../demo-pre-release-1.md](../demo-pre-release-1.md) and [wp_dpr1_03a_live_demo_verification.md](wp_dpr1_03a_live_demo_verification.md).
