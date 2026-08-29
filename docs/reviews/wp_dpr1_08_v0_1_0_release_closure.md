# WP-DPR1-08 — ForgeMind v0.1.0 Portfolio Release Closure Record

Durable closure record for the ForgeMind portfolio release `v0.1.0` publication and its independent verification. Completed 2026-08-29.

## Publication facts

- Publication date: 2026-08-29 (Release published 2026-08-29T20:12:00Z).
- Source commit (tagged release tree): `a2ac7d563f678f98a00aaf998ef0d391ff75a781` — GitHub `main` at publication; the regular merge commit of PR #139 (WP-DPR1-07 portfolio release lifecycle reconciliation).
- Annotated tag: `v0.1.0`; tag object `8e91ada34227bb72ce5f46eb0c7e7697fdf0057e`; peels to `a2ac7d563f678f98a00aaf998ef0d391ff75a781`; annotation `ForgeMind v0.1.0 — Public Portfolio Release`.
- GitHub Release: ID `379089527`; title `ForgeMind v0.1.0 — Public Portfolio Release`; URL https://github.com/Tihonya/forgemind-ai-operations/releases/tag/v0.1.0 ; published 2026-08-29T20:12:00Z; draft false; prerelease false; assets 0.

## Source reports and identities

- Publication report `/tmp/wp-dpr1-08-v0.1.0-publication-report.md`: SHA-256 `a964d92991833efc613c7ea009766c77c95be7f8e5927e57fb76daa9868a7d43`, 63 lines, 5537 bytes; verdict: `FORGEMIND v0.1.0 PUBLISHED — FIRST PUBLIC PORTFOLIO RELEASE COMPLETE`.
- Independent publication verification `/tmp/wp-dpr1-08-v0.1.0-independent-publication-verification-report.md`: SHA-256 `98974fb4b70fd87fe46b5fce4d5a761b4387f4084a598cf297402df411081f91`, 52 lines, 5827 bytes; verdict: `INDEPENDENT RELEASE VERIFICATION PASSED — FORGEMIND v0.1.0 IS PUBLIC AND WP-DPR1-08 COMPLETE`.
- Release-notes polish report `/tmp/wp-dpr1-08-v0.1.0-release-notes-polish-report.md`: SHA-256 `9df117dcb99680615ad70084beae44e8916e2fdb31773b5d68d0efe7455bcfea`, 35 lines, 2904 bytes; verdict: `v0.1.0 RELEASE NOTES POLISHED — PUBLIC RELEASE REMAINS VERIFIED`.
- Final Release-body identity (post-polish): SHA-256 `6aab0b194e699ef3f62cd4f5ddea98048af1e580f2c77fcd3786aca3d3cb98f0`, 54 lines, 4904 bytes.

## Public Demo disposition

- Public Demo: https://demo.forgemind-ai.tech/ — HTTP 200 at independent verification; `/health` reported `status: healthy` with backend, postgresql, redis and worker ok and `alembic_revision: d00f71c7`.

## Mixed provenance

- The public Demo runs the previously verified backend and worker images from candidate `edbbc938` and the corrected frontend built from `7b8af58db8ed9a953fb5e7cbcdcbba7fdb30d8ad`; the exact mixed provenance is recorded in [wp_dpr1_05_06_demo_frontend_closure.md](wp_dpr1_05_06_demo_frontend_closure.md).

## Boundary and immutable tag

- The published Release is a public portfolio release, not formal production Release 1 acceptance: Release 1 remains NOT READY / NOT DEPLOYED; staging and production remain NOT STARTED. The publication performed no deployment and no credential rotation.
- Tag `v0.1.0` remains permanently pinned to the independently reviewed release commit `a2ac7d563f678f98a00aaf998ef0d391ff75a781`. The repository closure commit that adds this record necessarily occurs after the immutable `v0.1.0` tag and is therefore not part of the tagged source tree; the tag is not moved or recreated to include this documentation. This is correct release hygiene, not version drift.

## Final status

`WP-DPR1-01 THROUGH WP-DPR1-08 COMPLETE — FORGEMIND v0.1.0 PUBLIC PORTFOLIO RELEASE PUBLISHED AND VERIFIED`
