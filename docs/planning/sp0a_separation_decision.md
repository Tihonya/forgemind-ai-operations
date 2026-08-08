# SP-0A — Repository Separation Decision

**Status:** APPROVED (Option C + repository name only; SP-0B NOT GRANTED)
**Date:** 2026-08-08
**Author:** Agent (principal engineer), prepared for Manager and Product Owner review
**Authoritative baseline:** `d8bafa55a50644101b790b4a7eab1408bac3d188` (origin/main at time of drafting)
**Assessment path:** `docs/reviews/sp0_repository_separation_assessment.md`
**Assessment SHA-256:** `05025ff7f417f23d5a83d9725cebba8791ba2e71bd326cd932b643e70640cba9`
**Assessment lines:** 1115

---

## Document status

This document records the accepted Product Owner decision for Option C and
the repository name `forgemind-agent-runtime`.

Approval is strictly limited to those two decisions. This document does not
authorize:

- SP-0B,
- the creation of the Runtime repository,
- any implementation, genericization, or code movement,
- any change to the ForgeMind Product Source of Truth,
- any change to the Decision Log.

Every implementation phase requires separate explicit authorization.

---

## 1. Decision question

Should the Agent Loop Runtime (currently embedded in the ForgeMind Product
repository under `scripts/agent-loop/` and `.agent-loop/*/SCHEMA.md`) be
separated into an independent repository so that it can evolve as a generic
AI-assisted engineering runtime, while ForgeMind continues as a separate
Product repository that consumes it?

---

## 2. Approved decision

Option C from the assessment is approved. Under approved Option C, once the
applicable phase is separately authorized:

- A new Runtime repository will be created.
- Runtime implementation and schemas will be **copied** (not moved) into the
  new repository.
- The existing ForgeMind copy will be retained through the normalized parity
  gate (SP-3) and the current-capability integration exercise (SP-4).
- The ForgeMind copy will be removed only at the explicit removal gate (SP-5).

This preserves provenance, keeps ForgeMind deployment independent of the
separation track, and provides a fallback copy until parity and integration
are proven.

---

## 3. Approved repository name

**Approved name:** `forgemind-agent-runtime`

Approval of the name does not authorize repository creation.

**Repository-name availability observation (read-only):**
As of 2026-08-08, the GitHub repository `Tihonya/forgemind-agent-runtime`
does not exist. The query
`gh repo view Tihonya/forgemind-agent-runtime` returned "Could not resolve
to a Repository." This is an observation only — no repository was created,
reserved, or modified.

Repository creation remains outside SP-0A and is explicitly excluded from
this task.

---

## 4. Ownership boundary

### 4.1 Product-owned artifacts that remain in the ForgeMind repository

- `backend/`, `frontend/`, `infra/`
- `forgemind_project_source_of_truth/`
- `HERMES.md`
- `Makefile`, `docker-compose.yml`, `docker-compose.dev.yml`
- `.env.example`, `README.md`
- `.github/workflows/ci-*.yml`
- `.agent-loop/project.json` — Product integration configuration
- `.agent-loop/gates.json` — Product gate configuration
- `scripts/agent-loop/templates/story-prd.json` — ForgeMind-specific story
  template
- All historical planning documents under `docs/planning/`

### 4.2 Runtime-owned artifacts that are copied according to the later approved migration manifest

- `scripts/agent-loop/lib/*.py` (core runtime implementation)
- `scripts/agent-loop/lib/*.sh` (bash helpers)
- `scripts/agent-loop/*.sh` (entry points and `config.sh`; initially copied
  unchanged, with `config.sh` genericized only in SP-2)
- `scripts/agent-loop/tests/` (Runtime-owned test inventory, exact scope
  determined in SP-0B)
- `scripts/agent-loop/README.md`
- `.agent-loop/failure-context/SCHEMA.md`
- `.agent-loop/review/SCHEMA.md`
- `.agent-loop/review-adapter/SCHEMA.md`
- `.agent-loop/repair/SCHEMA.md`
- `.agent-loop/repair-adapter/SCHEMA.md`
- `.agent-loop/manifests/SCHEMA.md`

### 4.3 Protected artifacts

- `.agent-loop/project.json` and `.agent-loop/gates.json` remain Product
  integration configuration consumed by the external Runtime.
- `HERMES.md` remains Product-owned. The Runtime derives its own governance
  document.
- The ForgeMind Product Source of Truth (`forgemind_project_source_of_truth/`)
  is protected and is not moved, copied, or referenced as a migration target.

---

## 5. Non-negotiable invariants

1. **COPY before removal.** No Runtime artifact is removed from ForgeMind
   before the external copy is in place and verified.
2. **No MOVE and no removal before SP-5.** The ForgeMind copy is retained
   through SP-1A, SP-1B, SP-2, SP-3, and SP-4. SP-5 is the first phase in
   which removal may occur.
3. **No genericization during SP-1A or SP-1B.** The bootstrap copy is a
   provenance-preserving blob equivalence. Genericization belongs to SP-2.
4. **Normalized semantic parity is required in SP-3.** The external Runtime
   must demonstrate semantic equivalence with the ForgeMind copy against the
   defined harness scenarios.
5. **A controlled mock-actor integration exercise is required in SP-4.** The
   external Runtime must demonstrate supervised integration with ForgeMind
   using the current-capability mock actors (not real-agent production
   integration).
6. **Product deployment must never depend on the Runtime repository.** The
   ForgeMind Product continues to work with its internal copy even if the
   Runtime repository has issues.
7. **Real-agent production integration remains a separate track.** Mock-actor
   exercises do not imply real-agent deployment readiness.

---

## 6. Proposed phase sequence from the assessment

The assessment proposes the following ordered sequence, subject to Product
Owner approval. Listing a phase here does not authorize its execution.
Every phase requires separate explicit authorization, and no phase may
begin before the preceding phase's exit criteria are satisfied and its
evidence is accepted. SP-0B authorization is currently NOT GRANTED.

| Phase | Purpose |
|-------|---------|
| SP-0B | Produce the exact migration manifest and the Runtime test inventory. |
| SP-1A | Provenance-preserving copy of Runtime-owned artifacts to the new repository. |
| SP-1B | Establish an independent test and CI baseline in the Runtime repository. |
| SP-2  | External configuration and genericization (remove ForgeMind-specific assumptions). |
| SP-3  | Cross-repository normalized semantic parity. |
| SP-4  | Supervised current-capability integration exercise using mock actors. |
| SP-5  | Explicit removal gate — the first phase in which removal from ForgeMind may occur. |

---

## 7. Consequences and trade-offs

### 7.1 Temporary bounded duplication

The Runtime implementation and schemas exist in both repositories during
SP-1A through SP-4. Duplication is bounded by the phase sequence and ends
no earlier than SP-5.

### 7.2 Independent Runtime evolution

After SP-2, the Runtime repository can evolve, be reused against other
target projects, and be versioned independently. ForgeMind development is
not gated by Runtime evolution.

### 7.3 Additional cross-repository coordination

Two repositories, two CI pipelines, and an integration contract require
coordination. The project-configuration bundle (`.agent-loop/project.json`
and `.agent-loop/gates.json` in ForgeMind) is the coupling point.

### 7.4 Compatibility fallback

The ForgeMind copy remains available as a fallback until SP-5. If the
external Runtime has issues, ForgeMind continues with its internal copy.
This rollback property is the central safety advantage of Option C over
Option B.

---

## 8. Evidence and rationale

The rationale for this decision rests on the merged assessment:

- No direct Agent Loop references were found in inspected Product
  application paths (`backend/`, `frontend/`, `infra/`) at baseline
  `d8bafa55a50644101b790b4a7eab1408bac3d188`.
- The extraction is primarily unidirectional: the Runtime contains all
  identified coupling; the Product does not import Runtime code.
- Genericization scope is bounded: 3 files require structural changes,
  9 files are portable as-is, and 2 files are test-only.
- Option C provides a provenance-preserving overlap, a parity gate, and a
  separate removal gate. This is the lowest-risk path among the three
  options assessed.

This decision document does **not** reproduce the full 1115-line assessment.
Readers should consult
`docs/reviews/sp0_repository_separation_assessment.md` for the full
evidence.

Verified evidence (assessment findings, coupling matrix, portability
matrix, ownership classification) is distinguished from implementation
phases (separately authorized) and approved decisions (Option C adoption
and repository name) throughout this document.

---

## 9. Risks and rollback principles

- **Pre-removal stages are operationally reversible.** SP-0A, SP-0B, SP-1A,
  SP-1B, and SP-2 produce artifacts that can be abandoned without affecting
  Product deployment.
- **Pre-SP-5 Runtime failures do not affect Product deployment.** ForgeMind
  continues to use its internal copy.
- **SP-5 is the first removal phase.** It requires separate Product Owner
  approval after SP-3 parity and SP-4 integration evidence are accepted.
- **Migration risk is bounded by the parity gate.** If the external Runtime
  fails to demonstrate parity, the separation may be halted at SP-3 without
  removing anything from ForgeMind.

---

## 10. Explicit exclusions

This document does not authorize and the SP-0A task does not perform:

- Any implementation.
- Creation of `forgemind-agent-runtime` or any other repository.
- Movement or copying of Runtime files or schemas.
- Modification of the ForgeMind Product Source of Truth.
- Modification of the Decision Log.
- Entry of this decision into `08_DECISION_LOG.md` (that entry requires
  separate, explicit Product Owner action).
- Execution of SP-0B.
- Real-agent integration work.

---

## 11. Approval block

Product Owner decision:
APPROVED

Option:
Option C — APPROVED

Approved repository name:
forgemind-agent-runtime — APPROVED

SP-0B authorization:
NOT GRANTED

Approval date:
2026-08-08

Approved by:
Product Owner (toha)

---

## 12. References

- Assessment: `docs/reviews/sp0_repository_separation_assessment.md`
  (merged via PR #59, merge commit `d8bafa55a50644101b790b4a7eab1408bac3d188`)
- Authoritative baseline: `d8bafa55a50644101b790b4a7eab1408bac3d188`
- Product Source of Truth: `forgemind_project_source_of_truth/`
- Product governance contract: `HERMES.md`
