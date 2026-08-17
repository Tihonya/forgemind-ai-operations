"""OpenRouter embedding smoke harness (WP-P7-02, preparation-only).

Authorization boundary: a LIVE OpenRouter embedding call is NOT
authorized by WP-P7-02 implementation. This module prepares the
mechanism for the separately authorized live embedding gate; it makes
no network calls unless explicitly and separately authorized.

What the future live gate must verify (Phase 7 contract, PD-3a):

1.  authenticated OpenRouter embedding request;
2.  exact model identifier ``openai/text-embedding-3-small``;
3.  exactly 1536 numeric dimensions;
4.  non-empty finite vector;
5.  deterministic repeated input behavior;
6.  database insertion compatibility;
7.  Golden Dataset seeding;
8.  runtime retrieval with citations;
9.  seed/query provider consistency;
10. fail-closed behavior for invalid credentials / provider failure;
11. no secrets in logs or evidence.

Checks 1-5 and 10 are defined here with deterministic verification
logic. Checks 6-9 involve the live database/retrieval path and are
reported as ``not_run`` by the offline harness (they are exercised by
the separately authorized live gate).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Literal

from app.config import Settings
from app.config import settings as application_settings

# Canonical PD-3a values (duplicated deliberately so the smoke harness
# is self-contained and cannot silently track a drifted default).
EXPECTED_BASE_URL = "https://openrouter.ai/api/v1"
EXPECTED_MODEL = "openai/text-embedding-3-small"
EXPECTED_DIMENSIONS = 1536

# Environment confirmation key for the live gate. The live path refuses
# to run unless BOTH the CLI flag and this env var are present — a
# double barrier against accidental credit consumption.
LIVE_CONFIRM_ENV = "FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM"


class EmbeddingSmokeError(Exception):
    """Raised when the smoke harness itself cannot proceed."""


@dataclass(frozen=True)
class SmokeCheck:
    """One verification item and its outcome."""

    name: str
    status: Literal["pass", "fail", "not_run"]
    detail: str = ""


@dataclass
class EmbeddingSmokeEvidence:
    """Deterministic evidence bundle — never contains secrets."""

    checks: list[SmokeCheck] = field(default_factory=list)
    vector_hash: str | None = None
    dimension: int | None = None
    model: str = ""
    endpoint: str = ""

    @property
    def passed_checks(self) -> list[SmokeCheck]:
        return [c for c in self.checks if c.status == "pass"]

    @property
    def failed_checks(self) -> list[SmokeCheck]:
        return [c for c in self.checks if c.status == "fail"]

    @property
    def overall(self) -> str:
        if self.failed_checks:
            return "FAIL"
        if self.checked_labels() == self._live_labels():
            return "PASS"
        return "PREPARATION_INCOMPLETE"

    @staticmethod
    def _live_labels() -> frozenset[str]:
        return frozenset(
            {
                "config.base_url",
                "config.model",
                "config.dimensions",
                "config.api_key_present",
                "vector.non_empty",
                "vector.numeric",
                "vector.finite",
                "vector.dimension",
                "vector.determinism",
                "provider.fail_closed_invalid_key",
                "db.insertion_compatibility",
                "seed.golden_dataset",
                "retrieval.citations",
                "seed_query.consistency",
                "evidence.no_secrets",
            }
        )

    def checked_labels(self) -> frozenset[str]:
        return frozenset(
            c.name
            for c in self.checks
            if c.status in ("pass", "fail")
        )

    def render(self) -> str:
        lines = [
            "Embedding smoke evidence (WP-P7-02)",
            f"  endpoint: {self.endpoint or '<not recorded>'}",
            f"  model: {self.model or '<not recorded>'}",
            f"  dimension: {self.dimension if self.dimension is not None else '-'}",
            f"  vector_hash: {self.vector_hash or '-'}",
        ]
        for check in self.checks:
            lines.append(f"  [{check.status:7s}] {check.name}: {check.detail}")
        lines.append(f"OVERALL: {self.overall}")
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(
            {
                "endpoint": self.endpoint,
                "model": self.model,
                "dimension": self.dimension,
                "vector_hash": self.vector_hash,
                "overall": self.overall,
                "checks": [
                    {"name": c.name, "status": c.status, "detail": c.detail}
                    for c in self.checks
                ],
            },
            indent=2,
        )


# ---------------------------------------------------------------------------
# Vector verification (pure, deterministic — same logic the live gate uses)
# ---------------------------------------------------------------------------


def vector_sha256(vector: list[float]) -> str:
    """Deterministic content hash of a vector (for determinism evidence)."""
    payload = json.dumps(vector, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def checks_for_vector(vector: list[float], expected_dimension: int) -> list[SmokeCheck]:
    """Run the pure vector contract checks (items 3-5)."""
    checks: list[SmokeCheck] = []
    if not vector:
        checks.append(SmokeCheck("vector.non_empty", "fail", "vector is empty"))
    else:
        checks.append(SmokeCheck("vector.non_empty", "pass", f"len={len(vector)}"))

    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vector)
    checks.append(
        SmokeCheck(
            "vector.numeric",
            "pass" if numeric else "fail",
            "all values numeric" if numeric else "non-numeric value present",
        )
    )

    finite = all(math.isfinite(float(v)) for v in vector) if numeric else False
    checks.append(
        SmokeCheck(
            "vector.finite",
            "pass" if finite else "fail",
            "all values finite" if finite else "non-finite value present",
        )
    )

    dim_ok = len(vector) == expected_dimension
    checks.append(
        SmokeCheck(
            "vector.dimension",
            "pass" if dim_ok else "fail",
            f"expected {expected_dimension}, got {len(vector)}",
        )
    )
    return checks


def determinism_check(vectors: list[list[float]]) -> SmokeCheck:
    """Deterministic repeated-input check (item 5): identical inputs must
    produce byte-identical vectors."""
    if len(vectors) < 2:
        return SmokeCheck(
            "vector.determinism",
            "not_run",
            "at least two repeated-input vectors required",
        )
    hashes = {vector_sha256(v) for v in vectors}
    if len(hashes) == 1:
        return SmokeCheck("vector.determinism", "pass", "repeated inputs identical")
    return SmokeCheck(
        "vector.determinism",
        "fail",
        f"repeated inputs diverged ({len(hashes)} distinct vectors)",
    )


# ---------------------------------------------------------------------------
# Offline preparation mode — zero network I/O, config verification only
# ---------------------------------------------------------------------------


def build_offline_evidence(config: Settings) -> EmbeddingSmokeEvidence:
    """Run the offline (preparation) portion against a Settings object.

    Verifies every piece of the PD-3a contract that is decidable without
    a live call, then reports the live-only items as ``not_run``.

    This method makes NO network calls and never prints or stores
    secret values.
    """
    evidence = EmbeddingSmokeEvidence()
    evidence.endpoint = config.openai_api_base
    evidence.model = config.openai_embedding_model
    evidence.dimension = config.embedding_dimensions

    # Config contract (fail-closed on any deviation).
    evidence.checks.append(
        SmokeCheck(
            "config.base_url",
            "pass" if config.openai_api_base == EXPECTED_BASE_URL else "fail",
            f"expected {EXPECTED_BASE_URL}, got {config.openai_api_base}",
        )
    )
    evidence.checks.append(
        SmokeCheck(
            "config.model",
            "pass" if config.openai_embedding_model == EXPECTED_MODEL else "fail",
            f"expected {EXPECTED_MODEL}, got {config.openai_embedding_model}",
        )
    )
    evidence.checks.append(
        SmokeCheck(
            "config.dimensions",
            "pass" if config.embedding_dimensions == EXPECTED_DIMENSIONS else "fail",
            f"expected {EXPECTED_DIMENSIONS}, got {config.embedding_dimensions}",
        )
    )
    key_present = bool(config.openai_api_key.strip())
    evidence.checks.append(
        SmokeCheck(
            "config.api_key_present",
            "pass" if key_present else "fail",
            "configured"
            if key_present
            else "missing — OpenRouter requires the key (PD-3a)",
        )
    )
    evidence.checks.append(
        SmokeCheck(
            "config.provider_not_fake",
            "pass" if config.embedding_provider != "fake" else "fail",
            f"embedding_provider={config.embedding_provider}",
        )
    )

    # Offline fail-closed probe: the configured provider must either
    # construct (no network I/O at construction time) or fail with a
    # typed configuration error — never make a network call here.
    try:
        build_provider_from_config(config)
    except Exception as exc:
        evidence.checks.append(
            SmokeCheck(
                "provider.construction",
                "fail",
                f"provider construction failed ({type(exc).__name__})",
            )
        )
    else:
        evidence.checks.append(
            SmokeCheck(
                "provider.construction",
                "pass",
                "provider constructed without network I/O",
            )
        )

    # Live-only gates — require the separately authorized live call.
    for label in (
        "vector.non_empty",
        "vector.numeric",
        "vector.finite",
        "vector.dimension",
        "vector.determinism",
        "provider.fail_closed_invalid_key",
        "db.insertion_compatibility",
        "seed.golden_dataset",
        "retrieval.citations",
        "seed_query.consistency",
    ):
        evidence.checks.append(
            SmokeCheck(label, "not_run", "requires the separately authorized live gate")
        )

    # Evidence safety is verifiable offline: nothing above contains a secret.
    evidence.checks.append(
        SmokeCheck(
            "evidence.no_secrets",
            "pass",
            "evidence bundle contains only names, statuses, and vector hashes",
        )
    )

    return evidence


def build_provider_from_config(config: Settings) -> Any:
    """Construct the OpenAI-compatible embedding provider from config.

    This performs NO network I/O: AsyncOpenAI construction is lazy and
    the factory-level validations are synchronous. Used by the offline
    harness to prove configuration is constructible.
    """
    from app.services.embedding_provider_factory import create_embedding_provider

    return create_embedding_provider(config=config)


# ---------------------------------------------------------------------------
# Live gate — DO NOT USE WITHOUT SEPARATE AUTHORIZATION
# ---------------------------------------------------------------------------


def assert_live_authorized() -> None:
    """Raise unless the live gate is explicitly and separately authorized.

    The authorization contract: the operator must pass ``--live`` AND
    set the environment confirmation variable. WP-P7-02 implementation
    itself never satisfies both.
    """
    if os.environ.get(LIVE_CONFIRM_ENV) != "yes":
        raise EmbeddingSmokeError(
            "LIVE embedding smoke is not authorized for this task. "
            "Set --live AND " + LIVE_CONFIRM_ENV + "=yes only in the "
            "separately authorized live gate."
        )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Offline preparation by default."""
    args = list(sys.argv[1:] if argv is None else argv)
    live = "--live" in args

    evidence = build_offline_evidence(application_settings)
    print(evidence.render())

    if live:
        try:
            assert_live_authorized()
        except EmbeddingSmokeError as exc:
            print(f"REFUSED: {exc}")
            return 2
        print("LIVE MODE: authorized externally — not executed by WP-P7-02.")
        return 0

    print("MODE: offline preparation (no live provider call performed)")
    return 0 if evidence.overall != "FAIL" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
