# Live Demo Independent Verification — Durable Record (WP-DPR1-03A)

**Verification date (UTC):** 2026-08-29
**Verified candidate (GitHub `main`):** `edbbc93894e74689e54c22056ac3e0b56880a72a`
**Live Demo:** https://demo.forgemind-ai.tech/
**Verifying package:** WP-DPR1-03A (independent live verification; not deployment, remediation, lifecycle reconciliation, or Product Owner acceptance)
**Deployment package:** WP-DPR1-02A (2026-08-27, in-place Compose update, one controlled reset)

## Deployed application image IDs (verified exact)

| Service | Image ID |
|---------|----------|
| backend | `sha256:7e1b21c263b710beecc13028f357adf030d2605568266f4873a5c29f6056ef51` |
| worker | `sha256:58d156b611c9b478fd3a59d41c1a5714dc002363ea3f19b700004bef4796c730` |
| frontend | `sha256:9a0de18f9f5524b6eef1dc5de7f9533851993527f340caef65ff8906859bc3a5` |

Support services matched the deployment report as-found (backup `cf78e766…`, caddy `5f5c8640…`, postgres `ccc6e83d…`, redis `ff02b58f…`); no identity drift.

## Results

- **Health and migrations — PASS.** 7/7 services running and healthy (caddy has no healthcheck by design); HTTPS `/`, `/login`, `/health` → 200 with clean TLS; `/health` JSON: backend ok, postgresql ok, redis ok, worker ok, `alembic_revision d00f71c7` (expected head). No traceback/fatal/critical lines in the bounded recent-log review.
- **Primary approval/task journey — PASS.** `manager.demo` opened RISK-001, reviewed AI analysis + recommendation, submitted via «Передати на погодження» without any manual UUID entry; `procurement.demo` approved in the Approval Center; created the linked procurement task (task `72de7a01-9970-400d-b248-1117eccc5205`, linked to approval request `f5ff306f-5588-45c0-9221-e7d71001daaf`). Duplicate prevention verified: UI button removed after creation; repeated submit refused (409 `approval_request_duplicate`); direct API replay idempotent (same task id).
- **Rejection path — PASS.** `manager.demo` submitted RISK-002 (request `12abd593-73bf-4903-9049-4fc7cf7a028f`); `procurement.demo` rejected it with a recorded reason. The rejected state survives reload, remains visible to the initiator, and is recorded in the immutable audit log.
- **Role boundaries — PASS.** `manager.demo` direct approve/reject attempts → 403, no approve/reject/create buttons in its UI; `auditor.demo` direct task creation → 403, read-only audit surface stating events are immutable via the interface; separate clean contexts per role, HttpOnly cookie token, no cross-role leakage.
- **Ukrainian / responsive / basic accessibility — PASS.** Ukrainian-first interface (`<html lang="uk">`), localized statuses and date formats across all journey screens; desktop 1440×900 without clipping; mobile 390×844 without horizontal overflow, reachable 44 px CTA; keyboard-completable login with visible focus. Concise check only — not a full WCAG audit.

## Observations (recorded, not remediated)

- **O1 (cosmetic):** some Golden Dataset-owned AI text remains English inside the Ukrainian interface (e.g. «Резюме ШІ: 8-unit shortage…»). Dataset-owned content; does not obstruct the walkthrough.
- **O2 (cosmetic):** some Audit Log detail rows may render the raw i18n fallback string `key 'trace (uk)' returned an object instead of string.`; the event data itself renders correctly. Candidate for a later small code-remediation package.
- **O3 (by design):** rejected requests are intentionally unavailable to the deciding Procurement Specialist (backend role scoping) while remaining visible to the initiator and the immutable audit log.

## Source report identity

- Full report: `/tmp/wp-dpr1-03a-concise-independent-live-demo-verification-report.md`
- SHA-256: `10d82ba784319c26e0896281c3ea83bb64ca40cb54ab25fe397fbfe5ccc6ed9b` (98 lines, 9705 bytes — both match the expected identity)
- Screenshots: `/tmp/wp-dpr1-03a-screenshots/` (8 images, no secrets; three published in [docs/assets/demo/](../assets/demo/))

## Verdict (exact, from the verified report)

`INDEPENDENT LIVE DEMO VERIFICATION PASSED — DOCUMENTATION FINALIZATION MAY BEGIN`

This record does not claim Product Owner acceptance. The verified Demo remains distinct from formal Release 1 (NOT READY / NOT DEPLOYED), staging and production (NOT STARTED), and no GitHub Release has been published.
