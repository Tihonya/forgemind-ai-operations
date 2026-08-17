"""Unit tests for the OpenRouter embedding smoke harness (WP-P7-02).

The implementation task is preparation-only: these tests validate every
offline-decidable check plus the live-authorization barrier. NO live
provider call occurs anywhere in this suite.
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from app.config import Settings
from app.ops.embedding_smoke import (
    EXPECTED_BASE_URL,
    EXPECTED_DIMENSIONS,
    EXPECTED_MODEL,
    EmbeddingSmokeError,
    EmbeddingSmokeEvidence,
    SmokeCheck,
    assert_live_authorized,
    build_offline_evidence,
    checks_for_vector,
    determinism_check,
    vector_sha256,
)


def _config(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "production",
        "embedding_provider": "openai",
        "openai_api_key": "sr-or-smoke-key",
        "openai_api_base": EXPECTED_BASE_URL,
        "openai_embedding_model": EXPECTED_MODEL,
        "embedding_dimensions": EXPECTED_DIMENSIONS,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Vector checks — pure
# ---------------------------------------------------------------------------


class TestVectorChecks:
    def test_valid_vector_passes_all_checks(self) -> None:
        vector = [0.1] * EXPECTED_DIMENSIONS
        checks = checks_for_vector(vector, EXPECTED_DIMENSIONS)
        assert all(c.status == "pass" for c in checks), checks

    def test_wrong_dimension_fails(self) -> None:
        vector = [0.1] * 128
        checks = checks_for_vector(vector, EXPECTED_DIMENSIONS)
        dim_check = next(c for c in checks if c.name == "vector.dimension")
        assert dim_check.status == "fail"

    def test_empty_vector_fails(self) -> None:
        checks = checks_for_vector([], EXPECTED_DIMENSIONS)
        non_empty = next(c for c in checks if c.name == "vector.non_empty")
        assert non_empty.status == "fail"

    def test_non_numeric_fails(self) -> None:
        vector: list[float] = cast(list[float], [0.1, "not-a-number"])
        checks = checks_for_vector(vector, 2)
        numeric = next(c for c in checks if c.name == "vector.numeric")
        assert numeric.status == "fail"

    def test_non_finite_fails(self) -> None:
        vector = [0.1, math.nan]
        checks = checks_for_vector(vector, 2)
        finite = next(c for c in checks if c.name == "vector.finite")
        assert finite.status == "fail"

    def test_deterministic_vectors_pass(self) -> None:
        v = [0.5, -0.25, 0.75]
        check = determinism_check([v, v, v])
        assert check.status == "pass"

    def test_divergent_vectors_fail(self) -> None:
        check = determinism_check([[0.0], [1.0]])
        assert check.status == "fail"

    def test_insufficient_vectors_not_run(self) -> None:
        check = determinism_check([[0.0]])
        assert check.status == "not_run"

    def test_sha256_is_stable(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert vector_sha256(v) == vector_sha256(list(v))
        assert vector_sha256(v) != vector_sha256([1.0, 2.0, 3.1])


# ---------------------------------------------------------------------------
# Offline evidence
# ---------------------------------------------------------------------------


class TestOfflineEvidence:
    def test_canonical_configuration_checks_pass(self) -> None:
        evidence = build_offline_evidence(_config())
        config_checks = [c for c in evidence.checks if c.name.startswith("config.")]
        assert config_checks, "config checks missing"
        assert all(c.status == "pass" for c in config_checks), config_checks

    def test_live_only_checks_are_not_run_offline(self) -> None:
        evidence = build_offline_evidence(_config())
        labels = {c.name for c in evidence.checks if c.status == "not_run"}
        assert "vector.non_empty" in labels
        assert "retrieval.citations" in labels
        assert "seed.golden_dataset" in labels

    def test_offline_evidence_never_contains_secret(self) -> None:
        evidence = build_offline_evidence(_config(openai_api_key="sk-very-secret"))
        rendered = evidence.render()
        assert "sk-very-secret" not in rendered
        assert "very-secret" not in rendered

    def test_wrong_base_url_fails(self) -> None:
        evidence = build_offline_evidence(
            _config(openai_api_base="https://api.openai.com/v1")
        )
        check = next(c for c in evidence.checks if c.name == "config.base_url")
        assert check.status == "fail"

    def test_wrong_model_fails(self) -> None:
        evidence = build_offline_evidence(
            _config(openai_embedding_model="text-embedding-ada-002")
        )
        check = next(c for c in evidence.checks if c.name == "config.model")
        assert check.status == "fail"

    def test_wrong_dimension_fails(self) -> None:
        evidence = build_offline_evidence(_config(embedding_dimensions=768))
        check = next(c for c in evidence.checks if c.name == "config.dimensions")
        assert check.status == "fail"

    def test_missing_key_fails_closed(self) -> None:
        evidence = build_offline_evidence(_config(openai_api_key=""))
        key_check = next(
            c for c in evidence.checks if c.name == "config.api_key_present"
        )
        assert key_check.status == "fail"
        # Fail-closed at the configuration layer: overall evidence is
        # FAIL and the live gate can never run from this state.
        # (Provider construction itself succeeds with the SDK sentinel
        # for non-official endpoints — an accepted existing factory
        # behavior; the missing key is rejected at the first live call
        # with a 401 classified as permanent.)
        assert evidence.overall == "FAIL"

    def test_fake_provider_fails(self) -> None:
        evidence = build_offline_evidence(_config(embedding_provider="fake"))
        check = next(
            c for c in evidence.checks if c.name == "config.provider_not_fake"
        )
        assert check.status == "fail"


# ---------------------------------------------------------------------------
# Remediation F-4: verdict semantics (synthetic evidence, offline)
# ---------------------------------------------------------------------------
# Synthetic bundles are built directly from the dataclass — no live
# provider call, no network I/O. They prove the verdict algebra.

_REQUIRED_LABELS = EmbeddingSmokeEvidence._live_labels()  # noqa: SLF001


def _all_required_pass() -> EmbeddingSmokeEvidence:
    evidence = EmbeddingSmokeEvidence()
    evidence.checks = [SmokeCheck(name, "pass", "synthetic") for name in _REQUIRED_LABELS]
    return evidence


class TestVerdictSemantics:
    def test_all_mandatory_passed_yields_pass(self) -> None:
        evidence = _all_required_pass()
        assert evidence.overall == "PASS"

    def test_pass_stays_reachable_with_supplementary_checks(self) -> None:
        """Extra supplementary PASS checks must NOT break PASS."""
        evidence = _all_required_pass()
        evidence.checks.append(SmokeCheck("config.provider_not_fake", "pass", "x"))
        evidence.checks.append(SmokeCheck("provider.construction", "pass", "x"))
        assert evidence.overall == "PASS"

    def test_offline_evidence_without_live_checks_is_preparation_incomplete(
        self,
    ) -> None:
        """Offline-only evidence (live items not_run) → PREPARATION_INCOMPLETE."""
        evidence = build_offline_evidence(_config())
        assert evidence.overall == "PREPARATION_INCOMPLETE"
        # And the failing-key offline case is FAIL (already covered in
        # TestOfflineEvidence.test_missing_key_fails_closed).

    def test_one_mandatory_failed_yields_fail(self) -> None:
        evidence = _all_required_pass()
        # Flip one mandatory check to fail.
        flipped: list[SmokeCheck] = []
        for check in evidence.checks:
            if check.name == "vector.dimension":
                flipped.append(SmokeCheck(check.name, "fail", "wrong dimension"))
            else:
                flipped.append(check)
        evidence.checks = flipped
        assert evidence.overall == "FAIL"

    def test_one_mandatory_missing_yields_preparation_incomplete(self) -> None:
        evidence = _all_required_pass()
        # Remove one mandatory label entirely (not executed).
        evidence.checks = [
            c for c in evidence.checks if c.name != "retrieval.citations"
        ]
        assert evidence.overall == "PREPARATION_INCOMPLETE"

    def test_failure_of_supplementary_check_yields_fail(self) -> None:
        """A failed supplementary (non-required) check is still a failure."""
        evidence = _all_required_pass()
        evidence.checks.append(SmokeCheck("config.provider_not_fake", "fail", "fake"))
        assert evidence.overall == "FAIL"

    def test_exit_codes_strict(self, monkeypatch: Any) -> None:
        from app.ops import embedding_smoke

        assert embedding_smoke.EXIT_CODES["PASS"] == 0
        assert embedding_smoke.EXIT_CODES["FAIL"] == 1
        assert embedding_smoke.EXIT_CODES["PREPARATION_INCOMPLETE"] == 2
        assert embedding_smoke.EXIT_CODES["REFUSED"] == 3
        # The offline default evidence is PREPARATION_INCOMPLETE under a
        # canonical (key-present, live-items-not-run) configuration — a
        # strict gate must treat that state as non-zero (exit 2).
        canonical = _config()
        monkeypatch.setattr(embedding_smoke, "application_settings", canonical)
        assert (
            embedding_smoke.main(["offline"])
            == embedding_smoke.EXIT_CODES["PREPARATION_INCOMPLETE"]
        )


# ---------------------------------------------------------------------------
# CLI exit-code contract (remediation R-3): PASS=0 FAIL=1
# PREPARATION_INCOMPLETE=2 REFUSED=3 — including the authorized-`--live`
# path, which performs NO live provider execution and therefore exits by
# the same evidence verdict (2), never 0.
# ---------------------------------------------------------------------------


class TestCliExitCodes:
    def test_offline_fail_exits_fail(self, monkeypatch: Any) -> None:
        from app.ops import embedding_smoke

        monkeypatch.setattr(
            embedding_smoke, "application_settings", _config(openai_api_key="")
        )
        assert embedding_smoke.main(["offline"]) == 1

    def test_offline_incomplete_exits_preparation_incomplete(
        self, monkeypatch: Any
    ) -> None:
        from app.ops import embedding_smoke

        monkeypatch.setattr(embedding_smoke, "application_settings", _config())
        # Canonical offline evidence (key present, live items not_run) is
        # PREPARATION_INCOMPLETE -> exit 2.
        assert (
            embedding_smoke.main(["offline"])
            == embedding_smoke.EXIT_CODES["PREPARATION_INCOMPLETE"]
        )

    def test_synthetic_pass_evidence_exits_pass(self, monkeypatch: Any) -> None:
        import app.ops.embedding_smoke as embedding_smoke

        monkeypatch.setattr(
            embedding_smoke,
            "build_offline_evidence",
            lambda config: _all_required_pass(),
        )
        assert (
            embedding_smoke.main(["offline"])
            == embedding_smoke.EXIT_CODES["PASS"]
        )

    def test_authorized_live_without_execution_exits_preparation_incomplete(
        self, monkeypatch: Any, capsys: Any
    ) -> None:
        """Both authorization barriers satisfied + no live provider
        execution still implemented -> evidence stays PREPARATION_INCOMPLETE
        and the CLI exits 2 (never 0)."""
        import app.ops.embedding_smoke as embedding_smoke

        monkeypatch.setenv("FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM", "yes")
        monkeypatch.setattr(embedding_smoke, "application_settings", _config())
        captured_evidence: dict[str, EmbeddingSmokeEvidence] = {}
        real_build = embedding_smoke.build_offline_evidence

        def spying_build(config: Settings) -> EmbeddingSmokeEvidence:
            evidence = real_build(config)
            captured_evidence["evidence"] = evidence
            return evidence

        monkeypatch.setattr(embedding_smoke, "build_offline_evidence", spying_build)

        rc = embedding_smoke.main(["--live"])
        out = capsys.readouterr().out

        assert rc == embedding_smoke.EXIT_CODES["PREPARATION_INCOMPLETE"]
        assert rc == 2
        assert "LIVE MODE: authorized externally" in out
        assert "not executed by WP-P7-02" in out
        assert "OVERALL: PREPARATION_INCOMPLETE" in out
        # The authorized path appended nothing on top of the pure offline
        # evidence — proving no live provider execution code path ran.
        assert captured_evidence["evidence"].overall == "PREPARATION_INCOMPLETE"

    def test_unauthorized_live_exits_refused(self, monkeypatch: Any) -> None:
        import app.ops.embedding_smoke as embedding_smoke

        monkeypatch.delenv("FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM", raising=False)
        monkeypatch.setattr(embedding_smoke, "application_settings", _config())
        assert embedding_smoke.main(["--live"]) == embedding_smoke.EXIT_CODES["REFUSED"]
        assert embedding_smoke.main(["--live"]) == 3


# ---------------------------------------------------------------------------
# Live-authorization barrier
# ---------------------------------------------------------------------------


class TestLiveAuthorizationBarrier:
    def test_refuses_without_confirmation_env(self, monkeypatch: Any) -> None:
        monkeypatch.delenv("FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM", raising=False)
        with pytest.raises(EmbeddingSmokeError, match="not authorized"):
            assert_live_authorized()

    def test_refuses_with_wrong_confirmation_value(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM", "maybe")
        with pytest.raises(EmbeddingSmokeError):
            assert_live_authorized()

    def test_passes_only_with_double_barrier(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("FORGEMIND_EMBEDDING_SMOKE_LIVE_CONFIRM", "yes")
        assert_live_authorized()  # no exception
