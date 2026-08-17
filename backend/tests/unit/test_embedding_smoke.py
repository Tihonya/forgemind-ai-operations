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
